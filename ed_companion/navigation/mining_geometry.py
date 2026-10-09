"""Small, snapshot-bound geometry reuse, never cached freshness or scores."""
from array import array
from itertools import chain
import math
from threading import Lock

from ed_companion.worker_budget import WorkerBudget


def nearby_rows(rows, origin_system, origin, radius, valid_position):
    """Keep source order and the existing rounded, inclusive radius rule."""
    system_key = str(origin_system or "").casefold()
    margin = radius + 0.1  # Conservative box: final test still rounds to 0.1 LY.
    budget = WorkerBudget()
    for index, row in enumerate(rows):
        budget.checkpoint()
        coordinates = valid_position(row.get("coordinates"))
        if str(row.get("system") or "").strip().casefold() == system_key:
            distance = 0.0
        elif origin is not None and coordinates is not None:
            dx = origin[0] - coordinates[0]
            dy = origin[1] - coordinates[1]
            dz = origin[2] - coordinates[2]
            # Preserve legacy NaN handling too: one NaN must not let the box
            # reject a row that the exact rounded-radius test would retain.
            if dx == dx and dy == dy and dz == dz and (
                abs(dx) > margin or abs(dy) > margin or abs(dz) > margin
            ):
                continue
            distance = round(math.sqrt(sum((dx ** 2, dy ** 2, dz ** 2))), 1)
        else:
            distance = None
        if distance is None or float(distance) > radius:
            continue
        yield index, distance


class _Selection:
    def __init__(self, source):
        self.source = source
        self.positions = array("Q")
        self.distances = array("d")

    def __iter__(self):
        return ((self.source[index], distance)
                for index, distance in zip(self.positions, self.distances))


class MiningGeometryCache:
    """One region, under 2 MiB of indices/distances plus a source reference.

    Opt in only for replacement-published immutable rows. Holding the source
    (not just its id) prevents GC identity reuse. Changed profile/path/reset
    scopes replace this cache in the controller. No ages, observations,
    filters, eligibility or ranking are retained here. Oversized selections
    stream without truncation or retaining another large catalog view.
    """
    MAX_ROWS = 100_000

    def __init__(self):
        self._lock = Lock()
        self._key = None
        self._selection = None

    def rows_for(self, rows, origin_system, origin, radius, valid_position):
        if radius <= 0:
            raise ValueError("Geometry reuse requires a bounded radius")
        key = (id(rows), len(rows), str(origin_system or "").casefold(),
               tuple(origin) if origin is not None else None, radius)
        with self._lock:
            if self._key == key and self._selection.source is rows:
                return iter(self._selection)
        iterator = nearby_rows(rows, origin_system, origin, radius, valid_position)
        selection = _Selection(rows)
        for index, distance in iterator:
            if len(selection.positions) >= self.MAX_ROWS:
                with self._lock:
                    self._key = self._selection = None
                return chain(selection, ((rows[index], distance),),
                             ((rows[position], value) for position, value in iterator))
            selection.positions.append(index)
            selection.distances.append(distance)
        with self._lock:
            self._selection = selection
            self._key = key
        return iter(selection)
