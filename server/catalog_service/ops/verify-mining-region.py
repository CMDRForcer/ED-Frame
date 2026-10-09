"""Read-only complete legacy/expanded paging equality on one DB snapshot.

Run via stdin in the deployed API container. No schema or data writes. Keeps
the original sphere and both first-page community-reference sets observable.
"""
import contextlib
import hashlib
import json
import time

from edframe_catalog import api
from edframe_catalog.database import connection

ORIGIN = dict(x=110.9375, y=-113.0625, z=41.21875, max_distance=250)


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str,
                                    separators=(',', ':')).encode()).hexdigest()


def collect_sites(expanded):
    params = dict(ORIGIN, commodity='platinum', max_age_days=3650, limit=1000,
                  include_community_overlaps=True, include_ring_candidates=True, offset=0)
    if expanded:
        params['regional_page_size'] = 5000
    rows, refs = [], []
    started = time.monotonic()
    for page in range(1, 51):
        payload = api.search_sites(**params)
        rows.extend(payload['results'])
        refs.extend(payload['communityReferences'])
        if not payload['hasMore']:
            return rows, refs, dict(pages=page, rows=len(rows), references=len(refs),
                                   seconds=round(time.monotonic()-started, 4))
        assert payload['nextCursor'], 'Incomplete sites cursor'
        params['cursor'] = payload['nextCursor']
        if page % 5 == 0:
            print(json.dumps({'sitesProgress': page, 'expanded': expanded}), flush=True)
    raise AssertionError('Unexpected sites budget exhaustion')


def collect_powerplay(expanded):
    params = dict(ORIGIN, max_age_hours=24, limit=200)
    if expanded:
        params['regional_page_size'] = 1000
    rows, systems = [], 0
    started = time.monotonic()
    for page in range(1, 101):
        payload = api.search_mining_powerplay(**params)
        rows.extend(payload['results'])
        systems += payload['systemCount']
        if not payload['hasMore']:
            return rows, dict(pages=page, rows=len(rows), systems=systems,
                              seconds=round(time.monotonic()-started, 4))
        assert payload['nextCursor'], 'Incomplete Powerplay cursor'
        params['cursor'] = payload['nextCursor']
    raise AssertionError('Unexpected Powerplay budget exhaustion')


with connection() as snapshot:
    snapshot.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    snapshot.execute("SET LOCAL statement_timeout='30s'")

    @contextlib.contextmanager
    def same_snapshot():
        yield snapshot

    api.connection = same_snapshot
    old_sites, old_refs, old_stats = collect_sites(False)
    new_sites, new_refs, new_stats = collect_sites(True)
    assert old_sites == new_sites, 'Complete sites payload/order changed'
    assert old_refs == new_refs, 'First-page reference domain changed'
    print(json.dumps({'sites': {'legacy': old_stats, 'expanded': new_stats,
                               'equal': True, 'sha256': digest(new_sites),
                               'referenceSha256': digest(new_refs)}}), flush=True)
    old_pp, old_pp_stats = collect_powerplay(False)
    new_pp, new_pp_stats = collect_powerplay(True)
    assert old_pp == new_pp, 'Complete Powerplay payload/order changed'
    assert old_pp_stats['systems'] == new_pp_stats['systems']
    print(json.dumps({'powerplay': {'legacy': old_pp_stats, 'expanded': new_pp_stats,
                                   'equal': True, 'sha256': digest(new_pp)}}), flush=True)
