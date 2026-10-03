#!/bin/sh
set -eu

SERVICE_DIR=/opt/edframe-catalog/server/catalog_service
BACKUP_DIR=/var/backups/edframe-catalog

cd "$SERVICE_DIR"
set -a
. ./.env
set +a

install -d -m 700 "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary="$BACKUP_DIR/catalog-$stamp.dump.partial"
target="$BACKUP_DIR/catalog-$stamp.dump"

trap 'rm -f "$temporary"' EXIT
docker compose exec -T db pg_dump \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --format custom \
    --no-owner > "$temporary"

test -s "$temporary"
docker compose exec -T db pg_restore --list < "$temporary" >/dev/null
chmod 600 "$temporary"
mv "$temporary" "$target"
trap - EXIT

find "$BACKUP_DIR" -type f -name 'catalog-*.dump' -mtime +14 -delete
printf 'Created verified catalog backup: %s\n' "$target"
