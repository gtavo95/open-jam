from itertools import pairwise

import numpy as np
import pytest

from open_jam import trayectos


def recorridos(n_veh=200, seed=0):
    """Vehículos que avanzan, frenan y se paran, muestreados cada 2 s."""
    rng = np.random.default_rng(seed)
    t, x, y, inicio = [], [], [], [0]
    for _ in range(n_veh):
        n = int(rng.integers(1, 400))
        tt = np.arange(n) * 2.0
        vel = np.where(rng.random(n) < 0.3, 0, rng.uniform(0, 15, n))
        ang = np.cumsum(rng.normal(0, 0.05, n))
        x.append(np.cumsum(vel * np.cos(ang) * 2))
        y.append(np.cumsum(vel * np.sin(ang) * 2))
        t.append(tt)
        inicio.append(inicio[-1] + n)
    f = lambda a: np.concatenate(a).astype(np.float32)
    return f(t), f(x), f(y), np.array(inicio, np.uint32)


def error_max(t, x, y, inicio, keep):
    peor = 0.0
    for a, b in pairwise(inicio):
        k = np.flatnonzero(keep[a:b]) + a
        px = np.interp(t[a:b], t[k], x[k])
        py = np.interp(t[a:b], t[k], y[k])
        peor = max(peor, float(np.hypot(px - x[a:b], py - y[a:b]).max()))
    return peor


@pytest.mark.parametrize("tol", [0.5, 1.5, 5.0])
def test_error_acotado(tol):
    t, x, y, inicio = recorridos()
    keep = trayectos.simplificar(t, x, y, inicio, tol)
    assert keep[inicio[:-1]].all() and keep[inicio[1:] - 1].all()  # extremos siempre
    assert error_max(t, x, y, inicio, keep) <= tol + 1e-3
    assert keep.mean() < 0.9


@pytest.mark.skipif(trayectos._rs is None, reason="extensión Rust sin compilar")
def test_rust_igual_a_python():
    t, x, y, inicio = recorridos(50)
    a = trayectos.simplificar(t, x, y, inicio, 1.5)
    b = trayectos.simplificar_py(t, x, y, inicio, 1.5)
    assert (a == b).all()
