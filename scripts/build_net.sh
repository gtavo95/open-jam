#!/usr/bin/env bash
# Convierte el OSM del área (ver scripts/bajar_osm.sh) en una red SUMO con semáforos.
# Usa los semáforos marcados en OSM (highway=traffic_signals) y une los que
# quedan en la misma intersección (calzadas divididas como Reforma). En OSM el semáforo
# suele estar en cada acceso, antes de la esquina: guess-signals.dist 40 y join-dist 50
# los juntan en un solo cruce (512 nodos en OSM -> 318 semáforos, faltan 3). No se usa
# --tls.discard-simple: descartaba 104 semáforos reales, sobre todo en zona 1.
# Sin --ramps.guess: metía 392 rampas falsas en calles urbanas (tramos que se ensanchan
# a 5 carriles y caen a 1 en 50 m), con cambios de carril forzados que trababan cruces.
# El offset queda fijo para que terreno y escena.json sigan alineados si cambia el OSM.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p sim
uv run netconvert \
  --osm-files data/osm/area.osm.xml \
  --output-file sim/area.net.xml \
  --keep-edges.by-vclass passenger \
  --remove-edges.isolated \
  --geometry.remove \
  --roundabouts.guess \
  --junctions.join \
  --tls.guess-signals \
  --tls.guess-signals.dist 40 \
  --tls.join \
  --tls.join-dist 50 \
  --tls.default-type static \
  --output.street-names \
  --output.original-names \
  --no-turnarounds.tls \
  --offset.disable-normalization \
  --offset.x -754053.29 \
  --offset.y -1609555.39 \
  --verbose false
