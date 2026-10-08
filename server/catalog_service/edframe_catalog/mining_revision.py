"""Content revisions for complete, consistently paginated mining snapshots.

No TTL or receipt-time shortcut: rows, deletions, yield materials, fallback
metadata and reference positions all contribute. This intentionally prefers
conservative invalidation over incorrectly declaring unchanged observations.
"""

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from ed_companion.navigation.mining_commodities import MINING_COMMODITIES
from .mining_overlaps import catalog, imported_system_positions


@lru_cache(maxsize=1)
def static_revision():
    facts = [catalog(), imported_system_positions(), MINING_COMMODITIES]
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True).encode())
    # A deployment changing response/projection rules must also invalidate
    # clients. Processes load their bundled references once, just as the API.
    for name in ("api.py", "mining_revision.py", "mining_metadata.py", "mining_overlaps.py"):
        digest.update(Path(__file__).with_name(name).read_bytes())
    return digest.hexdigest()


def mining_revision(conn, query):
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
    reference_names = sorted({r["system"].casefold() for r in catalog()}) \
        if query["include_community_overlaps"] else []
    values.extend((reference_names, reference_names))
    row = conn.execute(f"""
        WITH scope AS MATERIALIZED (
            SELECT ms.identity, LOWER(ms.system_name) AS system
            FROM mining_sites ms WHERE {' AND '.join(clauses)}
        ), names AS MATERIALIZED (
            SELECT system FROM scope GROUP BY system
            UNION SELECT unnest(%s::text[])
        ), dependencies AS MATERIALIZED (
            SELECT ms.*, ms.xmin::text AS row_version FROM mining_sites ms
            WHERE LOWER(ms.system_name) = ANY(ARRAY(SELECT system FROM names))
        ), samples AS MATERIALIZED (
            SELECT ys.*, ys.xmin::text AS row_version FROM mining_yield_samples ys
            JOIN dependencies d ON d.identity = ys.site_identity
        )
        SELECT
            (SELECT md5(COALESCE(string_agg(md5(identity), '' ORDER BY identity), ''))
             FROM scope) AS membership,
            (SELECT md5(COALESCE(string_agg(md5(d::text), '' ORDER BY identity), ''))
             FROM dependencies d) AS sites,
            (SELECT md5(COALESCE(string_agg(md5(s::text), '' ORDER BY sample_id), ''))
             FROM samples s) AS samples,
            (SELECT md5(COALESCE(string_agg(md5(ROW(m, m.xmin)::text), '' ORDER BY m.sample_id, m.commodity), ''))
             FROM mining_yield_materials m JOIN samples s USING (sample_id)) AS materials,
            (SELECT md5(COALESCE(string_agg(md5(ROW(r.system_name, r.ring_name, r.system_address,
                                                  r.ring_type, r.reserve_level, r.source, r.observed_at, r.xmin)::text),
                                          '' ORDER BY system_name, ring_name), ''))
             FROM ring_reference_metadata r
             WHERE LOWER(r.system_name) = ANY(ARRAY(SELECT system FROM names))) AS metadata,
            (SELECT md5(COALESCE(string_agg(md5(ROW(name, system_address, x, y, z, observed_at, xmin)::text),
                                          '' ORDER BY name), ''))
             FROM systems WHERE LOWER(name) = ANY(%s)) AS positions
        """, values).fetchone()
    if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in
            ("membership", "sites", "samples", "materials", "metadata", "positions")):
        raise ValueError("Mining revision could not be established")
    payload = {"query": query, "database": row, "static": static_revision()}
    return "s1-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
