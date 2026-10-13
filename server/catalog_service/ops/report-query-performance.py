"""Private read-only report: run inside the catalog image, not an HTTP endpoint."""
import argparse
import json

from edframe_catalog.database import connection
from edframe_catalog.query_performance import read_query_performance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sql", action="store_true", help="Include normalized SQL text for the operator")
    args = parser.parse_args()
    with connection() as conn:
        report = read_query_performance(conn, limit=args.limit, include_sql=args.sql)
    print(json.dumps(report, default=str, indent=2))


if __name__ == "__main__":
    main()
