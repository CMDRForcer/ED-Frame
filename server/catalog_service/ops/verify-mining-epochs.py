"""Real PostgreSQL tests in a disposable isolated schema, never public writes.

Run via stdin inside the API container. Sources arrive as JSON; no installed
code, API route, service, or public table is modified. Synthetic fixtures plus
optional READ-ONLY copies of public mining columns exercise real triggers.
The exact generated schema is dropped in finally, including on failure.
"""

import concurrent.futures
import json
import secrets
import sys
import time
import types

from edframe_catalog.database import connection
from psycopg import sql


def main():
    sources = json.load(sys.stdin)
    schema = "edframe_epoch_test_" + secrets.token_hex(8)
    module = types.ModuleType("edframe_catalog.mining_epochs")
    exec(compile(sources["epochs"], "<isolated-epochs>", "exec"), module.__dict__)
    sys.modules[module.__name__] = module
    namespace = {"__package__": "edframe_catalog", "__file__": __file__}
    exec(compile(sources["revision"], "<isolated-revision>", "exec"), namespace)
    namespace["static_revision"] = lambda: "isolated-consistency-test"
    namespace["catalog"] = lambda: [{"system": "Reference"}]
    read = namespace["mining_revision"]
    query = dict(commodity="platinum", system="", max_age_days=3650, x=0., y=0., z=0.,
                 max_distance=50., limit=5000, include_community_overlaps=False,
                 include_ring_candidates=True)
    passed = []
    def connect():
        conn = connection()
        conn.execute(sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
        conn.execute("SET statement_timeout = '60s'")
        conn.execute("SET lock_timeout = '3s'")
        conn.commit()
        return conn
    def check(name, condition):
        assert condition, name
        passed.append(name)
    def revision(conn, **changes):
        return read(conn, {**query, **changes})
    def site(conn, identity, name="Local", x=0, stamp=None):
        conn.execute("""INSERT INTO mining_sites
            (identity, system_name, x, y, z, ring_name, evidence, source, observed_at, received_at)
            VALUES (%s, %s, %s, 0, 0, 'A Ring', 'test', 'synthetic',
                    COALESCE(%s::timestamptz, now()), now())""", (identity, name, x, stamp))
    with connection() as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        with connect() as conn:
            conn.execute("""
                CREATE TABLE systems (LIKE public.systems INCLUDING ALL);
                CREATE TABLE mining_sites (LIKE public.mining_sites INCLUDING ALL);
                CREATE TABLE mining_yield_samples (LIKE public.mining_yield_samples INCLUDING ALL);
                ALTER TABLE mining_yield_samples ADD FOREIGN KEY (site_identity)
                    REFERENCES mining_sites(identity) ON DELETE CASCADE;
                CREATE TABLE mining_yield_materials (LIKE public.mining_yield_materials INCLUDING ALL);
                ALTER TABLE mining_yield_materials ADD FOREIGN KEY (sample_id)
                    REFERENCES mining_yield_samples(sample_id) ON DELETE CASCADE;
                CREATE TABLE ring_reference_metadata (LIKE public.ring_reference_metadata INCLUDING ALL);
            """)
            # A stable older age floor prevents unrelated, freshly inserted
            # rows changing the conservative age boundary in regional tests.
            site(conn, "age-floor", "Far", 10000, "2020-01-01T00:00:00Z")
            site(conn, "base")
            module.install_mining_epochs(conn, ["Reference"], schema=schema)
        with connect() as conn:
            original = revision(conn)
            check("stable_read", original == revision(conn))
            site(conn, "transient")
            conn.execute("DELETE FROM mining_sites WHERE identity='transient'")
            check("insert_delete_tombstone", original != revision(conn))
            conn.commit()
            original = revision(conn)
            conn.execute("UPDATE mining_sites SET evidence='updated' WHERE identity='base'")
            check("site_update", original != revision(conn))
            conn.rollback()
            check("rollback_restores_revision", original == revision(conn))
            conn.rollback()
            site(conn, "outside", "Outside", 10000)
            conn.commit()
            check("unrelated_region_does_not_invalidate", original == revision(conn))
            conn.rollback()
            conn.execute("""INSERT INTO mining_yield_samples
                (sample_id,site_identity,system_name,ring_name,observed_at,received_at,source)
                VALUES ('sample','base','Wrong Reported Name','A Ring',now(),now(),'synthetic')""")
            before = revision(conn)
            conn.execute("INSERT INTO mining_yield_materials VALUES ('sample','platinum',30)")
            check("material_insert_fk_authoritative", before != revision(conn))
            before = revision(conn)
            conn.execute("INSERT INTO mining_yield_materials VALUES ('sample','platinum',30) ON CONFLICT DO NOTHING")
            check("duplicate_observation_does_not_invalidate", before == revision(conn))
            before = revision(conn)
            conn.execute("""INSERT INTO mining_sites SELECT * FROM mining_sites WHERE identity='base'
                ON CONFLICT (identity) DO UPDATE SET evidence=excluded.evidence WHERE FALSE""")
            check("ignored_old_site_update_does_not_invalidate", before == revision(conn))
            before = revision(conn)
            conn.execute("UPDATE mining_yield_materials SET proportion=60")
            check("material_update", before != revision(conn))
            before = revision(conn)
            conn.execute("DELETE FROM mining_yield_materials")
            check("material_delete", before != revision(conn))
            conn.execute("INSERT INTO mining_yield_materials VALUES ('sample','platinum',30)")
            before = revision(conn)
            conn.execute("DELETE FROM mining_yield_samples WHERE sample_id='sample'")
            check("sample_cascade_delete", before != revision(conn))
            before = revision(conn)
            conn.execute("""INSERT INTO ring_reference_metadata
                (system_name,ring_name,system_address,ring_type,reserve_level,source,observed_at,provenance,ring_snapshot)
                VALUES ('Local','A Ring',1,'Metallic','Pristine','synthetic',now(),'{}','{}')""")
            check("metadata_insert", before != revision(conn))
            before = revision(conn)
            conn.execute("UPDATE ring_reference_metadata SET reserve_level='Major'")
            check("metadata_update", before != revision(conn))
            before = revision(conn)
            conn.execute("DELETE FROM ring_reference_metadata")
            check("metadata_delete", before != revision(conn))
            before = revision(conn)
            conn.execute("UPDATE mining_sites SET x=5000 WHERE identity='base'")
            check("move_out_keeps_old_footprint", before != revision(conn))
            before = revision(conn, x=5000.)
            conn.execute("UPDATE mining_sites SET x=0 WHERE identity='base'")
            check("move_back_keeps_new_footprint", before != revision(conn, x=5000.))
            before = revision(conn)
            site(conn, "renamed", "Renamed", 0)
            conn.execute("UPDATE mining_sites SET system_name='Other' WHERE identity='renamed'")
            check("name_change_old_new", before != revision(conn))
            conn.commit()
        # Uncommitted data/counters are invisible to another session and to a
        # previously established RR snapshot; commit publishes both together.
        with connect() as reader, connect() as writer:
            reader.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            before = revision(reader)
            writer.execute("UPDATE mining_sites SET evidence='committed' WHERE identity='base'")
            check("uncommitted_invisible", before == revision(reader))
            writer.commit()
            check("repeatable_read_consistent", before == revision(reader))
            reader.commit()
            check("commit_invalidates_next_snapshot", before != revision(reader))
        with connect() as conn:
            before = revision(conn)
            module.install_mining_epochs(conn, ["Reference"], schema=schema)
            check("reinstall_retains_counters", before == revision(conn))
            module.install_mining_epochs(conn, ["Reference"], schema=schema, rotate=True)
            check("restore_rotation_invalidates", before != revision(conn))
            before = revision(conn)
            conn.execute("TRUNCATE mining_yield_materials")
            check("truncate_invalidates", before != revision(conn))
            before = revision(conn)
            site(conn, "unknown", "Unknown", None)
            check("unknown_position_conservative", before != revision(conn))
            before = revision(conn)
            conn.execute("INSERT INTO systems (name,system_address,x,y,z,observed_at) VALUES ('Unrelated',1,0,0,0,now())")
            check("unrelated_system_update_ignored", before == revision(conn))
            before = revision(conn, include_community_overlaps=True)
            conn.execute("INSERT INTO systems (name,system_address,x,y,z,observed_at) VALUES ('Reference',2,0,0,0,now())")
            check("reference_position_insert", before != revision(conn, include_community_overlaps=True))
            before = revision(conn, include_community_overlaps=True)
            conn.execute("UPDATE systems SET x=1000 WHERE name='Reference'")
            check("reference_position_move", before != revision(conn, include_community_overlaps=True))
            before = revision(conn, include_community_overlaps=True)
            conn.execute("DELETE FROM systems WHERE name='Reference'")
            check("reference_position_delete", before != revision(conn, include_community_overlaps=True))
            before = revision(conn, max_age_days=1)
            site(conn, "expiring", "Age Test", 0, "2026-10-01T00:00:00Z")
            # Explicit DB time is injected ONLY into the isolated query to
            # cross the age floor without a 24-hour sleep or source mutation.
            class AtTime:
                def __init__(self, stamp): self.stamp = stamp
                def execute(self, text, values):
                    return conn.execute(text.replace("NOW()", "TIMESTAMPTZ '" + self.stamp + "'"), values)
            q = {**query, "max_age_days": 1}
            first = read(AtTime("2026-10-01T23:59:59Z"), q)
            second = read(AtTime("2026-10-02T00:00:01Z"), q)
            check("expiry_without_mutation", first != second)
            conn.commit()
        with connect() as conn:
            migration_before = revision(conn)
        original_sql = module.trigger_sql
        module.trigger_sql = lambda _: "SELECT * FROM deliberately_missing_migration_fixture"
        try:
            with connect() as conn:
                module.install_mining_epochs(conn, ["Reference"], schema=schema)
        except Exception as exc:
            assert type(exc).__name__ == 'UndefinedTable', str(exc)
        else:
            raise AssertionError("Injected migration failure did not fail")
        finally:
            module.trigger_sql = original_sql
        with connect() as conn:
            check("failed_migration_rolls_back_ready_and_counters", migration_before == revision(conn))
        def concurrent_update(i):
            with connect() as conn:
                conn.execute("UPDATE mining_sites SET evidence=%s WHERE identity='base'", (str(i),))
        with connect() as conn:
            before = conn.execute("SELECT revision FROM mining_revision_systems WHERE system_name='local'").fetchone()["revision"]
            cell_before = conn.execute("SELECT revision FROM mining_revision_cells WHERE cx=0 AND cy=0 AND cz=0").fetchone()["revision"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(concurrent_update, range(10)))
        with connect() as conn:
            after = conn.execute("SELECT revision FROM mining_revision_systems WHERE system_name='local'").fetchone()["revision"]
            check("concurrent_commits_no_lost_updates", after == before + 10)
            cell_after = conn.execute("SELECT revision FROM mining_revision_cells WHERE cx=0 AND cy=0 AND cz=0").fetchone()["revision"]
            check("concurrent_cell_counters_no_lost_updates", cell_after == cell_before + 10)
            site(conn, "independent", "Independent", 0)
        with connect() as conn:
            cell_before = conn.execute("SELECT revision FROM mining_revision_cells WHERE cx=0 AND cy=0 AND cz=0").fetchone()["revision"]
        def independent_update(i):
            with connect() as conn:
                conn.execute("UPDATE mining_sites SET evidence=%s WHERE identity=%s",
                             (str(i), "base" if i % 2 else "independent"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(independent_update, range(10)))
        with connect() as conn:
            cell_after = conn.execute("SELECT revision FROM mining_revision_cells WHERE cx=0 AND cy=0 AND cz=0").fetchone()["revision"]
            check("independent_systems_same_cell_no_lost_commits", cell_after == cell_before + 10)
        print(json.dumps({"isolatedSchema": schema, "checks": passed, "passed": len(passed)}), flush=True)
        if sources.get("benchmark"):
            benchmark(connect, module, namespace, schema, sources)
        elif sources.get("api") and sources.get("pages"):
            from tempfile import TemporaryDirectory
            baseline, pages_module, isolated_api = load_frozen_test_api(connect, namespace, sources)
            with TemporaryDirectory(prefix="edframe-frozen-test-") as directory:
                verify_frozen_yield_fixture(connect, isolated_api, baseline, pages_module, directory)
            print(json.dumps({"latestFrozenSourceIntegrity": True, "pageTestFilesRemoved": True}), flush=True)
    finally:
        with connection() as admin:
            admin.execute("SET LOCAL lock_timeout = '3s'")
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        print(json.dumps({"isolatedSchemaRemoved": schema, "publicTablesModified": False}), flush=True)


def benchmark(connect, module, namespace, schema, sources):
    # Public read sources only; all copies and DML stay in the isolated schema.
    with connect() as conn:
        conn.execute("SET LOCAL statement_timeout = '120s'")
        conn.execute("""TRUNCATE mining_sites CASCADE;
            ALTER TABLE mining_sites DISABLE TRIGGER USER;
            INSERT INTO mining_sites SELECT * FROM public.mining_sites;
            ALTER TABLE mining_sites ENABLE TRIGGER USER;""")
        # The temporary copied data is not served; atomically backfill before
        # any proof, exactly as the offline production installation would.
        started = time.monotonic()
        module.install_mining_epochs(conn, ["Reference"], schema=schema)
        print(json.dumps({"backfillSeconds":round(time.monotonic()-started,4)}),flush=True)
        conn.execute("ANALYZE mining_sites; ANALYZE mining_revision_footprints; ANALYZE mining_revision_systems; ANALYZE mining_revision_cells")
        conn.execute("INSERT INTO mining_revision_references VALUES ('hip 104026') ON CONFLICT DO NOTHING")
    query = dict(commodity="platinum", system="", max_age_days=3650,
                 x=110.9375,y=-113.0625,z=41.21875,max_distance=250.,limit=5000,
                 include_ring_candidates=True,include_community_overlaps=False)
    with connect() as conn:
        count = conn.execute("SELECT count(*) AS n FROM mining_sites").fetchone()["n"]
        sizes = conn.execute("""SELECT sum(pg_total_relation_size(oid)) AS bytes
            FROM pg_class WHERE relnamespace=%s::regnamespace AND relname LIKE 'mining_revision_%%'
            AND relkind='r'""", (schema,)).fetchone()
        for radius in (50.,250.,500.):
            timings=[]
            for _ in range(4):
                started=time.monotonic()
                namespace["mining_revision"](conn, {**query,"max_distance":radius})
                timings.append(round(time.monotonic()-started,4))
            print(json.dumps({"markerBenchmark":True,"radius":radius,"sites":count,
                              "seconds":timings,"markerBytes":int(sizes["bytes"] or 0)}),flush=True)
            started=time.monotonic()
            namespace["mining_content_revision"](conn, {**query,"max_distance":radius})
            print(json.dumps({"contentProofSeconds":round(time.monotonic()-started,4),
                              "radius":radius}),flush=True)
    if sources.get("api") and sources.get("pages"):
        verify_frozen_handler(connect, namespace, query, sources)
    elif sources.get("handler"):
        verify_handler(connect, namespace, query, sources["handler"])
    with connect() as conn:
        started=time.monotonic()
        conn.execute("UPDATE mining_sites SET evidence=evidence WHERE identity IN (SELECT identity FROM mining_sites LIMIT 1000)")
        print(json.dumps({"bulk1000UpdateSeconds":round(time.monotonic()-started,4)}),flush=True)
        identities = [r['identity'] for r in conn.execute("SELECT identity FROM mining_sites LIMIT 200").fetchall()]
        for active in (False,True):
            with conn.transaction(force_rollback=True):
                if not active:
                    conn.execute("ALTER TABLE mining_sites DISABLE TRIGGER USER")
                started=time.monotonic()
                for identity in identities:
                    conn.execute("UPDATE mining_sites SET evidence=evidence WHERE identity=%s",(identity,))
                print(json.dumps({"individual200UpdateSeconds":round(time.monotonic()-started,4),
                                  "markersActive":active}),flush=True)


def load_frozen_test_api(connect, namespace, sources):
    """Load source in this disposable child process, never installed workers."""
    from edframe_catalog import api as deployed_api
    baseline = deployed_api.search_sites
    deployed_api.connection = connect
    deployed_api.MINING_SNAPSHOT_PROTOCOL_ENABLED = False
    pages_module = types.ModuleType("edframe_catalog.mining_pages")
    exec(compile(sources["pages"], "<isolated-pages>", "exec"), pages_module.__dict__)
    sys.modules[pages_module.__name__] = pages_module
    revision_module = types.ModuleType("edframe_catalog.mining_revision")
    revision_module.__dict__.update(namespace)
    sys.modules[revision_module.__name__] = revision_module
    isolated_api = types.ModuleType("edframe_catalog.frozen_test_api")
    isolated_api.__package__ = "edframe_catalog"
    exec(compile(sources["api"], "<isolated-api>", "exec"), isolated_api.__dict__)
    isolated_api.connection = connect
    isolated_api.MINING_SNAPSHOT_PROTOCOL_ENABLED = True
    isolated_api.static_revision = lambda: "c" * 64
    return baseline, pages_module, isolated_api


def verify_frozen_handler(connect, namespace, query, sources):
    from pathlib import Path
    from tempfile import TemporaryDirectory
    import orjson
    from fastapi import HTTPException
    baseline, pages_module, isolated_api = load_frozen_test_api(connect, namespace, sources)
    optimized = isolated_api.search_sites
    arguments = {**query, "limit": 1000, "regional_page_size": 5000, "offset": 0}

    def normalized(rows):
        # Compare actual HTTP projections, including original source datetimes.
        return orjson.loads(orjson.dumps(rows))

    def fetch(handler, args, *, change=None):
        rows, references, timings = [], [], []
        args = dict(args)
        while True:
            started = time.monotonic()
            result = handler(**args)
            timings.append(round(time.monotonic() - started, 4))
            rows.extend(result["results"])
            references.extend(result["communityReferences"])
            if len(timings) == 1 and change:
                change(result)
            if not result["hasMore"] or result["nextOffset"] >= 50000:
                break
            assert len(timings) < 50, "bounded paging"
            args.update(cursor=result["nextCursor"], offset=result["nextOffset"])
            if args.get("snapshot_protocol"):
                args.pop("known_revision", None)
                args.update(snapshot_revision=result["revision"], snapshot_static=result["snapshotStatic"])
        return normalized(rows), normalized(references), result, timings

    with TemporaryDirectory(prefix="edframe-frozen-test-") as directory:
        path = Path(directory, "pages.sqlite3")
        pages = pages_module.FrozenPages(path)
        isolated_api.configured_pages = lambda: pages
        for radius in (50., 250., 500.):
            scoped = {**arguments, "max_distance": radius}
            before = fetch(baseline, scoped)
            after = fetch(optimized, {**scoped, "snapshot_protocol": 1})
            assert before[:2] == after[:2], "Changed rows/references/order"
            assert after[2]["snapshotComplete"] == (not after[2]["hasMore"])
            print(json.dumps({"frozenComparison": True, "radius": radius, "rows": len(after[0]),
                "legacyPageSeconds": before[3], "frozenPageSeconds": after[3],
                "legacyTotalSeconds": round(sum(before[3]), 4),
                "frozenTotalSeconds": round(sum(after[3]), 4),
                "complete": after[2]["snapshotComplete"], "identicalRowsReferencesOrder": True}), flush=True)

        frozen_before = fetch(optimized, {**arguments, "snapshot_protocol": 1})
        start = time.monotonic()
        unchanged = optimized(**{**arguments, "snapshot_protocol": 1,
                                 "known_revision": frozen_before[2]["revision"]})
        assert unchanged["notModified"] and unchanged["snapshotComplete"] and not unchanged["results"]
        print(json.dumps({"unchangedConfirmationSeconds": round(time.monotonic() - start, 4)}), flush=True)

        def mutate(_first):
            with connect() as writer:
                writer.execute("""INSERT INTO mining_sites
                    (identity,system_name,x,y,z,ring_name,ring_type,evidence,source,observed_at,received_at)
                    VALUES ('test-frozen-update','Test Frozen',%s,%s,%s,'A Ring','Metallic',
                            'test','synthetic',now(),now())""", (query['x'], query['y'], query['z']))
        frozen_churn = fetch(optimized, {**arguments, "snapshot_protocol": 1}, change=mutate)
        assert frozen_churn[:2] == frozen_before[:2], "Live update changed frozen pages"
        # A new search must immediately see the write despite the page TTL.
        fresh = fetch(optimized, {**arguments, "snapshot_protocol": 1,
                      "known_revision": frozen_before[2]["revision"]})
        assert fresh[2]["revision"] != frozen_before[2]["revision"] and not fresh[2]["notModified"]
        assert any(row['siteIdentity'] == 'test-frozen-update' for row in fresh[0])
        with connect() as writer:
            writer.execute("DELETE FROM mining_sites WHERE identity='test-frozen-update'")
        reverted = optimized(**{**arguments, "snapshot_protocol": 1,
                               "known_revision": fresh[2]["revision"]})
        assert reverted["revision"] != fresh[2]["revision"]
        assert not any(row['siteIdentity'] == 'test-frozen-update' for row in reverted["results"])
        print(json.dumps({"betweenPagesUpdatesPreserveFrozenRows": True,
                          "nextSearchSeesInsertAndDelete": True}), flush=True)

        # No PG connection is needed after the first page, even with tiny final
        # pages. A second API process/instance uses the same immutable SQLite DB.
        first = optimized(**{**arguments, "snapshot_protocol": 1})
        conn_factory = isolated_api.connection
        isolated_api.connection = lambda: (_ for _ in ()).throw(AssertionError("Unexpected live page query"))
        isolated_api.configured_pages = lambda: pages_module.FrozenPages(path)
        page = optimized(**{**arguments, "snapshot_protocol": 1,
            "regional_page_size": 17, "cursor": first["nextCursor"], "offset": first["nextOffset"],
            "snapshot_revision": first["revision"], "snapshot_static": first["snapshotStatic"]})
        assert len(page["results"]) == 17
        assert page["results"] == frozen_before[0][5000:5017]
        isolated_api.connection = conn_factory
        print(json.dumps({"continuationNoPostgresAndCrossInstance": True,
                          "pageDatabaseBytes": path.stat().st_size}), flush=True)

        # Compare the community reference path too, including missing-ring
        # candidates and metadata source timestamps, not just bare ring rows.
        community_args = {**arguments, "include_community_overlaps": True}
        community_old = fetch(baseline, community_args)
        community_new = fetch(optimized, {**community_args, "snapshot_protocol": 1})
        assert community_old[:2] == community_new[:2], "Changed community/yield projection"
        print(json.dumps({"communityRowsReferencesOrderIdentical": True,
                          "references": len(community_new[1])}), flush=True)

        verify_frozen_yield_fixture(connect, isolated_api, baseline, pages_module, directory)

        # Graceful capacity failure, no eviction of unexpired client chains.
        pages.capacity = 1
        isolated_api.configured_pages = lambda: pages
        try:
            optimized(**{**arguments, "commodity": "osmium", "snapshot_protocol": 1})
            raise AssertionError("Expected admission limit")
        except HTTPException as exc:
            assert exc.status_code == 503
        print(json.dumps({"capacityFailure503PreservesActivePages": True}), flush=True)
    print(json.dumps({"pageTestFilesRemoved": True, "installedApiModified": False}), flush=True)


def verify_frozen_yield_fixture(connect, api, baseline, pages_module, directory):
    """A commit DURING materialization cannot mix yields or fallback metadata."""
    import orjson
    from pathlib import Path
    name = "Test Frozen Yield Fixture"
    with connect() as conn:
        for i in range(2):
            conn.execute("""INSERT INTO mining_sites
                (identity,system_name,x,y,z,ring_name,ring_type,evidence,source,observed_at,received_at)
                VALUES (%s,%s,0,0,0,%s,'Metallic','test','synthetic',now(),now())""",
                         ("frozen-fixture-" + str(i), name, name + " " + str(i) + " A Ring"))
        conn.execute("""INSERT INTO mining_yield_samples
            (sample_id,site_identity,system_name,ring_name,observed_at,received_at,source)
            VALUES ('frozen-hit','frozen-fixture-0',%s,%s,now(),now(),'synthetic'),
                   ('frozen-miss','frozen-fixture-0',%s,%s,now(),now(),'synthetic')""",
                     (name, name + " 0 A Ring", name, name + " 0 A Ring"))
        conn.execute("INSERT INTO mining_yield_materials VALUES ('frozen-hit','platinum',30)")
        conn.execute("""INSERT INTO ring_reference_metadata
            (system_name,ring_name,system_address,ring_type,reserve_level,source,observed_at,provenance,ring_snapshot)
            VALUES (%s,%s,1,'Metallic','Pristine','synthetic',now(),'{}','{}')""", (name, name + " 0 A Ring"))
    args = dict(system=name, commodity="platinum", max_age_days=3650,
                include_ring_candidates=True, limit=1, offset=0)
    def all_rows(handler, protocol=False):
        current = {**args, **({"snapshot_protocol": 1} if protocol else {})}
        rows = []
        while True:
            result = handler(**current)
            rows.extend(result['results'])
            if not result['hasMore']:
                break
            current.update(cursor=result['nextCursor'], offset=result['nextOffset'])
            if protocol:
                current.update(snapshot_revision=result['revision'], snapshot_static=result['snapshotStatic'])
        return orjson.loads(orjson.dumps(rows))
    expected = all_rows(baseline)
    mutation = [False]
    class Stream:
        def __init__(self, wrapped): self.wrapped = wrapped
        def __enter__(self): self.wrapped.__enter__(); return self
        def __exit__(self, *args): return self.wrapped.__exit__(*args)
        def execute(self, *args): return self.wrapped.execute(*args)
        def fetchmany(self, size):
            batch = self.wrapped.fetchmany(size)
            if batch and not mutation[0]:
                mutation[0] = True
                with connect() as writer:
                    writer.execute("UPDATE mining_yield_materials SET proportion=60 WHERE sample_id='frozen-hit'")
                    writer.execute("UPDATE ring_reference_metadata SET reserve_level='Major' WHERE system_name=%s", (name,))
            return batch
    class Connection:
        def __init__(self): self.wrapped = connect()
        def __enter__(self): self.wrapped.__enter__(); return self
        def __exit__(self, *args): return self.wrapped.__exit__(*args)
        def execute(self, *args): return self.wrapped.execute(*args)
        def cursor(self, **kwargs): return Stream(self.wrapped.cursor(**kwargs))
    original_factory, original_pages = api.connection, api.configured_pages
    try:
        api.connection = Connection
        api.configured_pages = lambda: pages_module.FrozenPages(Path(directory, "fixture.sqlite3"))
        frozen = all_rows(api.search_sites, True)
        assert mutation[0] and frozen == expected, "Mixed yield/metadata during snapshot materialization"
        hit = next(row for row in frozen if row['siteIdentity'] == 'frozen-fixture-0')
        assert hit['prospectorSampleCount'] == 2 and hit['yieldStats'][0]['averageProportion'] == 30
        assert hit['reserveLevel'] == 'Pristine'
        api.connection = original_factory
        changed = all_rows(api.search_sites, True)
        hit = next(row for row in changed if row['siteIdentity'] == 'frozen-fixture-0')
        assert hit['yieldStats'][0]['averageProportion'] == 60 and hit['reserveLevel'] == 'Major'
        assert frozen[0]['observedAt'] == changed[0]['observedAt'], "Source age re-dated"
        print(json.dumps({"commitDuringBuildKeepsOriginalYieldAndMetadata": True,
                          "nextSearchUpdatesYieldsMetadataWithoutRedating": True,
                          "zeroSamplesRetained": True}), flush=True)
    finally:
        api.connection, api.configured_pages = original_factory, original_pages
        with connect() as conn:
            conn.execute("DELETE FROM mining_sites WHERE system_name=%s", (name,))
            conn.execute("DELETE FROM ring_reference_metadata WHERE system_name=%s", (name,))


def verify_handler(connect, namespace, query, handler_source):
    from edframe_catalog import api
    baseline = api.search_sites
    api.connection = connect
    api.MINING_SNAPSHOT_PROTOCOL_ENABLED = True
    api.static_revision = namespace["static_revision"]
    api._snapshot_revision = namespace["mining_revision"]
    exec(compile(handler_source, "<isolated-handler>", "exec"), api.__dict__)
    optimized = api.search_sites
    def fetch(handler, protocol=False):
        arguments = {**query, "limit":1000,"regional_page_size":5000,"offset":0}
        if protocol: arguments['snapshot_protocol']=1
        rows=[]
        pages=0
        while True:
            result = handler(**arguments)
            rows.extend(result['results'])
            pages+=1
            if not result['hasMore']: break
            assert pages<50, "bounded paging"
            arguments['cursor']=result['nextCursor']
            arguments['offset']=result['nextOffset']
            if protocol:
                arguments.update(snapshot_revision=result['revision'],snapshot_static=result['snapshotStatic'])
        return rows,pages,result
    saved=[]
    for handler, protocol in ((baseline,False),(optimized,True)):
        started=time.monotonic()
        rows,pages,result=fetch(handler,protocol)
        saved.append((rows,result))
        print(json.dumps({"handlerMarkers":protocol,"rows":len(rows),"pages":pages,
                          "seconds":round(time.monotonic()-started,4)}),flush=True)
    assert saved[0][0]==saved[1][0], "Changed rows/order"
    started=time.monotonic()
    unchanged=optimized(**{**query,"limit":1000,"regional_page_size":5000,"offset":0,
                          "snapshot_protocol":1,"known_revision":saved[1][1]['revision']})
    assert unchanged['notModified'] and unchanged['snapshotComplete'] and not unchanged['results']
    print(json.dumps({"identicalRowsOrder":True,"unchangedConfirmationSeconds":
                      round(time.monotonic()-started,4)}),flush=True)
    # A real between-pages insert AND delete must invalidate even though the
    # original row contents have returned. Only isolated synthetic rows change.
    arguments = {**query,"limit":1000,"regional_page_size":5000,"offset":0,"snapshot_protocol":1}
    first=optimized(**arguments)
    assert first['hasMore'], "Churn test needs multiple pages"
    arguments.update(cursor=first['nextCursor'],offset=first['nextOffset'],
                     snapshot_revision=first['revision'],snapshot_static=first['snapshotStatic'])
    with connect() as writer:
        writer.execute("""INSERT INTO mining_sites
            (identity,system_name,x,y,z,ring_name,ring_type,evidence,source,observed_at,received_at)
            VALUES ('test-between-pages','Test Transient',%s,%s,%s,'A Ring','Metallic','test','synthetic',now(),now())""",
                       (query['x'],query['y'],query['z']))
    optimized(**arguments)
    with connect() as writer:
        writer.execute("DELETE FROM mining_sites WHERE identity='test-between-pages'")
    from fastapi import HTTPException
    try:
        while True:
            result=optimized(**arguments)
            if not result['hasMore']: raise AssertionError("Transient change incorrectly accepted")
            arguments.update(cursor=result['nextCursor'],offset=result['nextOffset'])
    except HTTPException as exc:
        assert exc.status_code==409
    print(json.dumps({"transientBetweenPagesRejected":True}),flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"failed":type(exc).__name__,"detail":str(exc)}),flush=True)
        raise SystemExit(1)
