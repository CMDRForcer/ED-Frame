"""Explicit, transactional migration for cheap mining revision markers.

Not part of normal application startup. Run with collector/API writes paused;
the caller must commit the complete installation, never individual steps.
Historical footprints and counters are tombstones, not disposable caches.
"""

import re
from psycopg.pq import TransactionStatus

SCHEMA_VERSION = 1
CELL_SIZE = 128
TABLES = ("systems", "mining_sites", "mining_yield_samples",
          "mining_yield_materials", "ring_reference_metadata")


def _footprints(source):
    return f"""
        INSERT INTO mining_revision_footprints (system_name, cx, cy, cz)
        SELECT DISTINCT lower(system_name), floor(x / {CELL_SIZE})::bigint,
               floor(y / {CELL_SIZE})::bigint, floor(z / {CELL_SIZE})::bigint
        FROM ({source}) positions
        WHERE x BETWEEN -1e12 AND 1e12 AND y BETWEEN -1e12 AND 1e12
          AND z BETWEEN -1e12 AND 1e12
        ORDER BY 1, 2, 3, 4 ON CONFLICT DO NOTHING;
    """


def trigger_sql(schema):
    """One touch per affected system/statement, including OLD and NEW sets.

    Transition tables avoid per-row trigger queries during bulk imports.
    Cascaded yield deletes are also protected by their parent's delete trigger.
    All names are trusted constants; only a validated schema is interpolated.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
        raise ValueError("Invalid revision schema")
    statements = []
    for table in TABLES:
        for event, relations in (("INSERT", ("new_rows",)),
                                 ("UPDATE", ("old_rows", "new_rows")),
                                 ("DELETE", ("old_rows",))):
            source = " UNION ALL ".join(f"SELECT * FROM {name}" for name in relations)
            positions = None
            if table == "mining_sites":
                positions = f"SELECT system_name, x, y, z FROM ({source}) changed"
                names = f"SELECT system_name FROM ({source}) changed"
            elif table == "systems":
                positions = f"""SELECT c.name AS system_name, c.x, c.y, c.z
                    FROM ({source}) c JOIN mining_revision_references r
                    ON r.system_name = lower(c.name)"""
                names = f"SELECT system_name FROM ({positions}) positions"
            elif table == "mining_yield_samples":
                # The FK site is authoritative; retain the reported name too
                # so parent cascades/renames cannot erase the mutation footprint.
                names = f"""SELECT c.system_name FROM ({source}) c UNION
                    SELECT ms.system_name FROM ({source}) c
                    JOIN mining_sites ms ON ms.identity = c.site_identity"""
            elif table == "mining_yield_materials":
                names = f"""SELECT ys.system_name FROM ({source}) c
                    JOIN mining_yield_samples ys USING (sample_id) UNION
                    SELECT ms.system_name FROM ({source}) c
                    JOIN mining_yield_samples ys USING (sample_id)
                    JOIN mining_sites ms ON ms.identity = ys.site_identity"""
            else:
                names = f"SELECT system_name FROM ({source}) changed"
            body = ""
            if positions:
                body = f"""INSERT INTO mining_revision_systems (system_name)
                    SELECT DISTINCT lower(system_name) FROM ({positions}) p
                    ORDER BY 1 ON CONFLICT DO NOTHING;
                """ + _footprints(positions)
            body += f"""
                PERFORM mining_revision_touch(ARRAY(
                    SELECT DISTINCT lower(system_name) FROM ({names}) touched
                    ORDER BY 1));
                RETURN NULL;
            """
            name = f"mining_epoch_{table}_{event.lower()}"
            referencing = " ".join("OLD TABLE AS old_rows" if r == "old_rows"
                                   else "NEW TABLE AS new_rows" for r in relations)
            statements.append(f"""
                CREATE OR REPLACE FUNCTION {name}() RETURNS trigger
                LANGUAGE plpgsql SET search_path TO {schema}, pg_catalog AS $$
                BEGIN {body} END; $$;
                DROP TRIGGER IF EXISTS {name} ON {table};
                CREATE TRIGGER {name} AFTER {event} ON {table}
                REFERENCING {referencing} FOR EACH STATEMENT
                EXECUTE FUNCTION {name}();
            """)
        statements.append(f"""
            DROP TRIGGER IF EXISTS mining_epoch_truncate ON {table};
            CREATE TRIGGER mining_epoch_truncate AFTER TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION mining_revision_truncate();
        """)
    return "\n".join(statements)


def install_mining_epochs(conn, reference_names, *, schema="public", rotate=False):
    """Backfill and install atomically under source-table write locks.

    An explicit rotate is required after a DB restore; previously issued
    revisions must not become valid again when restored counters catch up.
    Reinstallation preserves counters, footprints and the database generation.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
        raise ValueError("Invalid revision schema")
    previous = conn.execute("SELECT current_setting('search_path') AS value").fetchone()["value"]
    conn.execute("SELECT set_config('search_path', %s, true)", (schema + ",pg_catalog",))
    try:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (45444652414,))
        conn.execute("LOCK TABLE " + ", ".join(TABLES) + " IN SHARE ROW EXCLUSIVE MODE")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mining_revision_state (
                singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                schema_version integer NOT NULL,
                generation uuid NOT NULL DEFAULT gen_random_uuid(),
                unknown_revision bigint NOT NULL DEFAULT 0,
                ready boolean NOT NULL DEFAULT FALSE
            );
            INSERT INTO mining_revision_state (schema_version) VALUES (1)
            ON CONFLICT DO NOTHING;
            CREATE TABLE IF NOT EXISTS mining_revision_systems (
                system_name text PRIMARY KEY, revision bigint NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS mining_revision_footprints (
                system_name text NOT NULL REFERENCES mining_revision_systems(system_name),
                cx bigint NOT NULL, cy bigint NOT NULL, cz bigint NOT NULL,
                PRIMARY KEY (system_name, cx, cy, cz)
            );
            CREATE TABLE IF NOT EXISTS mining_revision_references (
                system_name text PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS mining_revision_cells (
                cx bigint NOT NULL, cy bigint NOT NULL, cz bigint NOT NULL,
                revision bigint NOT NULL DEFAULT 1,
                PRIMARY KEY (cx, cy, cz)
            );
        """)
        state = conn.execute("SELECT * FROM mining_revision_state").fetchone()
        if state["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported mining epoch schema")
        conn.execute("UPDATE mining_revision_state SET ready = FALSE")
        # Never remove old references during a rolling deployment. Extra
        # invalidation is safe; missing a dependency is not.
        conn.execute("""INSERT INTO mining_revision_references
            SELECT DISTINCT lower(name) FROM unnest(%s::text[]) name
            ORDER BY 1 ON CONFLICT DO NOTHING""", (sorted(set(reference_names)),))
        conn.execute("""INSERT INTO mining_revision_systems (system_name)
            SELECT lower(system_name) FROM mining_sites UNION
            SELECT lower(system_name) FROM ring_reference_metadata UNION
            SELECT system_name FROM mining_revision_references
            ORDER BY 1 ON CONFLICT DO NOTHING""")
        conn.execute(_footprints("SELECT system_name, x, y, z FROM mining_sites"))
        conn.execute(_footprints("""SELECT s.name AS system_name, s.x, s.y, s.z
            FROM systems s JOIN mining_revision_references r ON r.system_name = lower(s.name)"""))
        conn.execute("""INSERT INTO mining_revision_cells (cx, cy, cz)
            SELECT DISTINCT cx, cy, cz FROM mining_revision_footprints
            ORDER BY 1, 2, 3 ON CONFLICT DO NOTHING""")
        conn.execute(f"""
            CREATE OR REPLACE FUNCTION mining_revision_touch(names text[]) RETURNS void
            LANGUAGE plpgsql SET search_path TO {schema}, pg_catalog AS $$
            BEGIN
                IF cardinality(names) = 0 THEN RETURN; END IF;
                INSERT INTO mining_revision_systems (system_name, revision)
                    SELECT DISTINCT name, 1 FROM unnest(names) name ORDER BY 1
                ON CONFLICT (system_name) DO UPDATE
                    SET revision = mining_revision_systems.revision + 1;
                -- A regional reader hashes only a few grid counters, never
                -- thousands of system names. Retained footprints propagate
                -- every mutation to ALL historical cells of that system.
                INSERT INTO mining_revision_cells (cx, cy, cz, revision)
                    SELECT DISTINCT cx, cy, cz, 1 FROM mining_revision_footprints
                    WHERE system_name = ANY(names) ORDER BY 1, 2, 3
                ON CONFLICT (cx, cy, cz) DO UPDATE
                    SET revision = mining_revision_cells.revision + 1;
                IF EXISTS (SELECT 1 FROM unnest(names) name WHERE NOT EXISTS
                    (SELECT 1 FROM mining_revision_footprints f WHERE f.system_name = name)) THEN
                    UPDATE mining_revision_state SET unknown_revision = unknown_revision + 1;
                END IF;
            END; $$;
            CREATE OR REPLACE FUNCTION mining_revision_truncate() RETURNS trigger
            LANGUAGE plpgsql SET search_path TO {schema}, pg_catalog AS $$
            BEGIN
                UPDATE mining_revision_state SET unknown_revision = unknown_revision + 1;
                RETURN NULL;
            END; $$;
        """)
        conn.execute(trigger_sql(schema))
        conn.execute("UPDATE mining_revision_state SET ready = TRUE" +
                     (", generation = gen_random_uuid()" if rotate else ""))
    finally:
        # A SQL failure already requires caller rollback; do not mask it with
        # a second query in an aborted transaction.
        if conn.info.transaction_status != TransactionStatus.INERROR:
            conn.execute("SELECT set_config('search_path', %s, true)", (previous,))


def main():
    import argparse
    import json
    from .database import connection
    from .mining_overlaps import catalog

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", required=True)
    parser.add_argument("--rotate-after-restore", action="store_true")
    args = parser.parse_args()
    with connection() as conn:
        conn.execute("SET LOCAL lock_timeout = '10s'")
        conn.execute("SET LOCAL statement_timeout = '120s'")
        install_mining_epochs(conn, [r["system"] for r in catalog()],
                              rotate=args.rotate_after_restore)
        state = conn.execute("SELECT schema_version, ready FROM mining_revision_state").fetchone()
        counts = conn.execute("""SELECT
            (SELECT count(*) FROM mining_revision_systems) AS systems,
            (SELECT count(*) FROM mining_revision_footprints) AS footprints""").fetchone()
    print(json.dumps({"installed": True, **state, **counts}))


if __name__ == "__main__":
    main()
