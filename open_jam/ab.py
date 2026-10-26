"""A/B de controladores de semáforos: el mismo tramo de hora pico, con y sin el agente.

Un `Caso` es (seed, escala, t0): la simulación con los semáforos de Webster corre hasta
`t0` y guarda su estado (con el generador aleatorio). Desde ese mismo estado corre `dur`
segundos cada controlador. Los vehículos, sus rutas y el azar son los mismos; lo único
que cambia es la decisión, así que la diferencia es del controlador.

Para no ajustar el agente a un solo tramo hay dos conjuntos de casos: `ajuste`, para
mejorarlo, y `prueba`, con otras semillas, otra demanda y otros t0, que se mira solo al
final.

Métricas de cada tramo, en toda la red:
  parado_h     vehículos·hora parados (< 0.1 m/s), muestreado cada `MUESTRA_S`: la principal
  llegaron     vehículos que terminaron su viaje en el tramo
  cola_final   vehículos parados al terminar: un controlador que deja el atasco para
               después se nota acá, no en parado_h
  teleports    vehículos que SUMO sacó por trabados

Uso:
  uv run python -m open_jam.ab presion --conjunto ajuste --paralelo 4
  MODEL_API_KEY=... uv run python -m open_jam.ab muse --conjunto ajuste
Resultados: out/ab/<fecha>-<controlador>-<conjunto>.jsonl, una línea por caso y controlador.
"""

import argparse
import json
import multiprocessing as mp
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from . import rutas, tiempos
from .config import Corrida
from .malla import Malla
from .sim import huella

DUR_S = 900
MUESTRA_S = 10
METRICAS = ("parado_h", "llegaron", "cola_final", "teleports")

BASE = Corrida("ab", fluidez=0, salidas=False, corredores=None, extra=("--save-state.rng",))


@dataclass(frozen=True)
class Caso:
    seed: int
    escala: float  # demanda relativa a la calibrada
    t0: int  # segundo simulado en que empieza el tramo
    dur: int = DUR_S


CONJUNTOS = {
    "ajuste": [Caso(s, 1.0, t0) for s in (1, 2, 3) for t0 in (1800, 2700)],
    "prueba": [Caso(s, e, t0) for s in (101, 102) for e in (0.9, 1.1) for t0 in (2250, 3150)],
}


class Controlador:
    """Base: los semáforos siguen su ciclo de Webster, nadie toca nada.

    `decidir` se llama cada `cada` segundos simulados con la `Lectura` de la malla y
    devuelve {tls: verdes nuevos} (ver `tiempos.fijar`) para los que cambian.
    """

    nombre = "webster"
    cada: float = 120

    def empezar(self, sumo, malla: Malla) -> None:
        pass

    def decidir(self, lectura) -> dict[str, list[float]]:
        return {}

    def resumen(self) -> dict[str, Any]:
        """Lo que el controlador quiera sumar a la fila de resultados (llamadas, tokens...)."""
        return {}


class MaxPresion(Controlador):
    """Ejemplo: reparte el verde del ciclo según la presión de cada fase.

    Presión de una fase: parados en los tramos que entran con verde menos parados en los
    tramos a los que salen (si la salida está llena, darle verde no sirve). El ciclo
    conserva el verde total de Webster; cada fase tiene al menos `VERDE_MIN_S` y el resto
    se reparte en proporción a la presión. `suavizado` acerca los tiempos de a poco al
    reparto, para no oscilar. Sin presión en ninguna fase, vuelve hacia Webster.
    """

    nombre = "presion"

    def __init__(self, cada: float = 120, suavizado: float = 0.5):
        self.cada = cada
        self.suavizado = suavizado

    def empezar(self, sumo, malla: Malla) -> None:
        idx = {t: k for k, t in enumerate(malla.tramos)}
        self.fases: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
        self.webster: dict[str, np.ndarray] = {}
        for tls in malla.nodos:
            verdes = np.array(tiempos.verdes(sumo, tls))
            if len(verdes) < 2 or verdes.sum() < len(verdes) * tiempos.VERDE_MIN_S:
                continue  # nada que repartir
            self.fases[tls] = [(np.array([idx[a] for a, _ in m], int), np.array([idx[b] for _, b in m], int))
                               for m in tiempos.movimientos(sumo, tls)]
            self.webster[tls] = verdes
        self.actual = dict(self.webster)

    def decidir(self, lectura) -> dict[str, list[float]]:
        q = lectura.parados
        res = {}
        for tls, fases in self.fases.items():
            p = np.array([max(q[e].sum() - q[s].sum(), 0) for e, s in fases])
            w = self.webster[tls]
            if p.sum() == 0:
                objetivo = w
            else:
                objetivo = tiempos.VERDE_MIN_S + (w.sum() - len(w) * tiempos.VERDE_MIN_S) * p / p.sum()
            antes = self.actual[tls]
            nuevo = np.clip(np.round(antes + self.suavizado * (objetivo - antes)),
                            tiempos.VERDE_MIN_S, tiempos.VERDE_MAX_S)
            if np.abs(nuevo - antes).max() >= 1:
                res[tls] = nuevo.tolist()
                self.actual[tls] = nuevo
        return res


NOMBRES = ("webster", "presion", "muse")


def crear(nombre: str) -> Controlador:
    if nombre == "muse":
        from .muse import ControladorMuse  # perezoso: muse.py importa este módulo

        return ControladorMuse()
    return {"webster": Controlador, "presion": MaxPresion}[nombre]()


def archivo_estado(base: Corrida, caso: Caso, out: Path) -> Path:
    c = base.con(seed=caso.seed, escala=caso.escala)
    return out / "ab" / "estados" / f"{huella(c)}-{caso.t0:05d}.xml.gz"


