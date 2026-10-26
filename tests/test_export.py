import hashlib
import json
from itertools import pairwise

import numpy as np
import pytest
import sumolib

from open_jam import rutas
from open_jam.export import (
    acumular,
    diferencias,
    escribir_manifest,
    exportar,
    red,
    ventana,
)


def leer_ventana(dest, v):
    """Lo que hace el visor: columnas desde el índice y suma acumulada por tramo."""
    raw = (dest / v["archivo"]).read_bytes()
    col = {k: np.frombuffer(raw, np.dtype(i["dtype"]), i["len"], i["offset"]) for k, i in v["binario"].items()}
    inicio = col["inicio"]
    t = acumular(col["t"].astype(np.int64), inicio)
    xy = acumular(col["xy"].reshape(-1, 2).astype(np.int64), inicio) / 10
    return raw, col, inicio, t, xy


def posiciones(inicio, t, xy, T):
    """Posición interpolada en `T` de cada tramo activo en `T`, ordenadas (el visor no sabe ids)."""
    res = []
    for a, b in pairwise(inicio):
        if t[a] <= T <= t[b - 1]:
            res.append((np.interp(T, t[a:b], xy[a:b, 0]), np.interp(T, t[a:b], xy[a:b, 1])))
    return np.array(sorted(res))


@pytest.fixture(scope="module")
def export(grilla, tmp_path_factory):
    dest = tmp_path_factory.mktemp("viz")
    # out_temporal es por test y esta fixture es del módulo: otro temporal a mano
    out_previo, rutas.OUT = rutas.OUT, dest / "out"
    try:
        meta, tam = exportar(grilla.con(nombre="on", backend="traci", fluidez=300), dest=dest, ventana_s=300)
    finally:
        rutas.OUT = out_previo
    return dest, meta, tam


def test_meta_y_ventanas(export):
    dest, meta, tam = export
    assert json.loads((dest / "on" / "meta.json").read_text()) == meta
    assert meta["ventana_s"] == 300 and meta["politica"] == "on"
    assert "periodos" not in meta["metricas"]
    assert [p["t0"] for p in meta["periodos"]] == [0, 300, 600]
    assert all(p["decisiones"] and all(p["decisiones"].values()) and p["resto"] for p in meta["periodos"])
    assert set(meta["periodos"][0]["corredores"]) == {"fila-1", "fila-2", "columna-b", "columna-c"}  # ids
    assert [(v["t0"], v["t1"], v["archivo"]) for v in meta["ventanas"]] == \
        [(300 * k, 300 * (k + 1), f"on/{k:04d}.bin") for k in range(len(meta["ventanas"]))]
    assert len(meta["ventanas"]) >= 3
    assert sum(v["bytes"] for v in meta["ventanas"]) == tam
    assert meta["puntos"] < meta["puntos_crudos"]
    for v in meta["ventanas"]:
        raw, col, inicio, t, xy = leer_ventana(dest, v)
        assert len(raw) == v["bytes"] and hashlib.sha256(raw).hexdigest() == v["sha256"]
        assert all(i["offset"] % 4 == 0 for i in v["binario"].values())  # TypedArray sin copiar
        assert inicio[0] == 0 and inicio[-1] == len(col["t"]) == v["puntos"]
        assert len(col["tipo"]) == v["tramos"] == len(inicio) - 1
        assert (np.diff(inicio) >= 2).all()  # cada tramo con al menos sus extremos
        assert len(col["xy"]) == 2 * len(col["t"]) == 2 * len(col["v"])
        for a, b in pairwise(inicio):
            assert (np.diff(t[a:b]) > 0).all()
            assert t[a] <= v["t1"] and t[b - 1] >= v["t0"]  # se cruza con la ventana
        assert np.abs(xy).max() < 1e4  # metros razonables, no basura de la reconstrucción


def test_continuidad_entre_ventanas(export):
    """En el borde T, los vehículos (y dónde están) son los mismos vistos desde las dos ventanas."""
    dest, meta, _ = export
    vs = [leer_ventana(dest, v) for v in meta["ventanas"]]
    for k in range(len(vs) - 1):
        T = meta["ventanas"][k]["t1"]
        antes, despues = posiciones(*vs[k][2:], T), posiciones(*vs[k + 1][2:], T)
        assert len(antes) > 0
        assert antes.shape == despues.shape and np.allclose(antes, despues), T


def test_manifest(export):
    dest, _, _ = export
    (dest / "viejo").mkdir()
    (dest / "viejo" / "meta.json").write_text("{}")
    escribir_manifest(dest, ["viejo"])
    (dest / "borrado").mkdir()
    (dest / "borrado" / "meta.json").write_text("{}")
    escribir_manifest(dest, ["borrado"])
    (dest / "borrado" / "meta.json").unlink()  # ya no está exportado: sale del manifest
    m = escribir_manifest(dest, ["on"])
    assert m == json.loads((dest / "manifest.json").read_text())
    assert {k: m[k] for k in ("version", "red", "escena", "terreno")} == \
        {"version": 1, "red": "red.json", "escena": "escena.json", "terreno": "terreno.bin"}
    assert m["escenarios"] == [{"id": "on", "titulo": "Semáforos encendidos", "meta": "on/meta.json"},
                               {"id": "viejo", "titulo": "viejo", "meta": "viejo/meta.json"}]


def test_red_con_corredores(grilla):
    r = red(sumolib.net.readNet(str(grilla.net)), grilla.corredores)
    calles = [c["id"] for c in r["calles"]]
    corr = {c["id"]: c for c in r["corredores"]}
    assert r["origen"] is None  # netgenerate: sin proyección
    assert list(corr) == ["fila-1", "fila-2", "columna-b", "columna-c"]
    assert sorted(calles[i] for i in corr["fila-1"]["calles"]) == ["A1B1", "B1A1", "B1C1", "C1B1",
                                                                  "C1D1", "D1C1"]
    assert corr["fila-1"]["semaforos"] == ["A1", "B1", "C1", "D1"]
    assert set(corr["fila-1"]["semaforos"]) & set(corr["columna-b"]["semaforos"]) == {"B1"}


def test_ventana_incluye_vecinos_y_tramos_sin_puntos_dentro():
    tramo = np.array([0, 0, 0, 0, 1, 1, 2, 2, 3, 3])
    t = np.array([0, 50, 120, 300, 10, 500, 210, 220, 0, 90])
    keep = ventana(t, tramo, 100, 200)
    # tramo 0: el anterior a 100 (50), el de adentro (120) y el posterior a 200 (300)
    # tramo 1: ningún punto dentro pero activo: sus dos extremos
    # tramo 2: empieza después; tramo 3: termina antes
    assert keep.tolist() == [False, True, True, True, True, True, False, False, False, False]


def test_diferencias_ida_y_vuelta():
    rng = np.random.default_rng(0)
    inicio = np.array([0, 3, 3, 10, 12], np.uint32)  # incluye un vehículo vacío
    a = rng.integers(-1000, 1000, (12, 2))
    assert (acumular(diferencias(a, inicio), inicio) == a).all()
    assert (acumular(diferencias(a[:, 0], inicio), inicio) == a[:, 0]).all()
