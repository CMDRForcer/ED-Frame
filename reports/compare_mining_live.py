"""Read-only comparison using the app's real projection, filter and planner."""
import json
from datetime import datetime, timezone
import requests
import time
from ed_companion.navigation.mining_finder import fetch_edframe_mining_candidates, merge_mining_candidates
from ed_companion.navigation.mining_market import fetch_edframe_system_coordinates, _fetch_edframe_catalog_markets
from ed_companion.navigation.mining_planner import plan_mining_routes
from ed_companion.phase14.controller_navigation import NavigationMixin

origin = fetch_edframe_system_coordinates('Shanteneri', get=requests.get)
diagnostics = {}
started = time.monotonic()
raw = fetch_edframe_mining_candidates('Shanteneri', requests.get, commodity='platinum', origin=origin['coordinates'], max_distance=250, diagnostics=diagnostics)
print(json.dumps({'ringFetchSeconds': round(time.monotonic() - started, 2), 'coverage': diagnostics, 'containsBZCeti': any(r.get('system') == 'BZ Ceti' for r in raw)}), flush=True)
markets = _fetch_edframe_catalog_markets('Shanteneri', 'platinum', max_distance=250, max_days_ago=1, landing_pad='L', get=requests.get, timeout=30, origin=origin, max_age_hours=1)

class Probe(NavigationMixin):
    _state = {'system': 'Shanteneri', 'currentPosition': origin['coordinates']}
    def _mining_rows(self):
        return self.rows

probe = Probe()
merged = merge_mining_candidates(raw)
probe.rows = probe._build_mining_rows(probe._state, {'candidates': merged})
candidates = probe._mining_find_page('Platinum', 250, 'ALL EVIDENCE', 'ALL RESERVES', 'LASER', 'Shanteneri', True)
routes = plan_mining_routes(candidates, 'Platinum', 'HIGHEST PROFIT', min_demand=5000, max_market_age_hours=1, landing_pad='L', result_limit=30, markets=markets, rings_only=True)
fields = ('system', 'ring', 'targetMatch', 'ringTypeName', 'sellSystem', 'station', 'sellPrice', 'marketKnown', 'demand', 'marketAgeSeconds')
same_system = []
for candidate in candidates:
    local_markets = [m for m in markets if m.get('system') == candidate.get('system')]
    assessed = plan_mining_routes([candidate], 'Platinum', 'HIGHEST PROFIT', min_demand=5000, max_market_age_hours=1, landing_pad='L', markets=local_markets)
    same_system.extend(r for r in assessed if r.get('marketKnown'))
targeted = {}
for name in ('BZ Ceti', 'Eta Sagittarii'):
    targeted[name] = [{k:r.get(k) for k in ('system','ring','ringType','hotspots')} for r in fetch_edframe_mining_candidates(name, requests.get, commodity='platinum', origin=origin['coordinates'])]
print(json.dumps({'time':datetime.now(timezone.utc).isoformat(), 'origin':origin, 'diagnostics':diagnostics, 'markets':len(markets), 'candidates':len(candidates), 'routeCount':len(routes), 'topRoutes':[{k:r.get(k) for k in fields} for r in routes[:3]], 'sameSystemRoutes':[{k:r.get(k) for k in fields} for r in same_system], 'targeted':targeted}, indent=2))
