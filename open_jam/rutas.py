import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "sim"
# En la nube (nube/tarea.py) las salidas van a otro disco.
OUT = Path(os.environ.get("OPEN_JAM_OUT", ROOT / "out"))
VIZ = Path(os.environ.get("OPEN_JAM_VIZ", ROOT / "viz"))
DATA = ROOT / "data"

NET = SIM / "area.net.xml"
VTYPES = SIM / "vtypes.add.xml"
LANDMARKS = SIM / "landmarks.txt"  # puntos de referencia del A* (ALT), los arma demanda.py
TLS = SIM / "tls_webster.add.xml"
RUTAS = (SIM / "am_calibrado.rou.xml", SIM / "am_fondo.rou.xml")
