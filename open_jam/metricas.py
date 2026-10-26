"""Métricas de una corrida leídas del `--statistic-output` de SUMO."""

import xml.etree.ElementTree as ET
from typing import Any


def leer(c, t: float, pendientes: int) -> dict[str, Any]:
    """Resumen de la corrida `c` que terminó en `t` con `pendientes` vehículos sin llegar.

    Con puntos de control hay un statistic-output por tramo: los conteos de vehículos ya
    vienen acumulados (están en el estado de SUMO); los promedios de viaje son de los que
    llegaron en cada tramo y se combinan ponderados.
    """
    archivos = c.tramos("stats.xml")
    if not archivos or not archivos[-1].exists():
        # SUMO lo escribe al cerrar; si no está, la corrida no tenía salidas o SUMO murió antes.
        raise FileNotFoundError(f"SUMO no escribió {c.salida('stats.xml')}; revisá {c.salida('log')}")
    veh = tele = None
    llegados, suma = 0, {"duration": 0.0, "waitingTime": 0.0, "timeLoss": 0.0}
    teleports = 0
    for archivo in archivos:
        s = ET.parse(archivo).getroot()
        veh, tele, trips = s.find("vehicles"), s.find("teleports"), s.find("vehicleTripStatistics")
        if veh is None or tele is None or trips is None:
            raise ValueError(f"{archivo} incompleto: falta vehicles, teleports o vehicleTripStatistics")
        n = int(trips.get("count"))
        llegados += n
        for k in suma:
            suma[k] += n * float(trips.get(k))
        teleports += int(tele.get("total"))
    insertados = int(veh.get("inserted"))
    prom = {k: round(v / llegados) if llegados else 0 for k, v in suma.items()}
    return {
        "escenario": c.nombre,
        "fin_s": int(t),
        "insertados": insertados,
        "llegaron": insertados - int(veh.get("running")),
        "sin_terminar": pendientes,
        "teleports": teleports,
        "viaje_prom_s": prom["duration"],
        "espera_prom_s": prom["waitingTime"],
        "demora_prom_s": prom["timeLoss"],
    }
