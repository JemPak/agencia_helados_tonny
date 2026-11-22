#!/usr/bin/env bash
# Respaldo completo de una base de Odoo: base de datos + filestore (imágenes y adjuntos).
# Uso: scripts/backup.sh [nombre_base]   (por defecto: agencia)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

DB="${1:-agencia}"
U="${POSTGRES_USER:-odoo}"
OUT="backups/${DB}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

docker compose exec -T db pg_dump -U "$U" -Fc "$DB" > "$OUT/db.dump"
docker compose exec -T odoo tar -C /var/lib/odoo/filestore -czf - "$DB" > "$OUT/filestore.tar.gz"

echo "Respaldo guardado en $OUT"
