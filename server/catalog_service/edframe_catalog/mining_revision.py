"""Cheap transactional revisions for consistently paginated mining snapshots."""

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from ed_companion.navigation.mining_commodities import MINING_COMMODITIES
from .mining_overlaps import catalog, imported_system_positions
from .mining_region import regional_box_clause
from .mining_epochs import CELL_SIZE, SCHEMA_VERSION


@lru_cache(maxsize=1)
def static_revision():
    facts = [catalog(), imported_system_positions(), MINING_COMMODITIES]
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True).encode())
    # A deployment changing response/projection rules must also invalidate
    # clients. Processes load their bundled references once, just as the API.
    for name in ("api.py", "mining_revision.py", "mining_epochs.py", "mining_pages.py",
                 "mining_metadata.py", "mining_overlaps.py", "mining_region.py"):
        digest.update(Path(__file__).with_name(name).read_bytes())
    return digest.hexdigest()


def mining_content_revision(conn, query):
    """Read a query-bound digest inside the page's repeatable-read transaction.

    Fingerprint the whole regional domain, not just the current page or
    commodity. Same-system rows outside the sphere can supply missing ring
    metadata; imported references can depend on positions outside the sphere.
    No rows, locks, epochs or mutation triggers are written by this protocol.
    """
    clauses = ["ms.observed_at >= NOW() - (%s * INTERVAL '1 day')"]
    values = [query["max_age_days"]]
    if query["system"]:
        clauses.append("LOWER(ms.system_name) = LOWER(%s)")
        values.append(query["system"].strip())
    coords = [query[k] for k in ("x", "y", "z", "max_distance")]
    if all(v is not None for v in coords):
        clauses.append("POWER(ms.x - %s, 2) + POWER(ms.y - %s, 2) + "
                       "POWER(ms.z - %s, 2) <= POWER(%s, 2)")
        values.extend(coords)
        # GiST helps small spheres; at broad radii its severe cardinality
        # underestimate caused a slower bitmap plan on representative data.
        # Both access paths retain the exact, inclusive sphere predicate.
        if coords[-1] <= 100:
            box_clause, box_values = regional_box_clause(*coords, alias="ms")
            clauses.append(box_clause)
            values.extend(box_values)
    reference_names = sorted({r["system"].casefold() for r in catalog()}) \
        if query["include_community_overlaps"] else []
    scope = conn.execute(f"""
        SELECT md5(COALESCE(string_agg(md5(identity), '' ORDER BY identity), '')) AS membership,
               COALESCE(array_agg(DISTINCT LOWER(ms.system_name)), ARRAY[]::text[]) AS names
        FROM mining_sites ms WHERE {' AND '.join(clauses)}
        """, values).fetchone()
    if (not isinstance(scope, dict) or not isinstance(scope.get("membership"), str)
            or not isinstance(scope.get("names"), list)
            or any(not isinstance(name, str) for name in scope["names"])):
        raise ValueError("Mining region could not be established")
    names = sorted(set(scope["names"]).union(reference_names))
    # Pass real region cardinality to PostgreSQL. ARRAY(SELECT ...) in the
    # earlier CTE plan was estimated as a few names even for 27,000 systems;
    # it chose large random index scans and spilled dependent row sets.
    # Both SELECTs belong to the caller's SAME repeatable-read transaction.
    row = conn.execute("""
        WITH dependencies AS MATERIALIZED (
            SELECT ms.*, ms.xmin::text AS row_version FROM mining_sites ms
            WHERE LOWER(ms.system_name) = ANY(%s)
        ), samples AS MATERIALIZED (
            SELECT ys.*, ys.xmin::text AS row_version FROM mining_yield_samples ys
            JOIN dependencies d ON d.identity = ys.site_identity
        )
        SELECT
            (SELECT md5(COALESCE(string_agg(md5(d::text), '' ORDER BY identity), ''))
             FROM dependencies d) AS sites,
            (SELECT md5(COALESCE(string_agg(md5(s::text), '' ORDER BY sample_id), ''))
             FROM samples s) AS samples,
            (SELECT md5(COALESCE(string_agg(md5(ROW(m, m.xmin)::text), '' ORDER BY m.sample_id, m.commodity), ''))
             FROM mining_yield_materials m JOIN samples s USING (sample_id)) AS materials,
            (SELECT md5(COALESCE(string_agg(md5(ROW(r.system_name, r.ring_name, r.system_address,
                                                  r.ring_type, r.reserve_level, r.source, r.observed_at, r.xmin)::text),
                                          '' ORDER BY r.system_name, r.ring_name), ''))
             FROM ring_reference_metadata r
             WHERE LOWER(r.system_name) = ANY(%s)) AS metadata,
            (SELECT md5(COALESCE(string_agg(md5(ROW(name, system_address, x, y, z, observed_at, xmin)::text),
                                          '' ORDER BY name), ''))
             FROM systems WHERE LOWER(name) = ANY(%s)) AS positions
        """, (names, names, reference_names)).fetchone()
    if isinstance(row, dict):
        row = {**row, "membership": scope["membership"]}
    if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in
            ("membership", "sites", "samples", "materials", "metadata", "positions")):
        raise ValueError("Mining revision could not be established")
    payload = {"query": query, "database": row, "static": static_revision()}
    return "s1-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def mining_revision(conn, query):
    """Hash retained CELL counters, not mining JSON, in the page's RR snapshot.

    Every historical grid cell touched by a system retains its dependency on
    that system's transactional counter, even after moves/deletions. The box
    deliberately over-selects complete cells; exact search results still use
    the original sphere. Unknown positions invalidate conservatively.

    The global oldest eligible timestamp is a cheap indexed age boundary:
    if ANY previously eligible row ages out, this timestamp must advance (or
    become null). It may invalidate unrelated regions but cannot miss expiry.
    No TTL is used as evidence of unchanged data.
    """
    values = []
    if query["system"]:
        domain = """SELECT md5(COALESCE(string_agg(md5(ROW(system_name, revision)::text),
            '' ORDER BY system_name), '')) FROM mining_revision_systems
            WHERE system_name = lower(%s)"""
        values.append(query["system"].strip())
    else:
        coords = [query[k] for k in ("x", "y", "z", "max_distance")]
        if any(v is None or not math.isfinite(v) for v in coords):
            raise ValueError("Mining revision requires a finite region")
        x, y, z, radius = coords
        if radius <= 0 or any(abs(v) + radius > 1e12 for v in (x, y, z)):
            raise ValueError("Mining revision region outside marker bounds")
        lower = [math.floor((v - radius) / CELL_SIZE) for v in (x, y, z)]
        upper = [math.floor((v + radius) / CELL_SIZE) for v in (x, y, z)]
        domain = """SELECT md5(COALESCE(string_agg(md5(ROW(cx, cy, cz, revision)::text),
            '' ORDER BY cx, cy, cz), '')) FROM mining_revision_cells
            WHERE cx BETWEEN %s AND %s AND cy BETWEEN %s AND %s
              AND cz BETWEEN %s AND %s"""
        values.extend((lower[0], upper[0], lower[1], upper[1], lower[2], upper[2]))
    references = sorted({r["system"].lower() for r in catalog()}) \
        if query["include_community_overlaps"] else []
    values.extend((references, references, query["max_age_days"]))
    row = conn.execute(f"""
        SELECT s.schema_version, s.ready, s.generation::text, s.unknown_revision,
            ({domain}) AS counters,
            (SELECT md5(COALESCE(string_agg(md5(ROW(system_name, revision)::text),
                '' ORDER BY system_name), '')) FROM mining_revision_systems
                WHERE system_name = ANY(%s)) AS reference_counters,
            (SELECT count(*) FROM unnest(%s::text[]) name WHERE NOT EXISTS
                (SELECT 1 FROM mining_revision_references r
                 WHERE r.system_name = name)) AS missing_references,
            (SELECT age.observed_at::text FROM mining_sites age
                WHERE age.observed_at >= NOW() - (%s * INTERVAL '1 day')
                -- Qualify the BASE timestamp, not the text output alias.
                -- Sorting its formatted output would scan/format every row
                -- instead of using the observed_at index for one age floor.
                ORDER BY age.observed_at LIMIT 1) AS age_boundary
        FROM mining_revision_state s WHERE singleton
        """, values).fetchone()
    if (not isinstance(row, dict) or row.get("schema_version") != SCHEMA_VERSION
            or row.get("ready") is not True or not isinstance(row.get("generation"), str)
            or not isinstance(row.get("unknown_revision"), int)
            or not isinstance(row.get("counters"), str)
            or not isinstance(row.get("reference_counters"), str)
            or row.get("missing_references") != 0
            or "age_boundary" not in row):
        raise ValueError("Mining revision markers are not ready")
    payload = {"query": query, "database": row, "static": static_revision()}
    return "s1-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
