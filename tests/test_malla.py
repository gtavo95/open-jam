import multiprocessing as mp

import numpy as np
import pytest
import sumolib

from open_jam import tiempos
from open_jam.malla import Malla


@pytest.fixture(scope="module")
def malla(grilla):
    return Malla.desde_net(sumolib.net.readNet(str(grilla.net)))


def test_matrices_de_la_grilla(grilla, malla):
    net = sumolib.net.readNet(str(grilla.net))
    tls = {t.getID() for t in net.getTrafficLights()}
    assert set(malla.nodos) == tls
    n, m = len(malla.nodos), len(malla.tramos)
    assert malla.entra.shape == malla.sale.shape == malla.llega.shape == (n, m)
    assert malla.vecinos.shape == (n, n) and malla.vecinos.diagonal().sum() == 0
    i = {x: k for k, x in enumerate(malla.nodos)}
    # dos semáforos unidos por una calle son vecinos en el sentido de la calle
    directos = [(e.getFromNode().getID(), e.getToNode().getID()) for e in net.getEdges()
                if e.getFromNode().getID() in tls and e.getToNode().getID() in tls]
    assert directos
    assert all(malla.vecinos[i[a], i[b]] for a, b in directos)
    # B @ 1: tramos que entran menos los que salen
    np.testing.assert_array_equal(malla.B @ np.ones(m), malla.entra.sum(axis=1) - malla.sale.sum(axis=1))


def test_entre_nodos(malla):
    x = np.arange(len(malla.tramos), dtype=float) + 1
    f = malla.entre_nodos(x)
    assert f.shape == (len(malla.nodos),) * 2
    assert (f.toarray() > 0).astype(int).tolist() == malla.vecinos.toarray().tolist()
    llega, entra = malla.llega.toarray(), malla.entra.toarray()
    for i, j in zip(*f.nonzero(), strict=True):
        assert f[i, j] == x[(llega[i] > 0) & (entra[j] > 0)].sum()


def _en_vivo(c, malla, cola):
    import libsumo as sumo

    sumo.start(c.args())
    try:
        sumo.simulationStep(120)
        lectura = malla.leer(sumo)
        tls = malla.nodos[0]
        antes = tiempos.fases(sumo, tls)
        errores = []
        for malo in (["x"], [1.0] * 9, [1.0] * len(tiempos.verdes(sumo, tls)), "30"):
            try:
                tiempos.fijar(sumo, tls, malo)
            except (TypeError, ValueError) as e:
                errores.append(str(e))
        fase, cambio = sumo.trafficlight.getPhase(tls), sumo.trafficlight.getNextSwitch(tls)
        nuevos = [40.0 + 5 * k for k in range(len(tiempos.verdes(sumo, tls)))]
        tiempos.fijar(sumo, tls, nuevos)
        sigue = (sumo.trafficlight.getPhase(tls), sumo.trafficlight.getNextSwitch(tls)) == (fase, cambio)
        cambios, ultima = [], (sumo.simulation.getTime(), fase)
        while len(cambios) < len(antes) + 1:
            sumo.simulationStep()
            t, f = sumo.simulation.getTime(), sumo.trafficlight.getPhase(tls)
            if f != ultima[1]:
                cambios.append((ultima[1], t - ultima[0]))
                ultima = (t, f)
        sumo.trafficlight.setProgram(tls, "off")
        try:
            tiempos.fijar(sumo, tls, nuevos)
        except ValueError as e:
            errores.append(str(e))
        cola.put({"lectura": lectura, "antes": antes, "despues": tiempos.fases(sumo, tls), "nuevos": nuevos,
                  "errores": errores, "sigue": sigue, "cambios": cambios[1:]})  # el primero es la fase que ya corría
    finally:
        sumo.close()


def test_lectura_y_tiempos(grilla, malla):
    ctx = mp.get_context("spawn")
    cola = ctx.Queue()
    p = ctx.Process(target=_en_vivo, args=(grilla.con(fluidez=0, salidas=False), malla, cola))
    p.start()
    r = cola.get(timeout=120)
    p.join()

    lec = r["lectura"]
    assert lec.vehiculos.sum() > 0 and (lec.flujo >= 0).all()
    assert (lec.parados <= lec.vehiculos).all()

    assert len(r["errores"]) == 5
    assert "desconocido" not in " ".join(r["errores"])
    assert r["sigue"]  # la fase en curso termina cuando iba a terminar
    verdes = iter(r["nuevos"])
    for a, d in zip(r["antes"], r["despues"], strict=True):
        assert a["estado"] == d["estado"]
        assert d["duracion"] == (next(verdes) if a["verde"] else a["duracion"])  # amarillos y rojos intactos
    # el ciclo corre con los tiempos nuevos
    for fase, dur in r["cambios"]:
        assert dur == r["despues"][fase]["duracion"]
