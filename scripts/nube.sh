#!/usr/bin/env bash
# Exporta escenarios en Cloud Batch con VMs spot (unos centavos de dólar por hora y escenario).
# Cada escenario corre en su VM; los puntos de control van al bucket, así que si Google recupera
# la VM, Batch reintenta y retoma desde el último.
#
#   scripts/nube.sh preparar          # una vez: APIs, repositorio de imágenes y bucket
#   scripts/nube.sh imagen            # construye la imagen en Cloud Build (después de cambiar el código o sim/)
#   scripts/nube.sh correr on off     # lanza el job
#   scripts/nube.sh estado            # jobs y puntos de control en el bucket
#   scripts/nube.sh bajar on off      # trae viz/data/ y actualiza el manifest
#   scripts/nube.sh demanda           # open_jam.demanda completo (con duaIterate, ~3 h) en una VM de 16 núcleos
#   scripts/nube.sh bajar-demanda     # trae las rutas y semáforos nuevos a sim/ (después: imagen y correr)
set -euo pipefail
cd "$(dirname "$0")/.."
PROYECTO="${PROYECTO:?definí PROYECTO con el id del proyecto de GCP}"
REGION="${REGION:-us-east1}"
MAQUINA="${MAQUINA:-c2d-highmem-4}"  # 32 GB: margen para el postproceso (ver la estimación en `correr`)
MEMORIA="${MEMORIA:-30000}"  # MiB para la tarea; menos que la VM
BUCKET="${BUCKET:-$PROYECTO-open-jam}"
IMAGEN="$REGION-docker.pkg.dev/$PROYECTO/open-jam/export:latest"
EXPORT_ARGS="${EXPORT_ARGS:---muestreo 4 --threads 4}"
G=(gcloud --project "$PROYECTO")

# lanzar <tarea> <escenarios> <n tareas> <máquina> <MiB> <cpuMilli>
lanzar() {
  local job="$1-$(date +%Y%m%d-%H%M%S)" config
  config=$(mktemp)
  command cat >"$config" <<JSON
{
  "taskGroups": [{
    "taskCount": $3,
    "parallelism": $3,
    "taskSpec": {
      "runnables": [{"container": {"imageUri": "$IMAGEN", "volumes": ["/mnt/disks/gcs:/mnt/disks/gcs"]}}],
      "volumes": [{"gcs": {"remotePath": "$BUCKET"}, "mountPath": "/mnt/disks/gcs"}],
      "environment": {"variables": {"TAREA": "$1", "ESCENARIOS": "$2", "EXPORT_ARGS": "$EXPORT_ARGS"}},
      "computeResource": {"cpuMilli": $6, "memoryMib": $5},
      "maxRunDuration": "43200s",
      "maxRetryCount": 3,
      "lifecyclePolicies": [{"action": "RETRY_TASK", "actionCondition": {"exitCodes": [50001]}}]
    }
  }],
  "allocationPolicy": {
    "instances": [{"policy": {"machineType": "$4", "provisioningModel": "SPOT",
                              "bootDisk": {"sizeGb": 50}}}]
  },
  "logsPolicy": {"destination": "CLOUD_LOGGING"}
}
JSON
  "${G[@]}" batch jobs submit "$job" --location "$REGION" --config "$config"
  rm "$config"
  echo "avance: scripts/nube.sh estado; logs en la consola de Batch (job $job)"
}

case "${1:-}" in
preparar)
  "${G[@]}" services enable batch.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    compute.googleapis.com logging.googleapis.com storage.googleapis.com
  "${G[@]}" artifacts repositories describe open-jam --location "$REGION" >/dev/null 2>&1 ||
    "${G[@]}" artifacts repositories create open-jam --repository-format docker --location "$REGION"
  "${G[@]}" storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
    "${G[@]}" storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access
  ;;
imagen)
  "${G[@]}" builds submit --region "$REGION" --config nube/cloudbuild.yaml --substitutions "_IMAGEN=$IMAGEN" .
  ;;
correr)
  shift
  [ $# -gt 0 ] || set -- on off
  escenarios=("$@")
  lista=$(IFS=,; echo "${escenarios[*]}")
  # El postproceso tiene todo el FCD en memoria: ~80 B por fila (medido el 2026-10-17), y en la
  # red hay ~61 000 vehículos en promedio (micro de 90 min). Mejor no lanzar si no entra.
  hasta=$(sed -nE 's/.*--hasta[ =]([0-9]+).*/\1/p' <<<"$EXPORT_ARGS"); hasta=${hasta:-5400}
  muestreo=$(sed -nE 's/.*--muestreo[ =]([0-9.]+).*/\1/p' <<<"$EXPORT_ARGS"); muestreo=${muestreo:-2}
  estimada=$(awk -v h="$hasta" -v m="$muestreo" 'BEGIN { printf "%d", 61000 * h / m * 80 / 2^20 + 3000 }')
  if [ "$estimada" -gt "$MEMORIA" ] && [ -z "${FORZAR:-}" ]; then
    echo "el postproceso pediría ~$estimada MiB y la tarea tiene $MEMORIA: subí MAQUINA/MEMORIA o el --muestreo (FORZAR=1 lanza igual)" >&2
    exit 1
  fi
  echo "memoria estimada del postproceso: ~$estimada MiB de $MEMORIA"
  lanzar export "$lista" ${#escenarios[@]} "$MAQUINA" "$MEMORIA" 4000
  ;;
demanda)
  # Sin puntos de control: si Google recupera la VM spot, Batch reintenta desde cero.
  lanzar demanda "" 1 "${MAQUINA_DEMANDA:-c2d-standard-16}" "${MEMORIA_DEMANDA:-60000}" 16000
  ;;
bajar-demanda)
  "${G[@]}" storage cp "gs://$BUCKET/demanda/sim/*" sim/
  mkdir -p out/equilibrio
  "${G[@]}" storage cp "gs://$BUCKET/demanda/equilibrio/*" out/equilibrio/
  ;;
estado)
  "${G[@]}" batch jobs list --location "$REGION" --format "table(name.basename(), status.state, createTime)" --limit 5
  "${G[@]}" storage ls "gs://$BUCKET/out/*/*.control.json" 2>/dev/null || echo "sin puntos de control todavía"
  ;;
bajar)
  shift
  [ $# -gt 0 ] || set -- on off
  mkdir -p viz/data
  "${G[@]}" storage cp "gs://$BUCKET/viz/data/red.json" viz/data/
  for e in "$@"; do
    rm -rf "viz/data/$e"
    "${G[@]}" storage cp -r "gs://$BUCKET/viz/data/$e" viz/data/
  done
  uv run python -c "import sys; from open_jam import rutas; from open_jam.export import escribir_manifest; escribir_manifest(rutas.VIZ / 'data', sys.argv[1:])" "$@"
  ;;
*)
  sed -n '2,13p' "$0"; exit 1 ;;
esac
