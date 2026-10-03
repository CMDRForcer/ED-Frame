#!/bin/sh
set -eu

SERVICE_DIR=/opt/edframe-catalog/server/catalog_service
cd "$SERVICE_DIR"
set -a
. ./.env
set +a

# Prices and demand older than 90 days are no longer useful for route advice.
# Systems and mining evidence remain durable so an upstream outage does not
# erase known geography.
docker compose exec -T db psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --command "DELETE FROM markets WHERE observed_at < NOW() - INTERVAL '90 days';"
docker compose exec -T db psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --command "VACUUM (ANALYZE) markets;"
