"""Corredores: trechos de las avenidas con conteo de MuniGuate, la unidad de decisión del agente.

Cada corredor sale de una estación de conteo (`demanda.ESTACIONES`): los tramos de esa
avenida (`demanda.misma_calle`) conectados entre sí y a menos de `LARGO_M` metros de la
estación siguiendo la calle. Una avenida con varias estaciones (Periférico, Roosevelt,
Vista Hermosa, Ruta al Atlántico) queda partida: cada tramo va a la estación más cercana
por la calle, así ningún tramo cae en dos corredores. Antes un corredor era todo tramo
cuyo nombre contuviera el de la avenida, y "6a Avenida" juntaba las de todas las zonas.

La lista vive en data/corredores.json, versionada con la red. Se regenera con
`uv run python -m open_jam.corredores` cuando cambia sim/area.net.xml (cambian los ids de
los tramos). Los semáforos de cada corredor no se guardan: se derivan de la red cargada
(los que controlan la entrada a alguno de sus tramos o la salida de ellos), así siempre
coinciden con los semáforos que de verdad tiene la simulación.
"""

import heapq
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from . import rutas
from .demanda import ESTACIONES, RADIO_M, misma_calle

ARCHIVO = rutas.DATA / "corredores.json"
LARGO_M = 1500  # cuánto se sigue la avenida desde la estación, hacia cada lado
CALZADAS_M = 60  # tramos semilla: hasta esto más lejos que el más cercano (las dos calzadas)

Corredor = dict[str, Any]  # {"nombre": str, "tramos": [edge ids], "semaforos": [tls ids]}


def slug(texto: str) -> str:
    """Id estable y legible: "Roosevelt (Mixco)" -> "roosevelt-mixco"."""
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _distancias(semillas, de_nodo, largo_m):
    """Dijkstra sobre los nodos de una avenida, sin importar el sentido de los tramos:
    {tramo: metros desde las semillas hasta su extremo más cercano}, solo los < `largo_m`."""
    dist, cola = {}, []
    for e in semillas:
        for nodo in (e.getFromNode(), e.getToNode()):
            dist[nodo.getID()] = 0.0
            heapq.heappush(cola, (0.0, nodo.getID()))
    while cola:
        d, n = heapq.heappop(cola)
        if d > dist.get(n, float("inf")) or d >= largo_m:
            continue
        for e in de_nodo.get(n, ()):
            for otro in (e.getFromNode().getID(), e.getToNode().getID()):
                nd = d + e.getLength()
                if nd < dist.get(otro, float("inf")):
                    dist[otro] = nd
                    heapq.heappush(cola, (nd, otro))
    res = {}
    for n, d in dist.items():
        for e in de_nodo.get(n, ()):
            if d < largo_m:
                res[e.getID()] = min(res.get(e.getID(), float("inf")), d)
    for e in semillas:
        res[e.getID()] = 0.0
    return res


def generar(net, estaciones=ESTACIONES, largo_m: float = LARGO_M) -> list[dict[str, Any]]:
    """Corredores de la red `net` (sumolib), uno por estación con tramos de su avenida.

    Determinista: misma red y mismas estaciones dan el mismo resultado.
    """
    por_calle: dict[str, list] = {}
    for est in estaciones:
        por_calle.setdefault(est[1], []).append(est)
    res = []
    for calle, ests in por_calle.items():
        de_nodo: dict[str, list] = {}
        for e in net.getEdges():
            if misma_calle(calle, e.getName()):
                for nodo in {e.getFromNode().getID(), e.getToNode().getID()}:
                    de_nodo.setdefault(nodo, []).append(e)
        dists = []
        for etiqueta, _, lat, lon, _ in ests:
            x, y = net.convertLonLat2XY(lon, lat)
            cerca = [(d, e) for e, d in net.getNeighboringEdges(x, y, RADIO_M) if misma_calle(calle, e.getName())]
            if not cerca:
                raise ValueError(f"{etiqueta}: no hay tramo de '{calle}' a menos de {RADIO_M} m de la estación")
            dmin = min(d for d, _ in cerca)
            dists.append(_distancias([e for d, e in cerca if d <= dmin + CALZADAS_M], de_nodo, largo_m))
        # cada tramo a la estación más cercana por la calle (en empate, la primera de la lista)
        tramos: list[list[str]] = [[] for _ in ests]
        for e in sorted({e for d in dists for e in d}):
            k = min(range(len(ests)), key=lambda i: dists[i].get(e, float("inf")))
            tramos[k].append(e)
        for (etiqueta, _, lat, lon, _), ts in zip(ests, tramos):
            res.append({"id": slug(etiqueta), "nombre": etiqueta, "calle": calle, "estacion": [lat, lon],
                        "tramos": ts})
    return res


