"""Qué se corre: red, rutas, horizonte y las opciones de SUMO que afectan el rendimiento."""

from dataclasses import dataclass, field, replace
from pathlib import Path

from . import corredores, rutas
from .fluidez import archivos
from .politicas import Politica


@dataclass(frozen=True)
class Corrida:
    """Una simulación: qué red, qué demanda, qué política y con qué opciones de SUMO.

    Las salidas van a `rutas.OUT` con `nombre` como prefijo.
    """

    nombre: str
    politica: str | Politica = "on"  # on | off | agente, o un objeto Politica (ver politicas.py)
    hasta: int = 5400  # segundos simulados
    seed: int = 42
    backend: str = "libsumo"  # libsumo (en proceso, sin socket) | traci
    meso: bool = False  # modelo mesoscópico (colas por tramo, mucho más rápido)
    threads: int = 1
    paso: float = 1.0  # step-length en segundos
    teleport: int = 600  # time-to-teleport; -1 lo desactiva. 10 min: en hora pico se espera eso y más
    sin_internos: bool = False  # --no-internal-links: sin carriles dentro de las intersecciones
    net: Path = rutas.NET
    adicionales: tuple[Path, ...] = (rutas.VTYPES, rutas.TLS)
    rutas: tuple[Path, ...] = rutas.RUTAS
    escala: float = 1.0  # --scale: multiplica la demanda cargada
    salidas: bool = True  # statistic-output y log
    por_paso: bool = False  # vuelve a Python en cada paso (como el script original)
    fluidez: int = 900  # periodo de la medición de fluidez (s); 0 no la mide
    reruteo: bool = True  # la mitad de los conductores (Waze) busca otra ruta cada 5 min según el tráfico
    ruteo: str = "astar"  # algoritmo de las rutas: dijkstra | astar | CH | CHWrapper
    corredores: Path | None = corredores.ARCHIVO  # corredores del agente (None: ninguno)
    # Cada cuántos s simulados guarda un punto de control (0: ninguno). Cada tramo entre puntos
    # escribe sus salidas aparte en out/<nombre>.control/; una corrida cortada retoma desde el último.
    control_s: int = 0
    fcd: float = 0  # cada cuántos s escribe posiciones de los vehículos en Parquet (0: no escribe)
    extra: tuple[str, ...] = field(default=())

    def con(self, **cambios) -> "Corrida":
        """Copia con algunos campos cambiados."""
        return replace(self, **cambios)

    def salida(self, tipo: str, desde: float = 0) -> Path:
        """Archivo de salida `tipo` (stats.xml, log, fluidez.xml, fcd.parquet...) del tramo que empieza en `desde`.

        Sin puntos de control hay un solo tramo: out/<nombre>.<tipo>.
        """
        if self.control_s:
            return rutas.OUT / f"{self.nombre}.control" / f"{int(desde):05d}.{tipo}"
        return rutas.OUT / f"{self.nombre}.{tipo}"

    def tramos(self, tipo: str) -> list[Path]:
        """Las salidas `tipo` de todos los tramos que hay escritos, en orden (una sola sin puntos de control)."""
        if not self.control_s:
            return [self.salida(tipo)]
        return sorted(self.salida(tipo).parent.glob(f"*.{tipo}"))

    def args(self, gui: bool = False, desde: float = 0, estado: Path | None = None) -> list[str]:
        """Línea de comandos de SUMO para esta corrida, o para su tramo desde `desde` cargando `estado`.

        No escribe nada: el directorio de salida y el additional de la fluidez los
        prepara `sim.correr` antes de arrancar SUMO.
        """
        cmd = [
            "sumo-gui" if gui else "sumo",
            "-n", str(self.net),
            "-a", ",".join(map(str, self.adicionales)),
            "-r", ",".join(map(str, self.rutas)),
            "--time-to-teleport", str(self.teleport),
            "--ignore-route-errors",
            "--ignore-junction-blocker", "15",  # destraba cruces bloqueados: +9% llegadas, -11% teleports
            "--no-step-log",
            "--seed", str(self.seed),
            "--step-length", str(self.paso),
            "--threads", str(self.threads),
            "--end", str(self.hasta),
        ]
        if self.control_s:
            cmd += ["--save-state.rng"]  # sin esto el tramo retomado diverge más de la corrida seguida
        if estado:
            cmd += ["--begin", str(desde), "--load-state", str(estado)]
        if self.salidas:
            cmd += [
                "--statistic-output", str(self.salida("stats.xml", desde)),
                "--duration-log.statistics", "true",
                "--log", str(self.salida("log", desde)),
            ]
        if self.fcd:
            cmd += ["--fcd-output", str(self.salida("fcd.parquet", desde)), "--device.fcd.period", str(self.fcd),
                    "--fcd-output.attributes", "x,y,speed,type"]
        if self.fluidez:
            add, _ = archivos(self, desde)
            cmd[cmd.index("-a") + 1] += f",{add}"
        if self.escala != 1.0:
            cmd += ["--scale", str(self.escala)]
        if self.meso:
            # junction-control: en las intersecciones se respetan semáforos y prioridades,
            # que es justo lo que el agente cambia.
            cmd += ["--mesosim", "--meso-junction-control", "true", "--meso-overtaking", "true"]
            # Calibrado contra micro en la red real, 90 min (scratchpad meso/grid.py):
            # por defecto meso deja pasar 60% más vehículos; así queda a ~1% en llegados y -5% en demora.
            cmd += ["--meso-edgelength", "50", "--meso-minor-penalty", "10",
                    "--meso-taujj", "3.0", "--meso-taufj", "3.0", "--meso-taujf", "3.0"]
        if self.reruteo:
            # 30 min de hora pico: +8% llegadas, -24% teleports, el doble de tiempo de cómputo.
            # Con probabilidad 1 y periodo 120 s no terminaba.
            cmd += ["--device.rerouting.probability", "0.5", "--device.rerouting.period", "300",
                    "--device.rerouting.adaptation-interval", "10", "--device.rerouting.adaptation-steps", "18",  # memoria de 3 min, como Waze
                    "--device.rerouting.threads", str(max(self.threads, 2)), "--routing-algorithm", self.ruteo]
            if self.ruteo == "astar" and self.net == rutas.NET and rutas.LANDMARKS.exists():  # son tramos de la red real
                cmd += ["--astar.landmark-distances", str(rutas.LANDMARKS)]
        if self.sin_internos:
            cmd += ["--no-internal-links"]
        return cmd + list(self.extra)
