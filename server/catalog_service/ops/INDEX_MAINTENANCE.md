# Capacity-aware online index maintenance

The catalog retains last-known facts, so ordinary age-based data deletion is
not a capacity policy. PostgreSQL VACUUM makes space reusable but does not
compact a partially populated B-tree into a smaller on-disk file.

`catalog-index-maintenance.py` defaults to a check. `--run` permits a bounded
`REINDEX INDEX CONCURRENTLY` of the three fixed secondary indexes only. It
never drops indexes manually, deletes catalog rows, removes backup archives or
prunes Docker images. The emergency offline repair on 31 October used a
separately reviewed procedure; that procedure is not an automatic action.

The timer checks every six hours. At 12 GiB or more free it uses inexpensive
catalog metadata. Below that threshold it measures actual leaf density in a
transaction that rolls back any temporary diagnostic extension/schema.
Only indexes at least 512 MiB and below 40% leaf fill are candidates.

Before a rebuild, the worker requires the expected backup filesystem UUID,
a completed full backup from the last 30 hours, a successful full pg_restore
archive read, and at least the larger of 5 GiB or the estimated index/WAL
headroom. It rechecks candidates after archive verification and rebuilds at
most one index per cycle. Database maintenance memory is 64 MiB with parallel
maintenance disabled; waits and execution time are bounded. A two-second
space/time watchdog can terminate only its own uniquely named database session.

An interrupted or failed rebuild requires manual inspection; the worker never
blindly drops an invalid index or retries through its review marker. Its lock
is shared with private admin maintenance, and pending/review-required admin
jobs block the scheduled worker. Existing daily backup and weekly VACUUM
services keep their previous schedules and retention rules.

Configuration is explicit and fails closed if absent. Create the root-only
file `/etc/edframe-catalog-index-maintenance.env` containing
`EDFRAME_BACKUP_UUID=<UUID of the dedicated backup filesystem>`, install the
service/timer alongside existing catalog units, and enable the timer only
after a successful check. Do not substitute the root filesystem when the
backup mount is absent. The operational status is written to
`/var/lib/edframe-catalog/index-maintenance/latest.json`.

Compaction controls avoidable bloat; genuine growth of the retained catalog
still requires adequate disk capacity. A capacity refusal is an operator action,
not permission to discard old facts or old backups.
