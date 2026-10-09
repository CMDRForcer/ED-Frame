"""Compare proposed revision SQL in one read-only database snapshot.

Execute ephemerally via stdin in the deployed API container. Input is a JSON
object with `before` and `after` source modules, not installed files. There is
no lifespan/schema initialization, persistent source install or database write.
The bundled/static version is held equal only to compare database content.
"""

import hashlib
import json
import sys
import time

from edframe_catalog.database import connection


class PlanRecorded(Exception):
    pass


class ExplainConnection:
    def __init__(self, conn, *, variant, radius):
        self.conn, self.variant, self.radius = conn, variant, radius

    def execute(self, sql, values):
        plan = self.conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
                                 values).fetchone()["QUERY PLAN"][0]
        nodes = []
        def visit(node, depth=0):
            nodes.append({"depth": depth, **{k: node[k] for k in (
                "Node Type", "Subplan Name", "CTE Name", "Index Name",
                "Relation Name", "Plan Rows", "Actual Rows", "Actual Loops",
                "Actual Total Time", "Rows Removed by Filter", "Temp Written Blocks") if k in node}})
            for child in node.get("Plans", []):
                visit(child, depth + 1)
        visit(plan["Plan"])
        print(json.dumps({"variant": self.variant, "radius": self.radius,
                          "executionMs": plan["Execution Time"], "nodes": nodes}), flush=True)
        raise PlanRecorded()


def function(source):
    namespace = {"__package__": "edframe_catalog", "__file__": __file__}
    exec(compile(source, "<ephemeral-revision-probe>", "exec"), namespace)
    namespace["static_revision"] = lambda: "read-only-cost-comparison"
    return namespace["mining_revision"]


def main():
    sources = json.loads(sys.stdin.read())
    functions = {name: function(sources[name]) for name in ("before", "after")}
    print(json.dumps({"readOnly": True, "sourceSha256": {
        name: hashlib.sha256(sources[name].encode()).hexdigest()
        for name in functions}}), flush=True)
    for radius in sources.get("radii", (50, 250, 500)):
        query = dict(commodity="platinum", system="", max_age_days=3650,
                     x=110.9375, y=-113.0625, z=41.21875,
                     max_distance=float(radius), limit=5000,
                     include_ring_candidates=True, include_community_overlaps=True)
        with connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '15s'")
            conn.execute("SET LOCAL lock_timeout = '1s'")
            if sources.get("explain"):
                for name, read in functions.items():
                    try:
                        read(ExplainConnection(conn, variant=name, radius=radius), query)
                    except PlanRecorded:
                        pass
                conn.rollback()
                continue
            revisions = {name: set() for name in functions}
            timings = {name: [] for name in functions}
            # Alternate endpoints to avoid assigning all warming to one variant.
            for name in sources.get("order", ("before", "after", "after", "before")):
                started = time.monotonic()
                revisions[name].add(functions[name](conn, query))
                seconds = round(time.monotonic() - started, 4)
                timings[name].append(seconds)
                print(json.dumps({"radius": radius, "variant": name,
                                  "seconds": seconds}), flush=True)
            assert all(len(values) == 1 for values in revisions.values()), "Unstable revision"
            print(json.dumps({"radius": radius, "stableRevisions": True,
                              "equalRevision": revisions["before"] == revisions["after"],
                              "timings": timings}), flush=True)
            conn.rollback()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # A timed-out diagnostic remains a failure, without echoing the entire
        # base64 stdin harness/stack into deployment logs.
        print(json.dumps({"probeFailed": type(exc).__name__, "detail": str(exc)}), flush=True)
        raise SystemExit(1)
