"""Exporta una corrida para la visualización web.

Antes: SUMO escribía FCD en XML (cientos de MB), Python lo releía con ElementTree y
lo mandaba en base64 dentro de un .js. Ahora SUMO escribe el FCD en Parquet cada
`muestreo` segundos, se lee en columnas con pyarrow y se guardan trayectorias simplificadas: de
cada vehículo solo quedan los puntos donde cambia de velocidad o de dirección (con un
error máximo de `tolerancia` metros). Un carro parado una hora queda en dos puntos.

Salida en viz/data/ (el contrato con el visor web):
  manifest.json        versión, archivos comunes y lista de escenarios
  red.json             calles, semáforos, corredores explícitos, origen geográfico
  <escenario>/meta.json  métricas, curva por minuto, periodos con las decisiones por
                       corredor, índice de las ventanas
  <escenario>/NNNN.bin una ventana de `VENTANA_S` (los periodos del agente): los tramos de
                       vehículo cuyo [primer t, último t] se solapa con [t0, t1] (aunque no
                       tengan puntos dentro: un carro parado); el que cruza un borde se repite en las
                       dos ventanas con el último punto anterior a t0 y el primero posterior
                       a t1, para que la interpolación siga continua. Así el visor baja solo
                       el pedazo que muestra. Columnas, listas para deck.gl TripsLayer:
                         inicio   uint32[n+1]  primer punto de cada tramo
                         tipo     uint8[n]     0 carro, 1 moto, 2 bus, 3 camión
                         xy       int32[2p]    decímetros desde el origen; el primer punto de
                                               cada tramo absoluto y los demás como diferencia
                         t        uint16[p]    segundos; igual: primero absoluto, luego diferencia
                         v        uint8[p]     km/h
                       En diferencias los bytes altos quedan casi todos en cero y brotli/gzip
                       los comprimen ~3.5x (vs ~1.8x en float32). El cliente reconstruye con
                       una suma acumulada por tramo.
Uso: uv run python -m open_jam.export on off --hasta 5400
"""

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import resource
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import sumolib

from . import corredores, rutas, trayectos
from .config import Corrida
from .politicas import politica
from .sim import correr

TIPOS = {"carro": 0, "moto": 1, "bus": 2, "camion": 3}
# jerarquía de la vía para dibujarla: 0 autopista/troncal, 1 primaria, 2 secundaria/terciaria, 3 local
JERARQUIA = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2, "tertiary": 2}
VENTANA_S = 900  # igual al periodo del agente: cada ventana es un periodo de decisiones
COLUMNAS = ("inicio", "tipo", "xy", "t", "v")
VERSION = 1
TITULOS = {"on": "Semáforos encendidos", "off": "Semáforos apagados", "agente": "Agente"}


def red(net, archivo_corr: Path | None = corredores.ARCHIVO) -> dict[str, Any]:
    """Calles, semáforos y corredores de la red (sumolib) para el visor."""
    calles = []
    for e in net.getEdges():
        if e.getFunction() == "internal":
            continue
        pts = [c for xy in e.getShape() for c in (round(xy[0], 1), round(xy[1], 1))]
        calles.append({"id": e.getID(), "p": pts, "l": e.getLaneNumber(), "n": e.getName(),
                       "w": round(sum(lane.getWidth() for lane in e.getLanes()), 1),
                       "k": JERARQUIA.get(e.getType().removeprefix("highway.").removesuffix("_link"), 3)})
    semaforos = []
    for tls in net.getTrafficLights():
        nodos = {c[0].getEdge().getToNode() for c in tls.getConnections()}
        xs = [n.getCoord() for n in nodos]
        nombres = sorted({c[0].getEdge().getName() for c in tls.getConnections() if c[0].getEdge().getName()})
        semaforos.append({"id": tls.getID(), "x": round(sum(p[0] for p in xs) / len(xs), 1),
                          "y": round(sum(p[1] for p in xs) / len(xs), 1), "n": " y ".join(nombres[:2])})
    # Los mismos corredores y semáforos que usa la simulación (corredores.py es la única fuente).
    lista = corredores.cargar(archivo_corr) if archivo_corr else []
    corr = corredores.con_semaforos(lista, corredores.enlaces_net(net))
    indice = {c["id"]: k for k, c in enumerate(calles)}
    faltan = sorted({e for c in lista for e in c["tramos"]} - indice.keys())
    if faltan:
        raise ValueError(f"{archivo_corr}: {len(faltan)} tramos no están en la red (p. ej. {faltan[:3]})")
    (x0, y0), (x1, y1) = net.getBBoxXY()
    # una red sin proyección (las de prueba) no tiene origen geográfico
    origen = list(net.convertXY2LonLat(0, 0)) if net.hasGeoProj() else None
    return {"origen": origen, "bbox": [x0, y0, x1, y1], "calles": calles, "semaforos": semaforos,
            "corredores": [{"id": k, "nombre": c["nombre"], "calles": sorted(indice[e] for e in c["tramos"]),
                            "semaforos": c["semaforos"]} for k, c in corr.items()]}


