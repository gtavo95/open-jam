"""Puntos de control: una corrida cortada retoma donde quedó y da (casi) lo mismo que seguida."""

from test_sim import correr_aparte, resultado

from open_jam import rutas


def test_tramos_dan_lo_mismo_que_seguida(grilla):
    seguida = correr_aparte(grilla.con(nombre="t-seg", fluidez=300))
    tramos = correr_aparte(grilla.con(nombre="t-tramos", fluidez=300, control_s=300))
    print(resultado(seguida), resultado(tramos), sep="\n")
    assert tramos["insertados"] == seguida["insertados"]
    assert [p["t0"] for p in tramos["periodos"]] == [p["t0"] for p in seguida["periodos"]] == [0, 300, 600]
    assert abs(tramos["llegaron"] - seguida["llegaron"]) <= 0.03 * seguida["llegaron"]
    assert abs(tramos["viaje_prom_s"] - seguida["viaje_prom_s"]) <= 0.05 * seguida["viaje_prom_s"]
    assert sorted(p.name for p in (rutas.OUT / "t-tramos.control").glob("*.stats.xml")) == [
        "00000.stats.xml", "00300.stats.xml", "00600.stats.xml"]


def test_retoma_desde_el_ultimo_punto(grilla):
    c = grilla.con(nombre="t-corte", fluidez=300, control_s=300, politica="off")
    corta = correr_aparte(c.con(hasta=600))  # como si se hubiera cortado a los 600 s
    assert "retomada_en" not in corta
    larga = correr_aparte(c)
    entera = correr_aparte(c.con(nombre="t-entera"))
    assert larga["retomada_en"] == 300  # el último punto antes de 600 (en 600 terminó, no guardó)
    assert [p["t0"] for p in larga["periodos"]] == [0, 300, 600]
    assert all(p["decisiones"] and not any(p["decisiones"].values()) for p in larga["periodos"])
    assert resultado(larga) | {"retomada_en": 0} == resultado(entera) | {"retomada_en": 0}


def test_otra_configuracion_no_retoma(grilla):
    c = grilla.con(nombre="t-otra", fluidez=300, control_s=300)
    correr_aparte(c.con(hasta=600))
    assert "retomada_en" not in correr_aparte(c.con(seed=7))


def test_terminada_no_vuelve_a_simular(grilla):
    c = grilla.con(nombre="t-fin", fluidez=300, control_s=300)
    primera = correr_aparte(c)
    carpeta = rutas.OUT / "t-fin.control"
    assert (carpeta / "fin.json").exists()
    for f in carpeta.glob("*.estado.xml.gz"):  # sin estados, solo podría devolver lo guardado
        f.unlink()
    assert correr_aparte(c) == primera  # los tiempos de pared también: no corrió de nuevo
    otra = correr_aparte(c.con(hasta=600))  # otro horizonte: corre de cero
    assert otra["pared_s"] != primera["pared_s"] and "retomada_en" not in otra
