#!/usr/bin/env bash
# Restaura un respaldo hecho con scripts/backup.sh. REEMPLAZA la base indicada.
# Uso: scripts/restore.sh backups/agencia-AAAAMMDD-HHMMSS [nombre_base]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

DIR="${1:?Indique la carpeta del respaldo}"
DB="${2:-agencia}"
U="${POSTGRES_USER:-odoo}"
[ -f "$DIR/db.dump" ] && [ -f "$DIR/filestore.tar.gz" ] || { echo "Respaldo incompleto en $DIR"; exit 1; }

read -r -p "Se reemplazará la base '$DB' con $DIR. ¿Continuar? [s/N] " ok
[ "$ok" = "s" ] || [ "$ok" = "S" ] || exit 1

docker compose stop odoo
docker compose exec -T db dropdb -U "$U" --if-exists "$DB"
docker compose exec -T db createdb -U "$U" -O "$U" "$DB"
docker compose exec -T db pg_restore -U "$U" -d "$DB" --no-owner < "$DIR/db.dump"
docker compose run --rm -T --no-deps --entrypoint "" odoo bash -c \
  "rm -rf /var/lib/odoo/filestore/$DB && mkdir -p /var/lib/odoo/filestore/$DB && tar -C /var/lib/odoo/filestore/$DB --strip-components=1 -xzf -" \
  < "$DIR/filestore.tar.gz"
docker compose start odoo

echo "Base '$DB' restaurada desde $DIR"
