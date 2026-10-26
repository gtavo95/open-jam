# Imagen para exportar escenarios en Cloud Batch (ver scripts/nube.sh).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
# libsumo y sumo vienen compilados con soporte de GUI aunque no se use: piden X11 y GL.
RUN apt-get update && apt-get install -y --no-install-recommends libx11-6 libxext6 libxrender1 libxft2 \
    libxcursor1 libxrandr2 libxi6 libxfixes3 libgl1 libglu1-mesa libfontconfig1 libgomp1 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PATH=/app/.venv/bin:$PATH \
    OPEN_JAM_OUT=/work/out OPEN_JAM_VIZ=/work/viz PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# Comprueba que SUMO y libsumo arrancan en esta imagen antes de subirla.
RUN for f in .venv/lib/python3.12/site-packages/sumo/bin/sumo .venv/lib/python3.12/site-packages/libsumo/_libsumo*.so; do \
      ! ldd "$f" | grep "not found"; done && sumo --version | head -1 && python -c "import libsumo, traci"
COPY data/corredores.json data/
COPY data/osm/polos.json data/osm/
COPY sim/area.net.xml sim/am_calibrado.rou.xml sim/am_fondo.rou.xml sim/vtypes.add.xml \
     sim/tls_webster.add.xml sim/landmarks.txt sim/
COPY open_jam open_jam
COPY nube/tarea.py nube/
ENTRYPOINT ["python", "nube/tarea.py"]
