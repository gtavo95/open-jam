#!/usr/bin/env bash
# Publica el visor en Cloudflare Pages y los datos (viz/data/) en un bucket de R2.
#
# Una sola vez:
#   - crear el bucket y darle un dominio público (R2 > bucket > Settings > Public access);
#   - CORS del bucket: GET desde el dominio de Pages;
#   - un token de R2 con escritura, guardado como perfil de aws: `aws configure --profile r2`;
#   - `pnpm dlx wrangler login` para Pages.
#
# Variables: R2_CUENTA (account id), R2_BUCKET, R2_URL (URL pública del bucket, con / final),
# PAGES_PROYECTO (por defecto open-jam).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${R2_CUENTA:?}" "${R2_BUCKET:?}" "${R2_URL:?}"
PAGES_PROYECTO="${PAGES_PROYECTO:-open-jam}"

test -f viz/data/manifest.json || { echo "falta viz/data/manifest.json: correr just exportar" >&2; exit 1; }

# Datos primero, para que el visor nuevo no apunte a archivos que todavía no están.
# Las ventanas no cambian una vez escritas (van con sha256 en meta.json): caché larga.
# manifest y meta.json se reescriben en cada export: caché corta.
S3=(aws s3 --profile r2 --endpoint-url "https://$R2_CUENTA.r2.cloudflarestorage.com")
"${S3[@]}" sync viz/data "s3://$R2_BUCKET/" --exclude "*.json" --cache-control "public, max-age=31536000, immutable"
"${S3[@]}" sync viz/data "s3://$R2_BUCKET/" --exclude "*" --include "*.json" --cache-control "public, max-age=60" --delete

cd web
pnpm install --frozen-lockfile
VITE_DATA_URL="$R2_URL" VITE_VERIFICAR_SHA256=1 pnpm build
pnpm dlx wrangler pages deploy dist --project-name "$PAGES_PROYECTO"