def preparar(base: Corrida, casos: list[Caso], out: Path) -> None:
    """Corre con Webster desde 0 y guarda el estado en el t0 de cada caso que falte.

    Todos los `casos` tienen que tener la misma seed y escala: una sola corrida los cubre.
    """
    import libsumo as sumo

    faltan = sorted({k.t0 for k in casos if not archivo_estado(base, k, out).exists()})
    if not faltan:
        return
    k = casos[0]
    archivo_estado(base, k, out).parent.mkdir(parents=True, exist_ok=True)
    sumo.start(base.con(seed=k.seed, escala=k.escala, hasta=faltan[-1]).args())
    try:
        for t0 in faltan:
            sumo.simulationStep(t0)
            final = archivo_estado(base, Caso(k.seed, k.escala, t0), out)
            tmp = final.with_name(f"tmp-{final.name}")
            sumo.simulation.saveState(str(tmp))
            tmp.replace(final)  # el estado vale solo si está completo
    finally:
        sumo.close()


def tramo(base: Corrida, caso: Caso, nombre: str, out: Path) -> dict[str, Any]:
    """Corre el tramo de `caso` con el controlador `nombre` desde el estado guardado."""
    import libsumo as sumo
    import sumolib

    c = base.con(seed=caso.seed, escala=caso.escala, hasta=caso.t0 + caso.dur)
    malla = Malla.desde_net(sumolib.net.readNet(str(c.net)))
    ctrl = crear(nombre)
    t_real = time.perf_counter()
    sumo.start(c.args(desde=caso.t0, estado=archivo_estado(base, caso, out)))
    try:
        ctrl.empezar(sumo, malla)
        calles = [e for e in sumo.edge.getIDList() if not e.startswith(":")]

        def parados():
            return sum(sumo.edge.getLastStepHaltingNumber(e) for e in calles)

        t, proxima = sumo.simulation.getTime(), caso.t0
        parado = llegaron = teleports = cambios = 0
        while t < c.hasta:
            if t >= proxima:
                nuevos = ctrl.decidir(malla.leer(sumo))
                for tls, verdes in nuevos.items():
                    tiempos.fijar(sumo, tls, verdes)
                cambios += len(nuevos)
                proxima = t + ctrl.cada
            if (t - caso.t0) % MUESTRA_S == 0:
                parado += parados() * MUESTRA_S
            sumo.simulationStep()
            llegaron += sumo.simulation.getArrivedNumber()
            teleports += sumo.simulation.getStartingTeleportNumber()
            t = sumo.simulation.getTime()
        cola = parados()
    finally:
        sumo.close()
    return asdict(caso) | {"controlador": nombre, "parado_h": round(parado / 3600, 2), "llegaron": llegaron,
                           "cola_final": cola, "teleports": teleports, "cambios": cambios,
                           **ctrl.resumen(), "pared_s": round(time.perf_counter() - t_real, 1)}


def _preparar(args):
    preparar(*args)


def _tramo(args):
    return tramo(*args)


def correr(controladores: list[str], casos: list[Caso], base: Corrida = BASE, paralelo: int = 1,
           out: Path | None = None) -> list[dict[str, Any]]:
    """Cada controlador en cada caso; cada simulación en su proceso (libsumo admite una por proceso)."""
    out = out or rutas.OUT
    grupos: dict[tuple[int, float], list[Caso]] = {}
    for k in casos:
        grupos.setdefault((k.seed, k.escala), []).append(k)
    ctx = mp.get_context("spawn")
    with ctx.Pool(paralelo, maxtasksperchild=1) as pool:
        pool.map(_preparar, [(base, g, out) for g in grupos.values()])
        return pool.map(_tramo, [(base, k, n, out) for k in casos for n in controladores])


def comparar(filas: list[dict[str, Any]], a: str, b: str) -> dict[str, dict[str, float]]:
    """Por métrica, la diferencia b - a en cada caso: media, desvío y en cuántos casos b < a."""
    por_caso: dict[tuple, dict[str, dict]] = {}
    for f in filas:
        por_caso.setdefault((f["seed"], f["escala"], f["t0"], f["dur"]), {})[f["controlador"]] = f
    pares = [(d[a], d[b]) for d in por_caso.values() if a in d and b in d]
    res = {}
    for m in METRICAS:
        dif = [y[m] - x[m] for x, y in pares]
        res[m] = {"n": len(dif), "media": round(statistics.fmean(dif), 2) if dif else 0,
                  "desvio": round(statistics.stdev(dif), 2) if len(dif) > 1 else 0,
                  "b_menor": sum(d < 0 for d in dif)}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("controlador", choices=NOMBRES[1:])
    ap.add_argument("--conjunto", choices=sorted(CONJUNTOS), default="ajuste")
    ap.add_argument("--dur", type=int, default=DUR_S)
    ap.add_argument("--paralelo", type=int, default=1)
    ap.add_argument("--threads", type=int, default=1)
    a = ap.parse_args()
    casos = [k if a.dur == k.dur else Caso(k.seed, k.escala, k.t0, a.dur) for k in CONJUNTOS[a.conjunto]]
    filas = correr(["webster", a.controlador], casos, BASE.con(threads=a.threads), a.paralelo)
    d = rutas.OUT / "ab"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now():%Y%m%d-%H%M%S}-{a.controlador}-{a.conjunto}.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in filas))
    for m, r in comparar(filas, "webster", a.controlador).items():
        print(f"{m:11s} {a.controlador} - webster: {r['media']:+9.2f} ± {r['desvio']:7.2f}  "
              f"menor en {r['b_menor']}/{r['n']} casos")
    print(f"-> {f.relative_to(rutas.ROOT)}")


if __name__ == "__main__":
    main()
