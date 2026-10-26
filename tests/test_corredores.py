import json
import subprocess

import pytest
import sumolib

from open_jam import corredores
from open_jam.demanda import ESTACIONES, misma_calle


@pytest.fixture(scope="module")
def avenida(tmp_path_factory):
    """Una avenida recta de 6 km (doble sentido, nodos cada 500 m) cruzada por calles y una
    paralela que se llama casi igual."""
    d = tmp_path_factory.mktemp("avenida")
    nodos = [f'<node id="a{k}" x="{k * 500}" y="0" type="priority"/>' for k in range(13)]
    nodos += [f'<node id="c{k}" x="{k * 500}" y="300"/>' for k in range(13)]
    nodos += ['<node id="p0" x="0" y="-300"/>', '<node id="p1" x="6000" y="-300"/>']
    tramos = []
    for k in range(12):
        tramos.append(f'<edge id="av{k}" from="a{k}" to="a{k + 1}" name="Avenida Prueba" numLanes="2"/>')
        tramos.append(f'<edge id="-av{k}" from="a{k + 1}" to="a{k}" name="Avenida Prueba" numLanes="2"/>')
    for k in range(13):
        tramos.append(f'<edge id="cr{k}" from="c{k}" to="a{k}" name="Calle {k}"/>')
    tramos.append('<edge id="par" from="p0" to="p1" name="Avenida Prueba A"/>')
    (d / "n.nod.xml").write_text("<nodes>" + "".join(nodos) + "</nodes>")
    (d / "n.edg.xml").write_text("<edges>" + "".join(tramos) + "</edges>")
    net = d / "n.net.xml"
    subprocess.run(["netconvert", "-n", d / "n.nod.xml", "-e", d / "n.edg.xml", "-o", net],
                   check=True, capture_output=True)
    n = sumolib.net.readNet(str(net))
    n.convertLonLat2XY = lambda lon, lat: (lon, lat)  # estaciones en x, y de la red: sin proyección
    return n


def test_misma_calle():
    assert misma_calle("Avenida Reforma", "Carril Auxiliar Avenida Reforma")
    assert misma_calle("Bulevar San Cristóbal", "Boulevard San Cristóbal")
    assert not misma_calle("6a Avenida", "6a Avenida A")
    assert not misma_calle("Carretera a El Salvador", "Antigua Carretera a El Salvador")


def test_generar_parte_la_avenida_entre_estaciones(avenida):
    # (etiqueta, calle, "lat" = y, "lon" = x, veh/día): dos estaciones a 2.5 km
    est = [("Prueba oeste", "Avenida Prueba", 0, 1000, 1), ("Prueba este", "Avenida Prueba", 0, 3500, 1)]
    oeste, este = corredores.generar(avenida, est, largo_m=800)
    assert (oeste["id"], este["id"]) == ("prueba-oeste", "prueba-este")
    assert not set(oeste["tramos"]) & set(este["tramos"])
    # cada tramo a la estación más cercana por la calle; el corte cae a mitad de camino (2250 m)
    assert {"av0", "-av0", "av3", "-av3"} <= set(oeste["tramos"])
    assert {"av5", "-av5", "av6", "-av6"} <= set(este["tramos"])
    # acotado: hasta 800 m de los tramos de la estación (av6 y av7, de 3000 a 4000 m): av9 empieza
    # a 500 m de ellos y entra; av10, a casi 1000 m (netconvert recorta los cruces), queda afuera
    assert "av9" in este["tramos"] and "av10" not in este["tramos"]
    # ni calles transversales ni la paralela que se llama parecido
    todos = set(oeste["tramos"]) | set(este["tramos"])
    assert not {t for t in todos if t.startswith("cr")} and "par" not in todos


def test_generar_es_determinista(avenida):
    est = [("Prueba", "Avenida Prueba", 0, 3000, 1)]
    assert corredores.generar(avenida, est) == corredores.generar(avenida, est)


def test_con_semaforos_deriva_de_los_tramos():
    lista = [{"id": "a", "nombre": "A", "tramos": ["e1", "e2"]}, {"id": "b", "nombre": "B", "tramos": ["e3"]}]
    corr = corredores.con_semaforos(lista, {"s1": {"e1", "x"}, "s2": {"e2", "e3"}, "s3": {"x"}})
    assert corr["a"]["semaforos"] == ["s1", "s2"]
    assert corr["b"]["semaforos"] == ["s2"]


def test_cargar_falla_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="open_jam.corredores"):
        corredores.cargar(tmp_path / "no.json")
    rep = tmp_path / "rep.json"
    rep.write_text(json.dumps({"corredores": [{"id": "a", "tramos": []}, {"id": "a", "tramos": []}]}))
    with pytest.raises(ValueError, match="repetidos"):
        corredores.cargar(rep)


def test_archivo_versionado():
    """data/corredores.json: un corredor por estación, acotados y sin tramos repetidos."""
    lista = corredores.cargar()
    assert [c["id"] for c in lista] == [corredores.slug(e[0]) for e in ESTACIONES]
    vistos = {}
    for c in lista:
        assert c["tramos"], c["id"]
        assert len(c["tramos"]) < 150, c["id"]  # antes "6a Avenida" juntaba ~1000 tramos de todas las zonas
        for e in c["tramos"]:
            assert e not in vistos, (e, c["id"], vistos.get(e))
            vistos[e] = c["id"]
    ids = {c["id"] for c in lista}
    assert {"periferico", "periferico-norte", "periferico-sur", "roosevelt", "roosevelt-mixco"} <= ids


def test_corredores_de_la_grilla_en_sumo(grilla):
    import traci

    traci.start(grilla.con(salidas=False, fluidez=0).args())
    try:
        corr = corredores.corredores(traci, grilla.corredores)
    finally:
        traci.close()
    assert corr["fila-1"]["semaforos"] == ["A1", "B1", "C1", "D1"]
    assert corr["columna-b"]["semaforos"] == ["B0", "B1", "B2", "B3"]


def test_corredores_de_otra_red_fallan(grilla, tmp_path):
    import traci

    otra = tmp_path / "otra.json"
    otra.write_text(json.dumps({"corredores": [{"id": "x", "nombre": "x", "tramos": ["no-existe"]}]}))
    traci.start(grilla.con(salidas=False, fluidez=0).args())
    try:
        with pytest.raises(ValueError, match="no están en la red"):
            corredores.corredores(traci, otra)
    finally:
        traci.close()
