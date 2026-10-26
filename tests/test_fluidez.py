from open_jam.fluidez import Fluidez

CORR = {"a": {"tramos": ["e1", "e2"]}, "b": {"tramos": ["e2"]}}  # e2 es de los dos

P0 = ('<interval begin="0.00" end="900.00" id="fluidez">\n'
      '<edge id="e1" sampledSeconds="100.00" waitingTime="10.00"/>\n'
      '<edge id="e2" sampledSeconds="50.00" waitingTime="50.00"/>\n'
      '<edge id="e3" sampledSeconds="50.00"/>\n'
      '</interval>\n')
P1 = ('<interval begin="900.00" end="1800.00" id="fluidez">\n'
      '<edge id="e1" sampledSeconds="200.00" waitingTime="0.00"/>\n'
      '</interval>\n')


def test_lee_lo_que_sumo_va_escribiendo(tmp_path):
    salida = tmp_path / "f.xml"
    fl = Fluidez(salida, CORR, 900)
    assert fl.ultimo() is None  # SUMO todavía no creó el archivo
    cabeza = '<?xml version="1.0"?>\n<meandata>\n'
    corte = P1.index("waitingTime")  # SUMO cortado a mitad de un tramo del segundo periodo
    salida.write_text(cabeza + P0 + P1[:corte])
    u = fl.ultimo()
    assert (u["t0"], u["t1"]) == (0, 900)
    assert u["red"] == {"parado_h": 0.0, "fluidez": round(1 - 60 / 200, 3)}
    assert u["corredores"]["a"]["fluidez"] == round(1 - 60 / 150, 3)
    assert u["corredores"]["b"]["fluidez"] == 0.0
    assert len(fl.periodos) == 1
    with open(salida, "a") as f:
        f.write(P1[corte:] + "</meandata>\n")
    u = fl.ultimo()
    assert (u["t0"], u["t1"]) == (900, 1800)
    assert u["corredores"]["b"]["fluidez"] is None  # nadie pasó por e2: sin dato, no "fluido"
    assert len(fl.periodos) == 2  # el primero no se contó dos veces
    fl.leer()
    assert len(fl.periodos) == 2
    r = fl.resumen()
    assert (r["t0"], r["t1"]) == (0, 1800)
    assert r["red"]["fluidez"] == round(1 - 60 / 400, 3)
    assert r["corredores"]["a"]["fluidez"] == round(1 - 60 / 350, 3)
