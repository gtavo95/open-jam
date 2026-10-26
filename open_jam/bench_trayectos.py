"""Benchmark de la simplificación de trayectorias: Python puro contra Rust (rayon).

Uso: uv run python -m open_jam.bench_trayectos [--vehiculos 26000]
"""

import argparse
import time
from itertools import pairwise

import numpy as np

from . import trayectos


def datos(n_veh, seed=0):
    """Vehículos de ~700 muestras (1400 s a 2 s), con tramos parados como en hora pico."""
    rng = np.random.default_rng(seed)
    largos = rng.integers(100, 1300, n_veh)
    inicio = np.concatenate([[0], np.cumsum(largos)]).astype(np.uint32)
    n = int(inicio[-1])
    t = np.empty(n, np.float32)
    x = np.empty(n, np.float32)
    y = np.empty(n, np.float32)
    for a, b in pairwise(inicio):
        k = b - a
        vel = np.where(rng.random(k) < 0.4, 0, rng.uniform(0, 15, k))
        ang = np.cumsum(rng.normal(0, 0.03, k))
        t[a:b] = np.arange(k) * 2
        x[a:b] = np.cumsum(vel * np.cos(ang) * 2)
        y[a:b] = np.cumsum(vel * np.sin(ang) * 2)
    return t, x, y, inicio


def medir(f, *args):
    t0 = time.perf_counter()
    r = f(*args)
    return time.perf_counter() - t0, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehiculos", type=int, default=26000)
    ap.add_argument("--muestra-py", type=int, default=500, help="vehículos para medir Python (se extrapola)")
    a = ap.parse_args()
    t, x, y, inicio = datos(a.vehiculos)
    print(f"{a.vehiculos} vehículos, {len(t) / 1e6:.1f} M puntos")
    s_rs, keep = medir(trayectos.simplificar, t, x, y, inicio, 1.5)
    print(f"rust   {s_rs:7.3f} s  conserva {keep.mean():.1%}")
    m = a.muestra_py
    fin = inicio[m]
    s_py, keep_py = medir(trayectos.simplificar_py, t[:fin], x[:fin], y[:fin], inicio[:m + 1], 1.5)
    s_py_total = s_py * len(t) / fin
    print(f"python {s_py_total:7.1f} s  (extrapolado de {m} vehículos)  -> rust {s_py_total / s_rs:.0f}x")
    assert (keep_py == keep[:fin]).all()


if __name__ == "__main__":
    main()
