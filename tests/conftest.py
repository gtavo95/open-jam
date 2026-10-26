"""Red y demanda chiquitas (cuadrícula 4x4 con semáforos) para que los tests corran en segundos."""

import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest
import sumo

from open_jam import rutas
from open_jam.config import Corrida

TOOLS = Path(sumo.SUMO_HOME) / "tools"


def calles_grilla(fila=None, columna=None):
    """Tramos de una fila (dígito) o columna (letra) de la cuadrícula de netgenerate, en los dos sentidos."""
    letras = "ABCD"
    if fila is not None:
        pares = [(f"{a}{fila}", f"{b}{fila}") for a, b in pairwise(letras)]
    else:
        pares = [(f"{columna}{k}", f"{columna}{k + 1}") for k in range(3)]
    return sorted(e for a, b in pares for e in (a + b, b + a))


# Dos filas y dos columnas: se cruzan en B1, B2, C1 y C2, semáforos compartidos.
CORREDORES_GRILLA = {"fila-1": calles_grilla(fila=1), "fila-2": calles_grilla(fila=2),
                     "columna-b": calles_grilla(columna="B"), "columna-c": calles_grilla(columna="C")}


@pytest.fixture(scope="session")
def grilla(tmp_path_factory):
    d = tmp_path_factory.mktemp("grilla")
    net, rou, tls = d / "g.net.xml", d / "g.rou.xml", d / "tls.add.xml"
    subprocess.run(["netgenerate", "--grid", "--grid.number", "4", "--grid.length", "200",
                    "--default.lanenumber", "2", "--tls.guess", "true", "-o", net],
                   check=True, capture_output=True)
    subprocess.run([sys.executable, TOOLS / "randomTrips.py", "-n", net, "-r", rou, "-o", d / "g.trips.xml",
                    "-e", "600", "-p", "0.8", "--seed", "1", "--validate"], check=True, capture_output=True)
    subprocess.run([sys.executable, TOOLS / "tlsCycleAdaptation.py", "-n", net, "-r", rou, "-o", tls, "-p", "w"],
                   check=True, capture_output=True)
    corr = d / "corredores.json"
    corr.write_text(json.dumps({"corredores": [{"id": k, "nombre": k, "tramos": v}
                                               for k, v in CORREDORES_GRILLA.items()]}))
    return Corrida("test", hasta=900, net=net, adicionales=(tls,), rutas=(rou,), corredores=corr)


@pytest.fixture(autouse=True)
def out_temporal(tmp_path, monkeypatch):
    """Las salidas de SUMO de cada test a un directorio temporal, no a out/."""
    out = tmp_path / "out"
    monkeypatch.setattr(rutas, "OUT", out)
    return out
