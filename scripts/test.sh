#!/usr/bin/env bash
# Corre las pruebas de aceptación de los módulos propios en una base temporal.
# Detiene el Odoo principal mientras tanto: sus tareas programadas recorren
# todas las bases y chocarían con la base de pruebas.
# Uso: scripts/test.sh [módulos]   (por defecto: todos los de addons/)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

MODULOS="${1:-$(ls addons | paste -sd, -)}"
TAGS="$(echo "$MODULOS" | sed 's/[^,]*/\/&/g')"
DB="pruebas_$(date +%s)"
U="${POSTGRES_USER:-odoo}"

limpiar() {
  rm -f "${LOG:-}"
  docker compose exec -T db dropdb -U "$U" --if-exists "$DB" >/dev/null 2>&1 || true
  docker compose run --rm -T --no-deps --entrypoint "" odoo rm -rf "/var/lib/odoo/filestore/$DB" >/dev/null 2>&1 || true
  docker compose start odoo >/dev/null
}
trap limpiar EXIT

docker compose stop odoo >/dev/null
LOG="$(mktemp)"
docker compose run --rm -T odoo odoo -d "$DB" -i "$MODULOS" \
  --test-enable --test-tags "$TAGS" --stop-after-init --max-cron-threads=0 2>&1 | tee "$LOG"
grep -q "0 failed, 0 error(s)" "$LOG"
