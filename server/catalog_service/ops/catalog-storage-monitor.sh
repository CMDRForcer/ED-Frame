#!/bin/sh
set -eu
cd /opt/edframe-catalog/server/catalog_service
set -a
. ./.env
set +a
exec python3 ops/catalog-storage-monitor.py
