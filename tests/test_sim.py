import multiprocessing as mp

import pytest

from open_jam import rutas
from open_jam.sim import correr


def _en_proceso(c, out, cola):
    rutas.OUT = out  # el monkeypatch de conftest no llega al proceso nuevo
    cola.put(correr(c))


def correr_aparte(c):
    """libsumo admite una sola simulación por proceso; cada test corre la suya aparte."""
    ctx = mp.get_context("spawn")
    cola = ctx.Queue()
    p = ctx.Process(target=_en_proceso, args=(c, rutas.OUT, cola))
    p.start()
    r = cola.get(timeout=300)
    p.join()
    return r


SIN_TIEMPOS = ("carga_s", "sim_s", "pared_s", "factor_tiempo_real", "fin_s")


def resultado(r):
    return {k: v for k, v in r.items() if k not in SIN_TIEMPOS and k != "escenario"}


def test_on_termina(grilla):
    r = correr_aparte(grilla.con(nombre="t-on"))
    assert r["insertados"] > 300
    assert r["sin_terminar"] == 0


def test_libsumo_y_traci_dan_lo_mismo(grilla):
    a = correr_aparte(grilla.con(nombre="t-lib", backend="libsumo"))
    b = correr_aparte(grilla.con(nombre="t-traci", backend="traci"))
    assert resultado(a) == resultado(b)


def test_por_paso_no_cambia_el_resultado(grilla):
    a = correr_aparte(grilla.con(nombre="t-salto"))
    b = correr_aparte(grilla.con(nombre="t-paso", por_paso=True))
    assert resultado(a) == resultado(b)


def test_hilos_son_deterministas(grilla):
    a = correr_aparte(grilla.con(nombre="t-h1", threads=1))
    b = correr_aparte(grilla.con(nombre="t-h4", threads=4))
    assert resultado(a) == resultado(b)


@pytest.mark.parametrize("meso", [False, True])
def test_off_cambia_algo(grilla, meso):
    on = correr_aparte(grilla.con(nombre=f"t-on-{meso}", meso=meso))
    off = correr_aparte(grilla.con(nombre=f"t-off-{meso}", meso=meso, politica="off"))
    assert on["insertados"] == off["insertados"]
    assert on["demora_prom_s"] != off["demora_prom_s"]


def test_fluidez(grilla):
    on = correr_aparte(grilla.con(nombre="t-fl-on"))
    off = correr_aparte(grilla.con(nombre="t-fl-off", politica="off"))
    sin = correr_aparte(grilla.con(nombre="t-fl-sin", fluidez=0))
    for r, encendido in ((on, True), (off, False)):
        assert 0 < r["fluidez"] < 1 and r["parado_h"] > 0
        assert [p["t0"] for p in r["periodos"]] == [0]  # 900 s de grilla: un periodo de 15 min
        assert set(r["corredores"]) == {"fila-1", "fila-2", "columna-b", "columna-c"}
        # las fijas registran todos los corredores encendidos o todos apagados
        assert r["periodos"][0]["decisiones"] == dict.fromkeys(r["corredores"], encendido)
        assert r["periodos"][0]["resto"] is encendido  # "off" apaga también los de fuera de corredores
    assert on["parado_h"] != off["parado_h"]
    assert "fluidez" not in sin
    assert resultado(sin) == {k: v for k, v in resultado(on).items()
                              if k not in ("fluidez", "parado_h", "corredores", "periodos")}


def test_landmarks_solo_en_la_red_real(grilla):
    # Son tramos de la red real: en otra red SUMO no arranca.
    assert "--astar.landmark-distances" not in grilla.args()
