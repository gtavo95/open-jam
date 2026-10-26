"""Benchmarks: corre variantes de una `Corrida` y mide tiempo real, memoria y resultado.

Cada variante corre en su propio proceso (libsumo admite una sola simulación por
proceso). Por defecto van de a una para que no compitan por CPU y memoria;
`--paralelo N` mide el rendimiento total cuando se corren N a la vez.

Uso:
  uv run python -m open_jam.bench base libsumo meso --hasta 1800
  uv run python -m open_jam.bench --lista
Resultados: out/bench/<fecha>.jsonl (una línea por corrida, con la curva por minuto).
"""

import argparse
import json
import multiprocessing as mp
import resource
import sys
import time
from datetime import datetime

from . import rutas
from .config import Corrida
from .sim import correr

BASE = Corrida("bench", backend="traci", fluidez=0)

VARIANTES = {
    "original": BASE.con(por_paso=True),  # como scripts/run_scenario.py: TraCI, vuelve a Python cada segundo
    "base": BASE,  # TraCI, pero SUMO avanza solo entre decisiones
    "libsumo": BASE.con(backend="libsumo"),
    "libsumo-t4": BASE.con(backend="libsumo", threads=4),
    "libsumo-t8": BASE.con(backend="libsumo", threads=8),
    "sin-internos": BASE.con(backend="libsumo", sin_internos=True),
    "teleport-120": BASE.con(backend="libsumo", teleport=120),
    "meso": BASE.con(backend="libsumo", meso=True),
    "meso-t4": BASE.con(backend="libsumo", meso=True, threads=4),
    "off": BASE.con(backend="libsumo", politica="off"),
    "meso-off": BASE.con(backend="libsumo", meso=True, politica="off"),
    "meso-fluidez": BASE.con(backend="libsumo", meso=True, fluidez=900),  # costo de medir la fluidez
    "fluidez": BASE.con(backend="libsumo", threads=4, fluidez=900),
    "libsumo-t2": BASE.con(backend="libsumo", threads=2),
    "sin-reruteo": BASE.con(backend="libsumo", threads=4, reruteo=False),  # costo del reruteo
    "meso-t8": BASE.con(backend="libsumo", meso=True, threads=8),
    "ch-t4": BASE.con(backend="libsumo", threads=4, ruteo="CH"),
    "chw-t4": BASE.con(backend="libsumo", threads=4, ruteo="CHWrapper"),
    "dijkstra-t4": BASE.con(backend="libsumo", threads=4, ruteo="dijkstra"),
}


def _una(nombre, c, cola):
    curva = []
    t0 = time.perf_counter()

    def observar(sumo, t):
        curva.append((int(t), round(time.perf_counter() - t0, 2), sumo.vehicle.getIDCount()))

    m = correr(c.con(nombre=f"bench-{nombre}"), observar=observar)
    m["max_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20)  # macOS: bytes
    m["curva"] = curva  # (t simulado, s reales, vehículos en red)
    cola.put(m)


def medir(nombres, hasta, paralelo=1):
    ctx = mp.get_context("spawn")
    cola = ctx.Queue()
    pend = [(n, VARIANTES[n].con(hasta=hasta)) for n in nombres]
    vivos, res = [], []
    while pend or vivos:
        while pend and len(vivos) < paralelo:
            n, c = pend.pop(0)
            p = ctx.Process(target=_una, args=(n, c, cola))
            p.start()
            vivos.append((n, p))
        r = cola.get()
        r["variante"] = r["escenario"].removeprefix("bench-")
        r["paralelo"] = paralelo
        res.append(r)
        resumen(r)
        for n, p in list(vivos):
            if n == r["variante"]:
                p.join()
                vivos.remove((n, p))
    return res


def resumen(r):
    print(f"{r['variante']:14s} pared {r['pared_s']:8.1f} s  carga {r['carga_s']:5.1f} s  "
          f"x{r['factor_tiempo_real']:6.2f} tiempo real  rss {r['max_rss_mb']:5d} MB  "
          f"llegaron {r.get('llegaron', '?'):>6}  teleports {r.get('teleports', '?'):>6}  "
          f"demora {r.get('demora_prom_s', '?')} s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("variantes", nargs="*", default=["base", "libsumo", "meso"])
    ap.add_argument("--hasta", type=int, default=1800)
    ap.add_argument("--paralelo", type=int, default=1)
    ap.add_argument("--lista", action="store_true")
    a = ap.parse_args()
    if a.lista:
        for n, c in VARIANTES.items():
            print(f"{n:14s} {c}")
        return
    desconocidas = set(a.variantes) - VARIANTES.keys()
    if desconocidas:
        sys.exit(f"variantes desconocidas: {desconocidas}")
    res = medir(a.variantes, a.hasta, a.paralelo)
    d = rutas.OUT / "bench"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in res))
    print(f"-> {f.relative_to(rutas.ROOT)}")


if __name__ == "__main__":
    main()
