"""Tiempos de verde de cada semáforo: lo que el agente controla en vivo.

Cada semáforo repite su ciclo de Webster (sim/tls_webster.add.xml, programa "w"):
fases de verde separadas por amarillos y rojos de despeje. El agente solo cambia cuánto
dura cada verde; la secuencia, los amarillos y los rojos quedan como están, así nunca se
salta un amarillo. Fase verde: tiene algún verde (G o g) y ningún amarillo; las de
transición ("yyyyrrrrGyyy", con un giro que sigue en verde) no se tocan.

`fijar` cambia el programa sin cortar la fase en curso: termina cuando iba a terminar
y los tiempos nuevos valen desde la fase siguiente.
"""

from typing import Any

from .politicas import PROGRAMA_ENCENDIDO

VERDE_MIN_S = 5.0
VERDE_MAX_S = 120.0


def es_verde(estado: str) -> bool:
    return ("G" in estado or "g" in estado) and "y" not in estado


def _programa(sumo, tls: str):
    for lg in sumo.trafficlight.getAllProgramLogics(tls):
        if lg.programID == PROGRAMA_ENCENDIDO:
            return lg
    raise ValueError(f"{tls}: no tiene el programa {PROGRAMA_ENCENDIDO!r}")


def fases(sumo, tls: str) -> list[dict[str, Any]]:
    """El ciclo del semáforo: [{"estado", "duracion", "verde"}], en orden."""
    return [{"estado": p.state, "duracion": p.duration, "verde": es_verde(p.state)} for p in _programa(sumo, tls).phases]


def verdes(sumo, tls: str) -> list[float]:
    """Duración de cada fase verde, en orden del ciclo."""
    return [f["duracion"] for f in fases(sumo, tls) if f["verde"]]


def movimientos(sumo, tls: str) -> list[set[tuple[str, str]]]:
    """Por cada fase verde, en orden, los (tramo de entrada, tramo de salida) que tienen verde."""
    enlaces = sumo.trafficlight.getControlledLinks(tls)  # por índice de señal: [(carril in, carril out, vía)]
    tramo = sumo.lane.getEdgeID
    return [{(tramo(a), tramo(b)) for i, s in enumerate(f["estado"]) if s in "Gg" for a, b, _ in enlaces[i]}
            for f in fases(sumo, tls) if f["verde"]]


def validar(sumo, tls: str, nuevos: Any) -> list[float]:
    """`nuevos` como lista de floats si sirve para `tls`; si no, ValueError o TypeError con el motivo."""
    if tls not in sumo.trafficlight.getIDList():
        raise ValueError(f"semáforo desconocido: {tls!r}")
    if not isinstance(nuevos, list | tuple) or not all(
            isinstance(v, int | float) and not isinstance(v, bool) for v in nuevos):
        raise TypeError(f"{tls}: los verdes deben ser una lista de segundos")
    n = len(verdes(sumo, tls))
    if len(nuevos) != n:
        raise ValueError(f"{tls}: tiene {n} fases verdes, llegaron {len(nuevos)} tiempos")
    fuera = [v for v in nuevos if not VERDE_MIN_S <= v <= VERDE_MAX_S]
    if fuera:
        raise ValueError(f"{tls}: verdes fuera de [{VERDE_MIN_S:g}, {VERDE_MAX_S:g}] s: {fuera}")
    return [float(v) for v in nuevos]


def fijar(sumo, tls: str, nuevos: Any) -> None:
    """Cambia los verdes de `tls` (ver `validar`). Con el semáforo apagado, ValueError."""
    nuevos = validar(sumo, tls, nuevos)
    tl = sumo.trafficlight
    if tl.getProgram(tls) != PROGRAMA_ENCENDIDO:
        raise ValueError(f"{tls}: está apagado (programa {tl.getProgram(tls)!r}); no tiene tiempos")
    lg = _programa(sumo, tls)
    resto = iter(nuevos)
    nuevas = []
    for p in lg.phases:
        d = next(resto) if es_verde(p.state) else p.duration
        nuevas.append(tl.Phase(d, p.state, d, d))
    fase, cambio = tl.getPhase(tls), tl.getNextSwitch(tls)
    tl.setProgramLogic(tls, tl.Logic(lg.programID, lg.type, fase, nuevas))
    tl.setPhaseDuration(tls, cambio - sumo.simulation.getTime())  # la fase en curso no se corta
