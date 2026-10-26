"""Políticas de semáforos. La única acción posible es apagar o encender los de cada corredor.

El simulador (`sim.correr`) llama a `Politica.decidir(obs)` cada `cada` segundos
simulados. `obs` es un dict serializable a JSON (lo que va a leer el LLM):

  t                  segundo simulado de la decisión
  periodo            índice del periodo de fluidez que empieza (t // periodo); None sin fluidez
  ultimo             {"t0", "t1"} del último periodo cerrado, o None al arrancar
  red                {"fluidez", "parado_h"} de ese periodo para toda la red, o None
  corredores         {id: {"fluidez", "parado_h"}} de ese periodo (None antes del primero)
  decision_anterior  {id: encendido} vigente hasta ahora (al arrancar, todos encendidos)

La respuesta es {id de corredor: True (encendidos) | False (apagados)}; los corredores
que no nombra quedan como estaban. Se valida (`validar`) antes de aplicarla y queda
registrada en las métricas de cada periodo (`periodos[i]["decisiones"]`), junto con
`periodos[i]["resto"]`: el estado fijo (`Politica.resto`) de los semáforos que no son
de ningún corredor.
"""

from typing import Any

from .corredores import Corredor

PROGRAMA_ENCENDIDO = "w"  # tiempos de Webster, sim/tls_webster.add.xml
PROGRAMA_APAGADO = "off"  # reglas de prioridad, como amarillo intermitente

Observacion = dict[str, Any]
Decision = dict[str, bool]


class Politica:
    """Base: decide cada `cada` segundos simulados qué corredores quedan encendidos."""

    cada: float = 900
    nombre: str = "politica"
    resto: bool = True  # semáforos fuera de los corredores: la base no los toca (siguen con Webster)

    def decidir(self, obs: Observacion) -> Decision:
        raise NotImplementedError

    def aplicar(self, sumo, corr: dict[str, Corredor], estado: Decision) -> None:
        """Lleva el `estado` completo {corredor: encendido} a los semáforos de SUMO."""
        aplicar_corredores(sumo, corr, estado)


class Fija(Politica):
    """Todos encendidos o todos apagados desde el inicio; decide una sola vez, en t = 0."""

    cada = float("inf")

    def __init__(self, encendido: bool):
        self.encendido = encendido
        self.resto = encendido
        self.nombre = "on" if encendido else "off"

    def decidir(self, obs: Observacion) -> Decision:
        return {c: self.encendido for c in obs["decision_anterior"]}

    def aplicar(self, sumo, corr: dict[str, Corredor], estado: Decision) -> None:
        # Todos los semáforos de la red, no solo los de corredores: "off" es la ciudad sin semáforos.
        aplicar(sumo, {tls: self.encendido for tls in sumo.trafficlight.getIDList()})


class Agente(Politica):
    """Ejemplo sin LLM, para probar el circuito: un umbral de fluidez por corredor.

    Si en el último periodo el corredor pasó parado más de `1 - umbral` de su tiempo,
    enciende sus semáforos (con la cola larga, el ciclo ordena los cruces); si fluye,
    los apaga (con poco tráfico el rojo solo hace esperar). Sin datos (nadie pasó por el
    corredor, o todavía no cerró ningún periodo) deja lo que había.
    """

    nombre = "agente"

    def __init__(self, umbral: float = 0.7, cada: float = 900):
        self.umbral = umbral
        self.cada = cada

    def decidir(self, obs: Observacion) -> Decision:
        d = {}
        for c, m in obs["corredores"].items():
            if m["fluidez"] is not None:
                d[c] = m["fluidez"] < self.umbral
        return d


def validar(decision: Any, conocidos) -> Decision:
    """La decisión tal cual si es {corredor conocido: bool}; si no, TypeError o ValueError con el motivo."""
    if not isinstance(decision, dict):
        raise TypeError(f"la decisión debe ser un dict {{corredor: bool}}, no {type(decision).__name__}")
    desconocidos = sorted(set(decision) - set(conocidos))
    if desconocidos:
        raise ValueError(f"corredores desconocidos: {desconocidos}")
    no_bool = sorted(c for c, v in decision.items() if not isinstance(v, bool))
    if no_bool:
        raise ValueError(f"valores que no son true/false en: {no_bool}")
    return dict(decision)


def observacion(t: float, periodo: int | None, ultimo: dict[str, Any] | None, anterior: Decision) -> Observacion:
    """Arma la observación para `decidir` (ver el docstring del módulo).

    `ultimo`: resumen del último periodo cerrado (`fluidez.resumir`) o None.
    """
    vacio = {"fluidez": None, "parado_h": None}
    return {
        "t": int(t),
        "periodo": periodo,
        "ultimo": {"t0": ultimo["t0"], "t1": ultimo["t1"]} if ultimo else None,
        "red": ultimo["red"] if ultimo else None,
        "corredores": {c: dict(ultimo["corredores"][c]) if ultimo else dict(vacio) for c in anterior},
        "decision_anterior": dict(anterior),
    }


def aplicar(sumo, decisiones: dict[str, bool]) -> None:
    """`decisiones`: {tls_id: True (encendido) | False (apagado)}.

    Solo toca los que cambian: `setProgram` reinicia el ciclo y, si se llamara en cada
    decisión, los semáforos que siguen encendidos perderían su fase.
    """
    for tls, encendido in decisiones.items():
        programa = PROGRAMA_ENCENDIDO if encendido else PROGRAMA_APAGADO
        if sumo.trafficlight.getProgram(tls) != programa:
            sumo.trafficlight.setProgram(tls, programa)


def estado_semaforos(corr: dict[str, Corredor], estado: Decision) -> dict[str, bool]:
    """{tls: encendido} de los semáforos de los corredores en `estado`.

    Un semáforo compartido por dos corredores (un cruce entre avenidas) queda apagado
    solo si todos sus corredores lo apagan.
    """
    res: dict[str, bool] = {}
    for c, encendido in estado.items():
        for tls in corr[c]["semaforos"]:
            res[tls] = res.get(tls, False) or encendido
    return res


def aplicar_corredores(sumo, corr: dict[str, Corredor], estado: Decision) -> None:
    """`estado`: {corredor: encendido}; `corr` sale de `corredores.corredores(sumo)`."""
    aplicar(sumo, estado_semaforos(corr, estado))


def politica(p: "str | Politica") -> Politica:
    """La política tal cual si ya es un objeto; si es un nombre: on, off o agente."""
    if isinstance(p, Politica):
        return p
    if p == "on":
        return Fija(True)
    if p == "off":
        return Fija(False)
    if p == "agente":
        return Agente()
    raise ValueError(f"política desconocida: {p!r} (on, off, agente o un objeto Politica)")
