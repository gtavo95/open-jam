#!/usr/bin/env bash
# Descarga de OSM todas las calles del área ampliada (Trébol, Roosevelt hasta San Cristóbal,
# Periférico, Belice, Calle Martí y la entrada del Atlántico en zona 18), hasta residenciales.
# Antes fuera del núcleo solo bajaban las vías terciarias o mayores: sin calles de barrio
# no había rutas alternas y todo el tráfico quedaba obligado a las arterias.
set -euo pipefail
cd "$(dirname "$0")/.."

AMPLIADA="14.555,-90.605,14.672,-90.455"
TODAS="motorway|trunk|primary|secondary|tertiary|unclassified|residential|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|living_street"

mkdir -p data/osm
curl -sS -A 'open-jam/0.1' -o data/osm/area.osm.xml \
  --data-urlencode "data=[out:xml][timeout:300];way[\"highway\"~\"^($TODAS)$\"]($AMPLIADA);(._;>;);out meta;" \
  https://overpass-api.de/api/interpreter
echo "vías: $(grep -c '<way' data/osm/area.osm.xml)"
