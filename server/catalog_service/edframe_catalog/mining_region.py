"""Bounded regional paging and indexed, exact spherical selection."""


def regional_page_limit(limit, requested, *, regional, maximum):
    # Opt-in: old apps and exact-system requests retain their original limits.
    return min(maximum, max(1, int(requested))) if regional and requested else limit


def regional_box_clause(x, y, z, radius, *, alias=""):
    """Cheap conservative prefilter; the original sphere predicate stays too.

    PostgreSQL's built-in GiST point operator needs no extension. The XY box
    plus Z range includes the whole sphere, including its boundary; it never
    turns a cube-only point into a valid result.
    """
    prefix = alias + "." if alias else ""
    return (
        f"point({prefix}x, {prefix}y) <@ box(point(%s, %s), point(%s, %s)) "
        f"AND {prefix}z BETWEEN %s AND %s",
        (x - radius, y - radius, x + radius, y + radius, z - radius, z + radius),
    )