def leer_fcd(fcd: Path | list[Path]) -> tuple[np.ndarray, np.ndarray, int]:
    """Lee el FCD que SUMO escribió en Parquet (uno o uno por tramo) y lo deja por vehículo y por tiempo.

    Devuelve (filas [vehículo, t, x, y, km/h] en float32, tipo de cada vehículo, n vehículos).
    """
    # Un micro de 90 min son ~80 M de filas: se arma directo en float32, tramo por tramo, para que
    # entre en la memoria de la VM (con float64 y np.unique sobre todo pasaba de 14 GB).
    partes, hasta = [], -np.inf
    for f in [fcd] if isinstance(fcd, Path) else fcd:
        tab = pq.read_table(f)
        tab = tab.filter(pc.is_valid(tab["vehicle_id"]))  # los pasos sin vehículos vienen como filas nulas
        # el paso del punto de control lo escriben los dos tramos: queda el del anterior
        tab = tab.filter(pc.greater(tab["timestep_time"], hasta))
        if len(tab):
            hasta = pc.max(tab["timestep_time"]).as_py()
        partes.append(tab)
    ids = pc.dictionary_encode(pa.chunked_array([c for p in partes for c in p["vehicle_id"].chunks],
                                                pa.string())).combine_chunks()
    tipos = pc.dictionary_encode(pa.chunked_array([c for p in partes for c in p["vehicle_type"].chunks],
                                                  pa.string())).combine_chunks()
    a = np.empty((len(ids), 5), np.float32)
    a[:, 0] = ids.indices.to_numpy()
    i = 0
    for p in partes:
        j = i + len(p)
        a[i:j, 1] = p["timestep_time"].to_numpy()
        a[i:j, 2] = p["vehicle_x"].to_numpy()
        a[i:j, 3] = p["vehicle_y"].to_numpy()
        a[i:j, 4] = p["vehicle_speed"].to_numpy()
        i = j
    a[:, 4] *= 3.6
    del partes
    # tipo de cada vehículo (el de su primera aparición)
    n = len(ids.dictionary)
    _, primera = np.unique(ids.indices.to_numpy(), return_index=True)
    nombres_tipo = tipos.dictionary.to_pylist()
    tipo = np.array([TIPOS.get(nombres_tipo[k], 0) for k in tipos.indices.to_numpy()[primera]], np.uint8)
    return a, tipo, n


