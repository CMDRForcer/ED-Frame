#!/bin/sh
set -eu

SERVICE_DIR=/opt/edframe-catalog/server/catalog_service
cd "$SERVICE_DIR"
set -a
. ./.env
set +a

# Every catalog table keeps one last-known row per stable identity.  Age makes
# a fact unsuitable for a live recommendation, but does not make the fact
# worthless.  Route APIs apply freshness filters; maintenance must therefore
# never erase markets, systems, stations, inventories, BGS snapshots, mining
# sites or yield samples merely because an upstream source has been quiet.
#
# Signals are the exception: their producer supplies an explicit expiry and
# the API never serves them after that point.  Removing them cannot turn known
# current state into UNKNOWN.
docker compose exec -T db psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --command "DELETE FROM state_signals WHERE expires_at <= NOW(); DELETE FROM collector_schema_metrics_hourly WHERE bucket_start < NOW() - INTERVAL '8 days';"
docker compose exec -T db psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set ON_ERROR_STOP=1 \
    --command "VACUUM (ANALYZE) markets, station_module_offers, station_ship_offers, state_bgs_snapshots, state_signals, collector_schema_metrics_hourly;"

disk_usage=$(df -P "$SERVICE_DIR" | awk 'NR == 2 {gsub(/%/, "", $5); print $5}')
case "$disk_usage" in
    ''|*[!0-9]*)
        echo "WARNING: unable to determine ED-Frame catalog disk usage" >&2
        ;;
    *)
        if [ "$disk_usage" -ge 85 ]; then
            echo "CRITICAL: ED-Frame catalog disk usage is ${disk_usage}% (threshold 85%)" >&2
            exit 2
        fi
        if [ "$disk_usage" -ge 70 ]; then
            echo "WARNING: ED-Frame catalog disk usage is ${disk_usage}% (threshold 70%)" >&2
        else
            echo "ED-Frame catalog disk usage is ${disk_usage}%"
        fi
        ;;
esac
