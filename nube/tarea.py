"""Una tarea de Cloud Batch: exporta un escenario (o rehace la demanda, TAREA=demanda) y guarda todo en el bucket montado.

Cada tarea toma el escenario `ESCENARIOS[BATCH_TASK_INDEX]`. Simula en el disco local de la VM
(fluidez.py lee el log de SUMO mientras se escribe, y eso no anda sobre gcsfuse) y copia los
puntos de control al bucket cada minuto. Si Google recupera la VM spot, Batch reintenta la tarea:
baja los puntos de control del bucket y `open_jam.export` retoma desde el último.
"""

import os
import resource
import shutil
import subprocess
import sys
import threading
from pathlib import Path

BUCKET = Path(os.environ.get("BUCKET_DIR", "/mnt/disks/gcs"))
SIM = Path(__file__).resolve().parent.parent / "sim"  # open_jam.rutas.SIM; el paquete no está en sys.path
OUT = Path(os.environ["OPEN_JAM_OUT"])
VIZ = Path(os.environ["OPEN_JAM_VIZ"])


def copiar(origen: Path, destino: Path) -> None:
    """Copia los archivos nuevos o cambiados; los .control.json y fin.json al final, para que nunca
    apunten a un estado de SUMO o a salidas que todavía no están en el destino."""
    if not origen.exists():
        return
    archivos = sorted((p for p in origen.rglob("*") if p.is_file()), key=lambda p: p.name.endswith((".control.json", "fin.json")))
    for p in archivos:
        d = destino / p.relative_to(origen)
        try:
            st = p.stat()
            if d.exists() and d.stat().st_size == st.st_size and d.stat().st_mtime >= st.st_mtime:
                continue
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, d)
        except FileNotFoundError:  # SUMO o export lo borró mientras tanto
            pass


def demanda() -> None:
    """Corre open_jam.demanda entero (routeSampler, duaIterate y otra vez routeSampler) y deja en el
    bucket lo que el export necesita en sim/ y los tiempos de equilibrio."""
    subprocess.run([sys.executable, "-m", "open_jam.demanda"], check=True)
    for nombre in ("am_calibrado.rou.xml", "am_fondo.rou.xml", "tls_webster.add.xml", "conteos_am.xml",
                   "vtypes.add.xml", "landmarks.txt"):
        (BUCKET / "demanda" / "sim").mkdir(parents=True, exist_ok=True)
        shutil.copy2(SIM / nombre, BUCKET / "demanda" / "sim" / nombre)
    ultima = max((OUT / "equilibrio").glob("[0-9][0-9][0-9]"))
    (BUCKET / "demanda" / "equilibrio").mkdir(parents=True, exist_ok=True)
    for p in ultima.glob("dump_*.xml"):
        shutil.copy2(p, BUCKET / "demanda" / "equilibrio" / p.name)
    print("demanda: lista en el bucket", flush=True)


def main() -> None:
    if os.environ.get("TAREA") == "demanda":
        return demanda()
    escenario = os.environ["ESCENARIOS"].split(",")[int(os.environ.get("BATCH_TASK_INDEX", "0"))]
    control = f"{escenario}.control"
    copiar(BUCKET / "out" / control, OUT / control)  # retoma si hay puntos de control de un intento anterior

    fin = threading.Event()

    def sincronizar() -> None:
        while not fin.wait(60):
            copiar(OUT / control, BUCKET / "out" / control)

    hilo = threading.Thread(target=sincronizar, daemon=True)
    hilo.start()
    args = os.environ.get("EXPORT_ARGS", "").split()
    r = subprocess.run([sys.executable, "-m", "open_jam.export", escenario, *args], check=False)
    # el mayor de los procesos hijos (SUMO o el que postprocesa); ru_maxrss viene en KB en Linux
    pico = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 2**20
    print(f"{escenario}: salió con {r.returncode}, pico de memoria {pico:.1f} GiB", flush=True)
    fin.set()
    hilo.join()
    copiar(OUT / control, BUCKET / "out" / control)
    if r.returncode:
        sys.exit(r.returncode)
    copiar(VIZ / "data" / escenario, BUCKET / "viz" / "data" / escenario)
    shutil.copy2(VIZ / "data" / "red.json", BUCKET / "viz" / "data" / "red.json")
    print(f"{escenario}: listo en el bucket", flush=True)


if __name__ == "__main__":
    main()
