"""Fluidez: cuánto del tiempo que los vehículos pasan en la red están parados.

SUMO lo mide solo con un `edgeData` (meandata) por periodo (15 min por defecto, la
cadencia del agente): por tramo, `sampledSeconds` (vehículo-segundos en el tramo) y
`waitingTime` (vehículo-segundos con velocidad < 0.1 m/s). Se suma por corredor y
para toda la red:

  parado_h  horas-vehículo paradas en el periodo (lo que se quiere bajar)
  fluidez   1 - parado / en red: fracción del tiempo en movimiento (1 = nadie se detiene)

SUMO escribe cada periodo al cerrarlo; `leer()` toma lo nuevo del archivo, así el
agente ve el periodo recién terminado en cuanto le toca decidir. Medirlo desde Python
(muestreando cada tramo) triplicaba el tiempo de una corrida meso y, en meso, casi no
veía vehículos parados.
"""

import re
from pathlib import Path
from typing import Any

INTERVALO = re.compile(rb'<interval begin="([\d.]+)"')
TRAMO = re.compile(rb'<edge id="([^"]+)"([^>]*)/>')
ATRIB = re.compile(rb'(sampledSeconds|waitingTime)="([\d.]+)"')
CIERRE = b"</interval>"


def archivos(c, desde: float = 0) -> tuple[Path, Path]:
    """(additional que le pide a SUMO la medición, salida donde SUMO la escribe) de la corrida `c`."""
    return c.salida("fluidez.add.xml", desde), c.salida("fluidez.xml", desde)


def escribir_adicional(c, desde: float = 0) -> Path:
    """Escribe el additional de `archivos(c, desde)`; devuelve la salida."""
    add, salida = archivos(c, desde)
    add.parent.mkdir(parents=True, exist_ok=True)
    add.write_text(f'<additional><edgeData id="fluidez" period="{c.fluidez}" file="{salida}" '
                   f'excludeEmpty="true"/></additional>\n')
    return salida


class Fluidez:
    """Lee incrementalmente la salida de SUMO y acumula por periodo, para la red y por corredor.

    `corr`: {id: {"tramos": [...]}} (ver `corredores.corredores`). Un tramo puede ser de
    varios corredores; cuenta en cada uno. `periodo` (s) da el fin de cada periodo: el
    último, SUMO lo cierra donde terminó la corrida, que depende de cómo se avanzó.
    """

    def __init__(self, salida: Path, corr: dict[str, dict[str, Any]], periodo: int):
        self.salida = salida
        self.periodo = periodo
        self.pos = 0
        self.resto = b""
        self.ids = list(corr)
        self.de_tramo: dict[str, list[str]] = {}
        for n, c in corr.items():
            for e in c["tramos"]:
                self.de_tramo.setdefault(e, []).append(n)
        # [{"t0", "t1", "red": [en_red_s, parado_s], "corredores": {id: [en_red_s, parado_s]}}]
        self.periodos: list[dict[str, Any]] = []

    def seguir_en(self, salida: Path) -> None:
        """Termina de leer el archivo actual y sigue en `salida` (el del tramo siguiente)."""
        self.leer()
        self.salida, self.pos, self.resto = salida, 0, b""

    def leer(self) -> None:
        """Agrega los periodos que SUMO terminó de escribir desde la última lectura.

        Un periodo a medio escribir (sin su `</interval>`) queda para la próxima.
        """
        if not self.salida.exists():
            return
        with open(self.salida, "rb") as f:
            f.seek(self.pos)
            nuevo = f.read()
        self.pos += len(nuevo)
        texto = self.resto + nuevo
        corte = texto.rfind(CIERRE)
        if corte < 0:
            self.resto = texto
            return
        corte += len(CIERRE)
        texto, self.resto = texto[:corte], texto[corte:]
        for bloque in texto.split(CIERRE)[:-1]:
            m = INTERVALO.search(bloque)
            t0 = int(float(m.group(1)))
            p = {"t0": t0, "t1": t0 + self.periodo, "red": [0.0, 0.0],
                 "corredores": {n: [0.0, 0.0] for n in self.ids}}
            for e, attrs in TRAMO.findall(bloque, m.end()):
                a = dict(ATRIB.findall(attrs))
                s, w = float(a.get(b"sampledSeconds", 0)), float(a.get(b"waitingTime", 0))
                p["red"][0] += s
                p["red"][1] += w
                for n in self.de_tramo.get(e.decode(), ()):
                    p["corredores"][n][0] += s
                    p["corredores"][n][1] += w
            self.periodos.append(p)

    def ultimo(self) -> dict[str, Any] | None:
        """Resumen (`resumir`) del último periodo cerrado; None si todavía no hay."""
        self.leer()
        return resumir(self.periodos[-1]) if self.periodos else None

    def resumen(self) -> dict[str, Any]:
        """Toda la corrida: un número por corredor y para la red."""
        self.leer()
        total = {"t0": self.periodos[0]["t0"] if self.periodos else 0,
                 "t1": self.periodos[-1]["t1"] if self.periodos else 0,
                 "red": [0, 0], "corredores": {n: [0, 0] for n in self.ids}}
        for p in self.periodos:
            for i in (0, 1):
                total["red"][i] += p["red"][i]
                for n in self.ids:
                    total["corredores"][n][i] += p["corredores"][n][i]
        return resumir(total)


def _fl(en_red: float, parado: float) -> dict[str, float | None]:
    return {"parado_h": round(parado / 3600, 1), "fluidez": round(1 - parado / en_red, 3) if en_red else None}


def resumir(p: dict[str, Any]) -> dict[str, Any]:
    """Periodo acumulado -> {"t0", "t1", "red": {fluidez, parado_h}, "corredores": {id: {...}}}."""
    return {"t0": p["t0"], "t1": p["t1"], "red": _fl(*p["red"]),
            "corredores": {n: _fl(*v) for n, v in p["corredores"].items()}}
