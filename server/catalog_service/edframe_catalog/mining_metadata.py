"""Join ring metadata without changing ring/planet IDs or sample ownership."""


def canonical_metadata(value, column):
    text = str(value or '').strip()
    key = text.casefold().replace(' ', '').replace('eringclass_', '').replace('resources', '')
    names = ({'metalic': 'Metallic', 'metallic': 'Metallic', 'metalrich': 'Metal Rich',
              'rocky': 'Rocky', 'icy': 'Icy'} if column == 'ring_type' else
             {'pristine': 'Pristine', 'major': 'Major', 'common': 'Common',
              'low': 'Low', 'depleted': 'Depleted'})
    return names.get(key, text)


def enrich_ring_metadata(conn, rows):
    pending = [row for row in rows if row.get("system") and row.get("ring")
               and (not row.get("ringType") or not row.get("reserveLevel"))]
    if not pending:
        return rows
    names = sorted({row["system"].strip().casefold() for row in pending})
    metadata = conn.execute(
        """SELECT system_address, system_name, ring_name, ring_type,
                  reserve_level, source, observed_at
           FROM mining_sites
           WHERE LOWER(system_name) = ANY(%s)
             AND (COALESCE(ring_type, '') <> ''
                  OR COALESCE(reserve_level, '') <> '')
           UNION ALL
           SELECT system_address, system_name, ring_name, ring_type,
                  reserve_level, source, observed_at
           FROM ring_reference_metadata WHERE LOWER(system_name) = ANY(%s)""", (names, names),
    ).fetchall()
    by_ring = {}
    for item in metadata:
        key = (str(item.get("system_name") or "").strip().casefold(),
               str(item.get("ring_name") or "").strip().casefold())
        by_ring.setdefault(key, []).append(item)
    for row in pending:
        key = (row["system"].strip().casefold(), row["ring"].strip().casefold())
        candidates = [item for item in by_ring.get(key, [])
                      if not (row.get("systemAddress") is not None
                              and item.get("system_address") is not None
                              and row["systemAddress"] != item["system_address"])]
        for output, column in (("ringType", "ring_type"), ("reserveLevel", "reserve_level")):
            if row.get(output):
                continue
            values = {canonical_metadata(item[column], column) for item in candidates if item.get(column)}
            # Conflicting observations are not silently resolved by fetch time.
            if len(values) != 1:
                continue
            row[output] = next(iter(values))
            row.setdefault("ringMetadataEvidence", []).extend(
                {"field": output, "source": item.get("source"),
                 "observedAt": item.get("observed_at")}
                for item in candidates if canonical_metadata(item.get(column), column) == row[output])
    return rows