def guardar(lista: list[dict[str, Any]], archivo: Path = ARCHIVO, largo_m: float = LARGO_M) -> None:
    datos = {"generado_con": "uv run python -m open_jam.corredores", "largo_m": largo_m, "corredores": lista}
    archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n")


def cargar(archivo: Path = ARCHIVO) -> list[dict[str, Any]]:
    """Lista de corredores del archivo: [{"id", "nombre", "tramos", ...}], en orden."""
    if not archivo.exists():
        raise FileNotFoundError(f"no existe {archivo}: generalo con `uv run python -m open_jam.corredores`")
    lista = json.loads(archivo.read_text())["corredores"]
    ids = [c["id"] for c in lista]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{archivo}: ids de corredor repetidos")
    return lista


def enlaces_sumo(sumo) -> dict[str, set[str]]:
    """{tls: tramos que entran o salen por él}, de la simulación cargada (libsumo o traci)."""
    res: dict[str, set[str]] = {}
    for tls in sumo.trafficlight.getIDList():
        res[tls] = {carril.rsplit("_", 1)[0] for enlaces in sumo.trafficlight.getControlledLinks(tls)
                    for entra, sale, _ in enlaces for carril in (entra, sale)}
    return res


def enlaces_net(net) -> dict[str, set[str]]:
    """Lo mismo que `enlaces_sumo` pero leído con sumolib (sin simular)."""
    return {tls.getID(): {lane.getEdge().getID() for c in tls.getConnections() for lane in c[:2]}
            for tls in net.getTrafficLights()}


def con_semaforos(lista: list[dict[str, Any]], enlaces: dict[str, set[str]]) -> dict[str, Corredor]:
    """{id: {"nombre", "tramos", "semaforos"}}: cada corredor con los semáforos de sus tramos."""
    de_tramo: dict[str, set[str]] = {}
    for tls, tramos in enlaces.items():
        for e in tramos:
            de_tramo.setdefault(e, set()).add(tls)
    return {c["id"]: {"nombre": c["nombre"], "tramos": list(c["tramos"]),
                      "semaforos": sorted({s for e in c["tramos"] for s in de_tramo.get(e, ())})}
            for c in lista}


def corredores(sumo, archivo: Path | None = ARCHIVO) -> dict[str, Corredor]:
    """Corredores de `archivo` con sus semáforos en la simulación cargada; {} si `archivo` es None.

    Falla si algún tramo no está en la red: el archivo es de otra red o de otra versión.
    """
    if archivo is None:
        return {}
    lista = cargar(archivo)
    red = set(sumo.edge.getIDList())
    faltan = sorted({e for c in lista for e in c["tramos"]} - red)
    if faltan:
        raise ValueError(f"{archivo}: {len(faltan)} tramos no están en la red (p. ej. {faltan[:3]}); "
                         "regeneralo con `uv run python -m open_jam.corredores`")
    return con_semaforos(lista, enlaces_sumo(sumo))


def main() -> None:
    import sumolib

    net = sumolib.net.readNet(str(rutas.NET))
    lista = generar(net)
    guardar(lista)
    corr = con_semaforos(lista, enlaces_net(net))
    for c in lista:
        km = sum(net.getEdge(e).getLength() for e in c["tramos"]) / 1000
        print(f"{c['id']:24s} {len(c['tramos']):4d} tramos {km:5.1f} km {len(corr[c['id']]['semaforos']):3d} semáforos")
    print(f"-> {ARCHIVO.relative_to(rutas.ROOT)}")


if __name__ == "__main__":
    main()
