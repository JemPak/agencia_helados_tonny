#!/usr/bin/env bash
# Crea una base de demostración copiando otra y le simula semanas de operación
# con DATOS FICTICIOS (usuarios, clientes, pedidos, ventas, compras, cierres).
# Uso: scripts/simular.sh [base_origen] [base_demo] [días]
#      por defecto: agencia -> agencia_demo, 28 días
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

ORIGEN="${1:-agencia}"
DEMO="${2:-agencia_demo}"
DIAS="${3:-28}"
U="${POSTGRES_USER:-odoo}"

[ "$ORIGEN" != "$DEMO" ] || { echo "La base demo debe ser distinta de la de origen"; exit 1; }

existe() { docker compose exec -T db psql -U "$U" -d postgres -tAc "select 1 from pg_database where datname='$1'" </dev/null | grep -q 1; }
existe "$ORIGEN" || { echo "No existe la base '$ORIGEN'"; exit 1; }
if existe "$DEMO"; then
  read -r -p "La base '$DEMO' ya existe y se reemplazará. ¿Continuar? [s/N] " ok
  [ "$ok" = "s" ] || [ "$ok" = "S" ] || exit 1
fi

docker compose stop odoo
trap 'docker compose start odoo >/dev/null' EXIT

docker compose exec -T db dropdb -U "$U" --if-exists "$DEMO"
docker compose exec -T db createdb -U "$U" -O "$U" -T "$ORIGEN" "$DEMO"
docker compose exec -T db psql -U "$U" -d "$DEMO" -qc \
  "update ir_config_parameter set value = gen_random_uuid()::text where key in ('database.uuid', 'database.secret');"
docker compose run --rm -T --no-deps --entrypoint "" odoo bash -c \
  "rm -rf /var/lib/odoo/filestore/$DEMO && cp -a /var/lib/odoo/filestore/$ORIGEN /var/lib/odoo/filestore/$DEMO"

docker compose run --rm -T -e DIAS="$DIAS" odoo \
  odoo shell -d "$DEMO" --no-http --max-cron-threads=0 --log-level=warn --log-handler=simulacion:INFO \
  < scripts/simulacion/simular_operacion.py

echo "Base '$DEMO' lista. Usuarios demo con clave demo2026 (ver README)."
