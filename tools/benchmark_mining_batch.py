"""Controlled public-catalog merge probe; never writes to its input profile."""
import argparse
import cProfile
import hashlib
import io
import json
from pathlib import Path
import pstats
import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ed_companion.history_archive import HistoryArchive
from ed_companion.navigation.catalog_json import load_catalog_json, catalog_view_value
from ed_companion.navigation.mining_batch import prepare_mining_batch
from ed_companion.navigation.mining_finder import mining_candidate_positions, mining_candidate_freshness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--rows', type=int, default=24456)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / '.test-tmp') or args.output.exists():
        raise RuntimeError('A new .test-tmp output directory is required')
    args.output.mkdir(parents=True)
    existing = load_catalog_json(args.catalog, {}, snapshot_arrays=True)['candidates']
    incoming = [catalog_view_value(row) for row in existing[:args.rows]]
    index = mining_candidate_positions(existing)
    archive = HistoryArchive(args.output / 'history.sqlite3')
    clock = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    def freshness(row, now=None, policy=None):
        return mining_candidate_freshness(row, now=now or clock, policy=policy)
    profile = cProfile.Profile()
    started = time.perf_counter()
    with patch('ed_companion.navigation.mining_finder.mining_candidate_freshness', freshness):
        result = profile.runcall(prepare_mining_batch, existing, incoming,
                                positions=index, archive=archive, snapshot_arrays=True)
    elapsed = time.perf_counter() - started
    digest = hashlib.sha256()
    for row in result['candidates']:
        digest.update(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    output = io.StringIO()
    pstats.Stats(profile, stream=output).sort_stats('cumulative').print_stats(35)
    data = dict(seconds=round(elapsed, 4), existing=len(existing), incoming=len(incoming),
                candidates=len(result['candidates']), archiveError=result['archiveError'],
                counts=archive.counts(), contentHash=digest.hexdigest(), profile=output.getvalue())
    (args.output / 'result.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps(data), flush=True)


if __name__ == '__main__':
    main()
