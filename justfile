# Pipeline completo: just todo. Cada paso se puede correr suelto.

default:
    @just --list

# OSM -> sim/area.net.xml (descarga de Overpass solo si falta data/osm/area.osm.xml)
red:
    test -f data/osm/area.osm.xml || scripts/bajar_osm.sh
    scripts/build_net.sh

# corredores del agente (data/corredores.json), desde la red
corredores:
    uv run python -m open_jam.corredores

# rutas calibradas con los conteos, conductores, landmarks del A* y semáforos Webster (~30 min)
demanda:
    uv run python -m open_jam.demanda

# relieve, edificios y zonas para el visor (viz/data/)
escena:
    uv run python -m open_jam.escena

# simula y exporta los escenarios para el visor (viz/data/)
exportar *escenarios="on off":
    uv run python -m open_jam.export {{escenarios}}

todo: red corredores demanda escena exportar

# una política con sus métricas: just correr off --meso
correr politica *flags:
    uv run python -m open_jam {{politica}} {{flags}}

test:
    uv run ruff check open_jam tests
    uv run pytest -q
    cd web && pnpm lint && pnpm check && pnpm test

# visor en http://localhost:5173 con los datos de viz/data/
web:
    cd web && pnpm dev

# A/B contra Webster desde el mismo estado: just ab presion --conjunto ajuste --paralelo 4
ab controlador *flags:
    uv run python -m open_jam.ab {{controlador}} {{flags}}

bench *flags:
    uv run python -m open_jam.bench {{flags}}

# publica en Cloudflare (ver scripts/deploy.sh)
deploy:
    scripts/deploy.sh