def curva(a: np.ndarray) -> list[dict[str, Any]]:
    """Vehículos en red, velocidad media y fracción parados, cada minuto."""
    m = a[a[:, 1] % 60 == 0]
    minuto = (m[:, 1] // 60).astype(np.int64)
    n = np.bincount(minuto)
    kmh = np.bincount(minuto, m[:, 4])
    parados = np.bincount(minuto, m[:, 4] < 5)
    return [{"t": int(k) * 60, "n": int(n[k]), "kmh": round(float(kmh[k] / n[k]), 1),
             "parados": round(float(parados[k] / n[k]), 3)} for k in np.flatnonzero(n)]


def tramos(a: np.ndarray, tipo: np.ndarray, salto: float) -> tuple[np.ndarray, int, np.ndarray]:
    """Parte cada vehículo donde desaparece del FCD (teleport): el visor lo dibujaría cruzando manzanas.

    Devuelve las filas con el número de tramo en vez del de vehículo, cuántos tramos hay y su tipo.
    """
    a = a[np.lexsort((a[:, 1], a[:, 0]))]  # por vehículo y luego por tiempo
    nuevo = np.ones(len(a), bool)
    nuevo[1:] = (a[1:, 0] != a[:-1, 0]) | (a[1:, 1] - a[:-1, 1] > salto)
    tipo = tipo[a[nuevo, 0].astype(np.int64)]
    a[:, 0] = np.cumsum(nuevo) - 1
    return a, len(tipo), tipo


def simplificar(a: np.ndarray, n: int, tolerancia: float) -> tuple[np.ndarray, np.ndarray]:
    """Puntos simplificados de cada tramo, ordenados por tramo y tiempo, e `inicio` de cada uno."""
    a = a[np.lexsort((a[:, 1], a[:, 0]))]  # por tramo y luego por tiempo
    inicio = np.searchsorted(a[:, 0], np.arange(n + 1)).astype(np.uint32)
    b = a[trayectos.simplificar(a[:, 1], a[:, 2], a[:, 3], inicio, tolerancia)]
    return b, np.searchsorted(b[:, 0], np.arange(n + 1)).astype(np.uint32)


def ventana(t: np.ndarray, tramo: np.ndarray, t0: float, t1: float) -> np.ndarray:
    """Máscara de los puntos (ordenados por tramo y tiempo) que van en la ventana [t0, t1].

    Los puntos dentro, más el último anterior a t0 y el primero posterior a t1 de cada
    tramo que cruza un borde; así entra también un tramo activo en la ventana pero sin
    puntos dentro (un carro parado del que la simplificación dejó solo los extremos).
    """
    sigue = tramo[1:] == tramo[:-1]  # el punto i+1 es del mismo tramo que el i
    keep = (t >= t0) & (t <= t1)
    keep[:-1] |= sigue & (t[:-1] < t0) & (t[1:] >= t0)
    keep[1:] |= sigue & (t[1:] > t1) & (t[:-1] <= t1)
    return keep


def columnas(b: np.ndarray, tramo: np.ndarray, tipo: np.ndarray) -> dict[str, np.ndarray]:
    """Columnas del binario de los puntos `b` (ordenados), del tramo `tramo[i]` cada uno."""
    ids = np.unique(tramo)
    inicio = np.searchsorted(tramo, ids).astype(np.uint32)
    inicio = np.append(inicio, np.uint32(len(b)))
    return {"inicio": inicio, "tipo": tipo[ids],
            "xy": diferencias(np.round(b[:, 2:4] * 10).astype(np.int32), inicio).ravel(),
            "t": diferencias(np.round(b[:, 1]).astype(np.int64), inicio).astype(np.uint16),
            "v": np.clip(np.round(b[:, 4]), 0, 255).astype(np.uint8)}


def diferencias(a: np.ndarray, inicio: np.ndarray) -> np.ndarray:
    """Cada fila menos la anterior, salvo la primera de cada vehículo, que queda absoluta."""
    d = a.copy()
    d[1:] -= a[:-1]
    primeros = inicio[:-1][inicio[:-1] < len(a)]
    d[primeros] = a[primeros]
    return d


def acumular(d: np.ndarray, inicio: np.ndarray) -> np.ndarray:
    """Inversa de `diferencias` (lo que hace el cliente web)."""
    a = np.cumsum(d, axis=0, dtype=np.int64)
    base = np.repeat(np.concatenate([[0], a[inicio[1:-1] - 1]]) if d.ndim == 1 else
                     np.vstack([np.zeros((1,) + d.shape[1:], np.int64), a[inicio[1:-1] - 1]]),
                     np.diff(inicio).astype(np.int64), axis=0)
    return a - base


def escribir(archivo: Path, cols: dict[str, np.ndarray]) -> dict[str, Any]:
    """Escribe las columnas una tras otra; devuelve su índice, tamaño y sha256."""
    indice, datos = {}, bytearray()
    for k in COLUMNAS:
        indice[k] = {"offset": len(datos), "len": len(cols[k]), "dtype": str(cols[k].dtype)}
        datos += cols[k].tobytes()
        datos += b"\0" * ((-len(datos)) % 4)  # alinea cada columna a 4 bytes para leerla con TypedArray sin copiar
    archivo.write_bytes(datos)
    return {"bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest(), "binario": indice}


def exportar(c: Corrida, muestreo: float = 2, tolerancia: float = 1.5, dest: Path = rutas.VIZ / "data",
             ventana_s: int = VENTANA_S) -> tuple[dict[str, Any], int]:
    """Corre `c` y escribe `dest/<nombre>/meta.json` y sus ventanas; devuelve (meta, bytes)."""
    carpeta = dest / c.nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("*.bin"):  # ventanas de un export anterior más largo
        viejo.unlink()
    rutas.OUT.mkdir(parents=True, exist_ok=True)
    # TraCI y no libsumo: libsumo trae su propio Arrow y choca con pyarrow en el mismo proceso.
    # Con SUMO avanzando solo entre decisiones, TraCI rinde igual (ver open_jam/bench.py).
    # La fluidez siempre: el visor muestra las decisiones de cada periodo.
    c = c.con(backend="traci", fluidez=c.fluidez or ventana_s, fcd=muestreo)
    metr = correr(c)
    fcd = c.tramos("fcd.parquet")
    a, tipo, n = leer_fcd(fcd)
    memoria(c.nombre, "FCD leído")
    a2, n_tramos, tipo_tramo = tramos(a, tipo, 2 * muestreo)
    b, inicio = simplificar(a2, n_tramos, tolerancia)
    t = np.round(b[:, 1])
    tramo = np.repeat(np.arange(n_tramos), np.diff(inicio).astype(np.int64))
    ventanas = []
    for k in range(max(1, math.ceil(float(t.max(initial=0)) / ventana_s))):
        t0, t1 = k * ventana_s, (k + 1) * ventana_s
        keep = ventana(t, tramo, t0, t1)
        cols = columnas(b[keep], tramo[keep], tipo_tramo)
        archivo = f"{c.nombre}/{k:04d}.bin"
        ventanas.append({"t0": t0, "t1": t1, "archivo": archivo, "tramos": len(cols["tipo"]),
                         "puntos": len(cols["t"]), **escribir(dest / archivo, cols)})
    periodos = metr.pop("periodos", [])
    meta = {"escenario": c.nombre, "politica": politica(c.politica).nombre, "muestreo_s": muestreo,
            "tolerancia_m": tolerancia, "ventana_s": ventana_s, "metricas": metr, "periodos": periodos,
            "curva": curva(a), "vehiculos": n, "tramos": n_tramos, "puntos": len(b), "puntos_crudos": len(a),
            "ventanas": ventanas}
    (carpeta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
    memoria(c.nombre, "ventanas escritas")
    for f in fcd:  # recién ahora: si algo de arriba falla, se reintenta sin volver a simular
        f.unlink()
    return meta, sum(v["bytes"] for v in ventanas)


def memoria(escenario: str, etapa: str) -> None:
    """Pico de memoria del proceso hasta acá, en el log (ru_maxrss: KB en Linux, bytes en macOS)."""
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    print(f"{escenario}: pico de memoria {pico / 2**30:.1f} GiB ({etapa})", flush=True)


def escribir_manifest(dest: Path, escenarios: list[str]) -> dict[str, Any]:
    """Agrega o actualiza `escenarios` en dest/manifest.json; conserva los demás que sigan exportados."""
    archivo = dest / "manifest.json"
    previo = json.loads(archivo.read_text()) if archivo.exists() else {}
    lista = [e for e in previo.get("escenarios", []) if e["id"] not in escenarios and (dest / e["meta"]).exists()]
    lista += [{"id": e, "titulo": TITULOS.get(e, e), "meta": f"{e}/meta.json"} for e in escenarios]
    orden = list(TITULOS)
    lista.sort(key=lambda e: (orden.index(e["id"]) if e["id"] in orden else len(orden), e["id"]))
    manifest = {"version": VERSION, "red": "red.json", "escena": "escena.json", "terreno": "terreno.bin",
                "escenarios": lista}
    archivo.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("escenarios", nargs="*", default=["on", "off"], help="políticas: on, off, agente")
    ap.add_argument("--hasta", type=int, default=5400)
    ap.add_argument("--muestreo", type=float, default=2)
    ap.add_argument("--tolerancia", type=float, default=1.5)
    ap.add_argument("--meso", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--control", type=int, default=900,
                    help="punto de control cada N s simulados (0: ninguno); un export cortado retoma desde ahí")
    a = ap.parse_args()
    dest = rutas.VIZ / "data"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "red.json").write_text(json.dumps(red(sumolib.net.readNet(str(rutas.NET))),
                                              ensure_ascii=False, separators=(",", ":")))
    # Un proceso por escenario: cada SUMO usa sus hilos y los escenarios corren a la vez.
    corridas = [Corrida(e, politica=e, hasta=a.hasta, meso=a.meso, threads=a.threads, control_s=a.control)
                for e in a.escenarios]
    with ProcessPoolExecutor(len(corridas), mp_context=mp.get_context("spawn")) as ex:
        res = ex.map(exportar, corridas, [a.muestreo] * len(corridas), [a.tolerancia] * len(corridas))
    for e, (meta, tam) in zip(a.escenarios, res):
        print(f"{e}: {meta['vehiculos']} vehículos, {meta['puntos_crudos']} -> {meta['puntos']} puntos, "
              f"{len(meta['ventanas'])} ventanas, {tam / 1e6:.1f} MB", flush=True)
    escribir_manifest(dest, a.escenarios)


if __name__ == "__main__":
    main()
