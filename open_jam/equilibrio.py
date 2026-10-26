"""Tiempos de viaje de equilibrio para la demanda calibrada (duaIterate en meso).

Las rutas candidatas de routeSampler salen de randomTrips, que rutea con la red vacía: todos
eligen el camino más corto a flujo libre y se amontonan en unos pocos corredores. duaIterate
simula la demanda, mide cuánto tarda cada tramo y vuelve a rutear, hasta que los conductores
no ganan cambiando de ruta (equilibrio de Wardrop, con el modelo de Gawron). Con los tiempos de
la última iteración `demanda` rutea otra vez las candidatas y deja que routeSampler elija entre
las de flujo libre y las de hora pico.

Corre en meso (~1.5 min por iteración en esta red) y se guarda: se rehace solo si cambian la
red, la demanda, los conductores, los semáforos o este comando.
"""

import shutil
from pathlib import Path

ITERACIONES = 20
FIN = 5400  # como el export: los que salen al final de la hora siguen midiendo tramos
AGREGACION = 900  # periodo de los tiempos por tramo (s)


def pesos(net: Path, rutas: list[Path], adicionales: list[Path], destino: Path, tools: Path,
          landmarks: Path, py: str, hilos: int, huella, run) -> Path:
    """Corre duaIterate en `destino` (o reusa la corrida anterior) y devuelve los tiempos por tramo de la última iteración.

    El primer adicional son los vType: duarouter también los necesita, y los escribe aparte para
    que SUMO no los cargue dos veces.
    La iteración 0 simula las rutas tal como vienen (--skip-first-routing).
    """
    ultima = ITERACIONES - 1
    dump = destino / f"{ultima:03d}" / f"dump_{float(AGREGACION)}.xml"  # duaIterate lo nombra así
    # Los argumentos de SUMO son los de `config.Corrida` en meso, sin reruteo (lo reemplaza duaIterate).
    cmd = [py, tools / "assign" / "duaIterate.py", "-n", net.resolve(), "-r", ",".join(str(r.resolve()) for r in rutas),
           "-+", ",".join(str(a.resolve()) for a in adicionales), "-b", 0, "-e", FIN, "-a", AGREGACION,
           "-l", ITERACIONES, "--mesosim", "--time-to-teleport", 600, "--disable-summary", "--disable-tripinfos",
           "--routing-algorithm", "astar", "--skip-first-routing", "--clean-alt", "--no-gzip",
           "duarouter--routing-threads", hilos, "duarouter--additional-files", adicionales[0].resolve(), "duarouter--vtype-output", "vtypes.xml",
           "duarouter--astar.landmark-distances", landmarks.resolve(),
           "sumo--threads", 4, "sumo--ignore-route-errors", "true", "sumo--ignore-junction-blocker", 15,
           "sumo--meso-junction-control", "true", "sumo--meso-overtaking", "true", "sumo--meso-edgelength", 50,
           "sumo--meso-minor-penalty", 10, "sumo--meso-taujj", 3.0, "sumo--meso-taufj", 3.0, "sumo--meso-taujf", 3.0]
    clave = huella(cmd, [net, *rutas, *adicionales, landmarks])
    sello = destino / "huella"
    if dump.exists() and sello.exists() and sello.read_text() == clave:
        print(f"= {destino.name}/ (equilibrio ya calculado con la misma demanda)")
        return dump
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    run(cmd, cwd=destino)
    sello.write_text(clave)
    return dump
