"""Corre una `Corrida`: arranca SUMO, avanza y le da el control a la política.

La política no se llama en cada paso sino cada `politica.cada` segundos simulados;
entre decisiones SUMO avanza solo (`simulationStep(t)`), sin volver a Python.
Con libsumo eso es una llamada de función; con TraCI, un mensaje por socket.

Puntos de control (`Corrida.control_s`): cada tanto se guarda el estado de SUMO y el de
Python (decisiones y fluidez) y SUMO sigue en un tramo nuevo, con sus salidas aparte, en
el mismo proceso (`load`). Si la corrida se corta, `correr` la retoma desde el último punto
de control de la misma configuración; las salidas de los tramos terminados quedan cerradas.
Al terminar guarda las métricas en `fin.json`: si lo que falla es lo que viene después (el
postproceso del export), volver a correrla no resimula nada.
"""

import hashlib
import importlib
import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from . import metricas
from .config import Corrida
from .corredores import corredores
from .fluidez import Fluidez, escribir_adicional, resumir
from .politicas import observacion, politica, validar


def backend(nombre: str) -> ModuleType:
    """libsumo y traci tienen la misma API; libsumo corre dentro del proceso."""
    return importlib.import_module(nombre)


def correr(c: Corrida, gui: bool = False, observar: Callable[[Any, float], None] | None = None,
           cada_obs: float = 60) -> dict[str, Any]:
    """Devuelve las métricas de la corrida más los tiempos reales.

    `observar(sumo, t)` se llama cada `cada_obs` segundos simulados (export, benchmarks).
    Si `c.fluidez`, se mide la fluidez (ver open_jam/fluidez.py), la política la recibe en
    su observación y las métricas traen `periodos`, cada uno con las `decisiones`
    {corredor: encendido} vigentes al empezar ese periodo y `resto` (`Politica.resto`).
    """
    if c.control_s and c.fluidez and c.control_s % c.fluidez:
        raise ValueError(f"control_s ({c.control_s}) tiene que ser múltiplo de fluidez ({c.fluidez})")
    fin = terminada(c)
    if fin and not gui and not observar:
        return fin
    p = politica(c.politica)
    sumo = backend("traci" if gui else c.backend)
    previo = ultimo_control(c)
    desde = previo["t"] if previo else 0
    if c.salidas or c.control_s:
        c.salida("log", desde).parent.mkdir(parents=True, exist_ok=True)
    if c.control_s and not previo:
        for viejo in c.salida("x").parent.glob("*"):  # de otra corrida con el mismo nombre
            viejo.unlink()
    salida_fl = escribir_adicional(c, desde) if c.fluidez else None
    if salida_fl:
        salida_fl.unlink(missing_ok=True)  # de una corrida anterior con el mismo nombre: se leería como propia
    estado_sumo = c.salida("estado.xml.gz", desde) if previo else None
    t0 = time.perf_counter()
    if sumo.__name__ == "traci":
        sumo.start(c.args(gui, desde, estado_sumo), stdout=subprocess.DEVNULL)
    else:
        sumo.start(c.args(desde=desde, estado=estado_sumo))
    try:
        carga = time.perf_counter() - t0
        corr = corredores(sumo, c.corredores)
        fl = Fluidez(salida_fl, corr, c.fluidez) if salida_fl else None
        estado = {k: True for k in corr}  # al arrancar todos los semáforos tienen su programa de Webster
        historial: list[tuple[float, dict[str, bool]]] = []  # (t, estado vigente desde t)
        if previo:
            estado = previo["estado"]
            historial = [(t, e) for t, e in previo["historial"]]
            if fl:
                fl.periodos = previo["periodos"]
            p.aplicar(sumo, corr, estado)  # ídem al retomar en otro proceso

        def control(s, t):
            if t <= desde or t >= c.hasta:
                return
            archivo = c.salida("estado.xml.gz", t)
            s.simulation.saveState(str(archivo))
            nueva_fl = escribir_adicional(c, t) if fl else None
            s.load(c.args(gui, t, archivo)[1:])  # cierra las salidas del tramo que termina
            p.aplicar(s, corr, estado)  # el estado de SUMO no guarda el programa "off": vuelven a Webster
            if fl:
                fl.seguir_en(nueva_fl)
            guardar_control(c, t, estado, historial, fl.periodos if fl else [])

        def decidir(s, t):
            nonlocal estado
            periodo = int(t // c.fluidez) if c.fluidez else None
            obs = observacion(t, periodo, fl.ultimo() if fl else None, estado)
            estado = estado | validar(p.decidir(obs), corr)
            p.aplicar(s, corr, estado)
            historial.append((t, dict(estado)))

        tareas = [[0, p.cada, decidir]]  # [próxima vez, cada, función]; la política va primero
        if c.control_s:
            tareas.insert(0, [0, c.control_s, control])  # antes de decidir: la decisión ya es del tramo nuevo
        if observar:
            tareas.append([0, cada_obs, observar])
        t = sumo.simulation.getTime()
        for tarea in tareas:
            tarea[0] = t
        while t < c.hasta and sumo.simulation.getMinExpectedNumber() > 0:
            for tarea in tareas:
                if t >= tarea[0]:
                    tarea[2](sumo, t)
                    tarea[0] = t + tarea[1]
            if c.por_paso:
                sumo.simulationStep()
            else:
                sumo.simulationStep(min(min(tarea[0] for tarea in tareas), c.hasta))
            t = sumo.simulation.getTime()
        pendientes = sumo.simulation.getMinExpectedNumber()
    finally:
        sumo.close()  # cierra también el último periodo de fluidez y el statistic-output
    total = time.perf_counter() - t0

    m = metricas.leer(c, t, pendientes) if c.salidas else {"escenario": c.nombre, "fin_s": int(t)}
    if previo:
        m["retomada_en"] = desde  # carga_s y pared_s son solo de esta parte
    m |= {"carga_s": round(carga, 2), "sim_s": round(total - carga, 2), "pared_s": round(total, 2),
          "factor_tiempo_real": round(t / max(total - carga, 1e-9), 2)}
    if fl:
        r = fl.resumen()
        m |= {"fluidez": r["red"]["fluidez"], "parado_h": r["red"]["parado_h"], "corredores": r["corredores"],
              "periodos": [resumir(x) | {"decisiones": vigente(historial, x["t0"]), "resto": p.resto} for x in fl.periodos]}
    if c.control_s:
        guardar_fin(c, m)
    return m


def vigente(historial: list[tuple[float, dict[str, bool]]], t: float) -> dict[str, bool]:
    """Estado {corredor: encendido} decidido por última vez en o antes de `t`."""
    previos = [e for ti, e in historial if ti <= t]
    return previos[-1] if previos else (historial[0][1] if historial else {})


def huella(c: Corrida) -> str:
    """Identifica la configuración de la corrida, sin el horizonte: alargarla también retoma."""
    # Una política objeto entra por su nombre: su repr trae la dirección de memoria.
    return hashlib.sha256(repr(c.con(hasta=0, politica=politica(c.politica).nombre)).encode()).hexdigest()[:16]


def guardar_control(c: Corrida, t: float, estado: dict[str, bool], historial: list, periodos: list) -> None:
    """Lo de Python del punto de control en `t`; el estado de SUMO ya está en `c.salida("estado.xml.gz", t)`."""
    archivo = c.salida("control.json", t)
    tmp = archivo.with_suffix(".tmp")
    tmp.write_text(json.dumps({"t": t, "huella": huella(c), "estado": estado, "historial": historial,
                               "periodos": periodos}))
    tmp.replace(archivo)  # el punto de control vale solo si está completo


def archivo_fin(c: Corrida) -> Path:
    return c.salida("fin.json").parent / "fin.json"


def guardar_fin(c: Corrida, m: dict[str, Any]) -> None:
    """Las métricas de la corrida terminada, con lo que identifica la configuración y el horizonte."""
    archivo = archivo_fin(c)
    tmp = archivo.with_suffix(".tmp")
    tmp.write_text(json.dumps({"huella": huella(c), "hasta": c.hasta, "metricas": m}))
    tmp.replace(archivo)


def terminada(c: Corrida) -> dict[str, Any] | None:
    """Las métricas de esta misma corrida si ya terminó (misma configuración y horizonte), o None."""
    if not c.control_s or not archivo_fin(c).exists():
        return None
    d = json.loads(archivo_fin(c).read_text())
    return d["metricas"] if d["huella"] == huella(c) and d["hasta"] == c.hasta else None


def ultimo_control(c: Corrida) -> dict[str, Any] | None:
    """El último punto de control de esta misma configuración antes de `c.hasta`, o None."""
    if not c.control_s:
        return None
    validos = []
    for archivo in c.salida("control.json").parent.glob("*.control.json"):
        d = json.loads(archivo.read_text())
        if d["huella"] == huella(c) and d["t"] < c.hasta and c.salida("estado.xml.gz", d["t"]).exists():
            validos.append(d)
    return max(validos, key=lambda d: d["t"], default=None)
