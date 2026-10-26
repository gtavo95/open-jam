import io
import json
import urllib.error

import pytest

from open_jam import ab, rutas
from open_jam.muse import ControladorMuse, ErrorMuse, Muse


def respuesta(texto, estado="completed"):
    return {"status": estado, "usage": {"input_tokens": 10, "output_tokens": 5},
            "output": [{"type": "reasoning", "content": []},
                       {"type": "message", "content": [{"type": "output_text", "text": texto}]}]}


def http(codigo):
    return urllib.error.HTTPError("u", codigo, "x", {}, io.BytesIO(b'{"error": "x"}'))


def test_cuerpo_y_texto():
    vistos = []

    def post(url, cuerpo, clave, timeout):
        vistos.append((url, cuerpo, clave))
        return respuesta('{"a": 1}')

    m = Muse(modelo="muse-spark-1.3", clave="k", post=post)
    assert m.responder("ins", "in", {"type": "json_schema"}) == '{"a": 1}'
    url, cuerpo, clave = vistos[0]
    assert url == "https://api.meta.ai/v1/responses" and clave == "k"
    assert cuerpo["model"] == "muse-spark-1.3" and cuerpo["instructions"] == "ins" and cuerpo["input"] == "in"
    assert cuerpo["text"] == {"format": {"type": "json_schema"}} and cuerpo["store"] is False
    assert (m.llamadas, m.tokens_in, m.tokens_out) == (1, 10, 5)


def test_reintenta_429_y_no_400(monkeypatch):
    monkeypatch.setattr("open_jam.muse.time.sleep", lambda s: None)
    errores = [http(429), http(503)]

    def post(*a):
        if errores:
            raise errores.pop(0)
        return respuesta("ok")

    assert Muse(clave="k", post=post).responder("i", "x") == "ok"

    def malo(*a):
        raise http(400)

    with pytest.raises(ErrorMuse, match="HTTP 400"):
        Muse(clave="k", post=malo).responder("i", "x")
    with pytest.raises(ErrorMuse, match="MODEL_API_KEY"):
        Muse(clave="").responder("i", "x")
    with pytest.raises(ErrorMuse, match="incomplete"):
        Muse(clave="k", post=lambda *a: respuesta("x", "incomplete")).responder("i", "x")


class FalsoMuse(Muse):
    """Responde con lo que se le indique, mirando el estado que recibe."""

    def __init__(self, hacer):
        super().__init__(clave="k")
        self.hacer, self.vistos = hacer, []

    def responder(self, instrucciones, entrada, formato=None):
        estado = json.loads(entrada)
        self.vistos.append(estado)
        return json.dumps(self.hacer(estado))


def test_controlador_valida_lo_que_dice_el_modelo(grilla, monkeypatch):
    base = ab.BASE.con(net=grilla.net, adicionales=grilla.adicionales, rutas=grilla.rutas)
    caso = ab.Caso(seed=1, escala=1.0, t0=300, dur=300)

    def bueno(estado):
        s = estado["semaforos"][0]
        nodos = [{"tls": s["tls"], "verdes": [20.0] * len(s["webster"])},
                 {"tls": s["tls"], "verdes": [999.0] * len(s["webster"])},  # fuera de rango
                 {"tls": "inventado", "verdes": [20.0]}]
        return {"nodos": nodos}

    ctrl = ControladorMuse(cada=60, muse=FalsoMuse(bueno))
    monkeypatch.setattr(ab, "crear", lambda nombre: ctrl)
    ab.preparar(base, [caso], rutas.OUT)
    fila = ab.tramo(base, caso, "muse", rutas.OUT)
    assert ctrl.muse.vistos and ctrl.muse.vistos[0]["semaforos"]
    assert fila["cambios"] > 0 and fila["invalidos"] >= 2 and fila["fallos"] == 0
    assert fila["llamadas"] == 0  # el falso no pasa por el cliente HTTP


def test_fallo_del_modelo_no_corta_la_simulacion(grilla, monkeypatch):
    base = ab.BASE.con(net=grilla.net, adicionales=grilla.adicionales, rutas=grilla.rutas)
    caso = ab.Caso(seed=1, escala=1.0, t0=300, dur=180)

    class Roto(Muse):
        def responder(self, *a, **k):
            raise ErrorMuse("sin red")

    ctrl = ControladorMuse(cada=60, muse=Roto(clave="k"))
    monkeypatch.setattr(ab, "crear", lambda nombre: ctrl)
    ab.preparar(base, [caso], rutas.OUT)
    fila = ab.tramo(base, caso, "muse", rutas.OUT)
    assert fila["fallos"] >= 1 and fila["cambios"] == 0 and fila["error"] == "sin red"
    assert fila["llegaron"] > 0
