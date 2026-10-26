"""Simplificación de trayectorias en espacio-tiempo.

De cada vehículo se conserva un punto solo si, al interpolar linealmente en el tiempo
entre el último punto conservado y el siguiente candidato, algún punto intermedio
queda a más de `tol` metros de donde estaba de verdad. Es la versión greedy
("opening window") de Douglas-Peucker sincronizado en el tiempo (SED).

`simplificar` usa la extensión en Rust (`trayectos_rs`) si está compilada; si no,
la versión en Python puro de abajo, que sirve de referencia en los tests.
"""

import numpy as np

MAX_VENTANA = 64  # igual que en rust/trayectos/src/lib.rs

try:
    import trayectos_rs as _rs
except ImportError:  # sin compilar: uv run maturin develop -r -m rust/trayectos/Cargo.toml
    _rs = None


def simplificar(t, x, y, inicio, tol):
    """Máscara booleana de puntos a conservar. `inicio[i]:inicio[i+1]` es el vehículo i."""
    t, x, y = (np.ascontiguousarray(a, np.float32) for a in (t, x, y))
    inicio = np.ascontiguousarray(inicio, np.uint32)
    if _rs is not None:
        return np.frombuffer(_rs.simplificar(t, x, y, inicio, float(tol)), np.bool_)
    return simplificar_py(t, x, y, inicio, tol)


def simplificar_py(t, x, y, inicio, tol):
    keep = np.zeros(len(t), np.bool_)
    tol2 = tol * tol
    for i in range(len(inicio) - 1):
        a, b = int(inicio[i]), int(inicio[i + 1])
        if b - a == 0:
            continue
        keep[a] = keep[b - 1] = True
        ancla = a
        j = a + 2
        while j < b:
            # ¿todos los puntos entre ancla y j caben en el segmento ancla -> j?
            dt = t[j] - t[ancla]
            fuera = False
            for k in range(ancla + 1, j):
                f = (t[k] - t[ancla]) / dt if dt > 0 else 0.0
                px = x[ancla] + f * (x[j] - x[ancla])
                py = y[ancla] + f * (y[j] - y[ancla])
                if (px - x[k]) ** 2 + (py - y[k]) ** 2 > tol2:
                    fuera = True
                    break
            # Ventana máxima: acota el costo (cuadrático) en vehículos parados mucho tiempo.
            if fuera or j - ancla > MAX_VENTANA:
                ancla = j - 1
                keep[ancla] = True
            j += 1
    return keep
