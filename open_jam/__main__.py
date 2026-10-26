"""Corre la hora pico con una política de semáforos y reporta métricas.

Uso: uv run python -m open_jam on|off|agente [--meso] [--threads 4] [--hasta 5400] [--gui]
"""

import argparse

from .config import Corrida
from .sim import correr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("politica", choices=["on", "off", "agente"])
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--hasta", type=int, default=5400)
    ap.add_argument("--meso", action="store_true", help="modelo mesoscópico (~20x más rápido)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    c = Corrida(a.politica, politica=a.politica, hasta=a.hasta, meso=a.meso, threads=a.threads, seed=a.seed)
    for k, v in correr(c, gui=a.gui).items():
        if k not in ("corredores", "periodos"):  # por corredor y por periodo: demasiado para la terminal
            print(f"{k:18s} {v}")


if __name__ == "__main__":
    main()
