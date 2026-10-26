import json

import pytest

from open_jam.politicas import (
    PROGRAMA_APAGADO,
    PROGRAMA_ENCENDIDO,
    Agente,
    Politica,
    aplicar_corredores,
    estado_semaforos,
    politica,
    validar,
)
from open_jam.sim import correr

CORR = {"a": {"semaforos": ["s1", "s2"]}, "b": {"semaforos": ["s2", "s3"]}}  # s2: cruce de a y b


class SumoFalso:
    """Lo mínimo de `trafficlight` para ver qué programas se ponen, sin SUMO."""

    def __init__(self, tls):
        self.programas = dict.fromkeys(tls, PROGRAMA_ENCENDIDO)
        self.cambios = []
        self.trafficlight = self

    def getProgram(self, tls):
        return self.programas[tls]

    def setProgram(self, tls, programa):
        self.programas[tls] = programa
        self.cambios.append(tls)


def test_semaforo_compartido_se_apaga_solo_si_todos_sus_corredores_lo_apagan():
    assert estado_semaforos(CORR, {"a": False, "b": True}) == {"s1": False, "s2": True, "s3": True}
    assert estado_semaforos(CORR, {"a": True, "b": False}) == {"s1": True, "s2": True, "s3": False}
    assert estado_semaforos(CORR, {"a": False, "b": False}) == dict.fromkeys(("s1", "s2", "s3"), False)


def test_aplicar_corredores_solo_toca_los_que_cambian():
    s = SumoFalso(["s1", "s2", "s3", "s4"])
    aplicar_corredores(s, CORR, {"a": False, "b": True})
    assert s.programas == {"s1": PROGRAMA_APAGADO, "s2": PROGRAMA_ENCENDIDO, "s3": PROGRAMA_ENCENDIDO,
                           "s4": PROGRAMA_ENCENDIDO}
    assert s.cambios == ["s1"]  # s2 y s3 ya estaban encendidos: no se reinicia su ciclo; s4 no es de nadie


def test_validar_rechaza_lo_que_no_es_dict():
    with pytest.raises(TypeError, match="dict"):
        validar(["a"], CORR)


@pytest.mark.parametrize("mala, motivo", [
    ({"zzz": True}, "desconocidos"),
    ({"a": 1}, "true/false"),
    ({"a": "true"}, "true/false"),
])
def test_validar_rechaza(mala, motivo):
    with pytest.raises(ValueError, match=motivo):
        validar(mala, CORR)


def test_validar_acepta_parcial():
    assert validar({"b": False}, CORR) == {"b": False}


def test_politica_por_nombre_u_objeto():
    a = Agente()
    assert politica(a) is a
    assert politica("agente").nombre == "agente"
    assert politica("off").nombre == "off"
    with pytest.raises(ValueError):
        politica("lunes")


class Alterna(Politica):
    """Prende las filas en los periodos pares y las columnas en los impares; guarda lo que ve."""

    def __init__(self, cada):
        self.cada = cada
        self.vistas = []
        self.programas = []

    def decidir(self, obs):
        self.vistas.append(json.loads(json.dumps(obs)))  # la observación tiene que viajar como JSON
        filas = obs["periodo"] % 2 == 0
        return {c: c.startswith("fila") == filas for c in obs["decision_anterior"]}

    def aplicar(self, sumo, corr, estado):
        super().aplicar(sumo, corr, estado)
        self.programas.append({tls: sumo.trafficlight.getProgram(tls) for c in corr for tls in corr[c]["semaforos"]})
        self.corr = corr


def test_politica_alterna_corredores_de_punta_a_punta(grilla):
    # TraCI y no libsumo: así la política corre en este proceso y se puede revisar después.
    p = Alterna(cada=300)
    r = correr(grilla.con(nombre="t-alterna", backend="traci", politica=p, fluidez=300))
    assert len(r["periodos"]) >= 2
    for k, per in enumerate(r["periodos"]):
        assert per["t0"] == 300 * k and per["t1"] == 300 * (k + 1)
        assert per["decisiones"] == {c: c.startswith("fila") == (k % 2 == 0) for c in per["corredores"]}
    # la primera decisión no tiene periodo anterior; las demás ven el que acaba de cerrar
    assert p.vistas[0]["ultimo"] is None and p.vistas[0]["corredores"]["fila-1"]["fluidez"] is None
    assert p.vistas[0]["decision_anterior"] == dict.fromkeys(r["corredores"], True)
    for k, obs in enumerate(p.vistas[1:], 1):
        assert obs["ultimo"] == {"t0": 300 * (k - 1), "t1": 300 * k}
        assert obs["corredores"] == r["periodos"][k - 1]["corredores"]
        assert obs["decision_anterior"] == r["periodos"][k - 1]["decisiones"]
    # en SUMO: un cruce entre una fila y una columna siempre queda encendido (uno de los dos lo está)
    compartidos = set(p.corr["fila-1"]["semaforos"]) & set(p.corr["columna-b"]["semaforos"])
    assert compartidos
    for k, programas in enumerate(p.programas):
        prendidos = [c for c in p.corr if c.startswith("fila") == (k % 2 == 0)]
        for tls, prog in programas.items():
            de_alguno_prendido = any(tls in p.corr[c]["semaforos"] for c in prendidos)
            assert prog == (PROGRAMA_ENCENDIDO if de_alguno_prendido else PROGRAMA_APAGADO), (k, tls)
        assert all(programas[t] == PROGRAMA_ENCENDIDO for t in compartidos)


def test_agente_de_ejemplo(grilla):
    a = Agente(umbral=0.85, cada=300)
    r = correr(grilla.con(nombre="t-agente", backend="traci", politica=a, fluidez=300))
    assert r["periodos"][0]["decisiones"] == dict.fromkeys(r["corredores"], True)  # sin datos: Webster
    for antes, ahora in zip(r["periodos"], r["periodos"][1:]):
        for c, m in antes["corredores"].items():
            esperado = antes["decisiones"][c] if m["fluidez"] is None else m["fluidez"] < 0.85
            assert ahora["decisiones"][c] == esperado
    assert {v for p in r["periodos"] for v in p["decisiones"].values()} == {True, False}  # no es trivial
    assert all(p["resto"] for p in r["periodos"])  # lo de fuera de corredores sigue con Webster


class Rota(Politica):
    cada = 300

    def decidir(self, obs):
        return {"no-existe": True}


def test_decision_invalida_cierra_sumo(grilla):
    with pytest.raises(ValueError, match="desconocidos"):
        correr(grilla.con(nombre="t-rota", backend="traci", politica=Rota()))
    # si SUMO hubiera quedado abierto, TraCI no dejaría arrancar otra simulación
    r = correr(grilla.con(nombre="t-despues", backend="traci", hasta=60, fluidez=0))
    assert r["fin_s"] == 60
