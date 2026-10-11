"""Approved isolated-container probe; no API lifespan or schema setup."""
import json
import os
import time

from edframe_catalog.trade_routes import search_trade_routes
from ed_companion.navigation.trade_route_model import search_filters
from ed_companion.navigation.trade_routes import validate_trade_routes


def main():
    assert 'default_transaction_read_only=on' in os.environ.get('PGOPTIONS', ''), 'Require read-only PostgreSQL defaults'
    for radius, carriers, commodity in ((50,False,'ALL'),(100,False,'ALL'),(50,True,'ALL'),(50,False,'gold')):
        filters=search_filters([0,0,0],radius,100,100,10_000_000,24,'L',carriers,commodity)
        start=time.perf_counter()
        payload=search_trade_routes(filters,refresh=True)
        checked=validate_trade_routes(payload,filters)
        assert len(checked['results']) == len(payload['results']), 'Client discarded a live route'
        if commodity == 'ALL':
            assert checked['results'], 'No round trips for representative Sol search'
        print(json.dumps(dict(radiusLy=radius,excludeCarriers=carriers,commodity=commodity,
            seconds=round(time.perf_counter()-start,3),count=len(checked['results']),
            matchedLoops=payload['matchedLoops'],coverage=payload['coverage'])),flush=True)
    start=time.perf_counter()
    cached=search_trade_routes(filters)
    assert cached['cached'] and cached['generatedAt']==payload['generatedAt']
    print(json.dumps(dict(cacheSeconds=round(time.perf_counter()-start,4))),flush=True)


if __name__ == '__main__':
    main()
