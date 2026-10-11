import copy
import random
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ed_companion.navigation.trade_route_model import search_filters, rank_loops
from ed_companion.navigation.trade_routes import fetch_trade_routes, validate_trade_routes, describe_trade_routes
from ed_companion.navigation.mining_market import MiningMarketError
from ed_companion.phase14.controller_trade_routes import TradeRoutesMixin


def fixture(capacity=10, budget=50, commodity="ALL", sort_by="PROFIT"):
    filters = search_filters([0,0,0],50,100,capacity,budget,24,"L",False,commodity,sort_by)
    stations = [dict(marketId=1,system="A system",station="A port",coordinates=[0,0,0],landingPadSize="L",distanceLy=0),
        dict(marketId=2,system="B system",station="B port",coordinates=[10,0,0],landingPadSize="L",distanceLy=10)]
    now = datetime.now(timezone.utc).isoformat()
    def q(market,symbol,buy,sell):
        return dict(marketId=market,commodity=symbol,buyPrice=buy,sellPrice=sell,stock=10,demand=10,observedAt=now,source="test")
    quotes = [q(1,"gold",10,5),q(2,"gold",30,20),q(1,"water",40,30),q(2,"water",20,10)]
    return filters,stations,quotes


class TradeRouteModelTests(unittest.TestCase):
    def test_both_legs_conserve_capacity_cash_stock_and_demand(self):
        f,s,q = fixture()
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual((row["outbound"]["tonnes"],row["inbound"]["tonnes"]),(5,5))
        self.assertEqual((row["outbound"]["purchaseCr"],row["inbound"]["purchaseCr"]),(50,100))
        self.assertEqual(row["profitCr"],100)
        self.assertEqual(row["finalBudgetCr"],150)
        self.assertEqual(row["roundTripLy"],20)
        q[0]["stock"]=1; q[2]["demand"]=2
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual(row["outbound"]["tonnes"],1)
        self.assertEqual(row["inbound"]["tonnes"],2)

    def test_most_profitable_outbound_can_fund_more_return_cargo(self):
        f,s,q = fixture(capacity=10,budget=100)
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual(row["outbound"]["budgetAfterCr"],200)
        self.assertEqual(row["inbound"]["tonnes"],10)

    def test_no_return_offer_is_not_a_round_trip(self):
        f,s,q = fixture()
        self.assertEqual(rank_loops(s,q[:2],f)["results"],[])
        for bad in (None,0):
            changed=copy.deepcopy(q);changed[2]["demand"]=bad
            self.assertEqual(rank_loops(s,changed,f)["results"],[])

    def test_geometry_pad_carrier_freshness_and_unknown_goods_are_checked(self):
        f,s,q=fixture()
        for change in ("range","pad","carrier","age","unknown","coordinates"):
            with self.subTest(change=change):
                stations=copy.deepcopy(s);quotes=copy.deepcopy(q);filters=dict(f)
                if change=="range":stations[1]["coordinates"]=[101,0,0]
                elif change=="pad":stations[1]["landingPadSize"]="S"
                elif change=="carrier":stations[1]["fleetCarrier"]=True;filters["excludeCarriers"]=True
                elif change=="age":quotes[2]["observedAt"]="2020-01-01T00:00:00Z"
                elif change=="unknown":quotes[2]["commodity"]="unknown"
                else:stations[1]["coordinates"]=[float("nan"),0,0]
                self.assertEqual(rank_loops(stations,quotes,filters)["results"],[])

    def test_selected_outbound_does_not_restrict_return_commodity(self):
        f,s,q=fixture(commodity="gold")
        row=rank_loops(s,q,f)["results"][0]
        self.assertEqual(row["outbound"]["commodity"],"gold")
        self.assertEqual(row["inbound"]["commodity"],"water")

    def test_unit_margin_selects_different_cargo_than_total_profit(self):
        f,s,q = fixture(capacity=10,budget=100000,sort_by="UNIT_PROFIT")
        q.extend([dict(q[0],commodity="platinum",stock=1),
            dict(q[1],commodity="platinum",sellPrice=100,demand=1)])
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual(row["outbound"]["commodity"],"platinum")
        self.assertEqual(row["unitProfitCr"],100)
        f["sortBy"] = "PROFIT"
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual(row["outbound"]["commodity"],"gold")

    def test_unit_margin_keeps_a_lower_outbound_margin_that_funds_a_better_return(self):
        f,s,q = fixture(capacity=10,budget=1000,sort_by="UNIT_PROFIT")
        q[1]["sellPrice"] = 110
        q[2]["sellPrice"] = 6000; q[3]["buyPrice"] = 2000
        q.extend([dict(q[0],commodity="platinum",stock=1),
            dict(q[1],commodity="platinum",sellPrice=111,demand=1),
            dict(q[0],commodity="hydrogenfuel",buyPrice=3,sellPrice=2),
            dict(q[1],commodity="hydrogenfuel",buyPrice=1,sellPrice=1)])
        row = next(r for r in rank_loops(s,q,f)["results"] if r["stationA"]["marketId"]==1)
        self.assertEqual((row["outbound"]["commodity"],row["inbound"]["commodity"]),("gold","water"))
        self.assertEqual(row["unitProfitCr"],4100)
        self.assertEqual(row["inbound"]["tonnes"],1)

    def test_unit_frontier_matches_exhaustive_affordable_cargo_pairs(self):
        rng = random.Random(7619)
        for case in range(60):
            f,s,initial = fixture(capacity=rng.randint(1,10),budget=rng.randint(20,500),sort_by="UNIT_PROFIT")
            q = [dict(initial[0],marketId=market,commodity=symbol,
                buyPrice=rng.randint(1,100),sellPrice=rng.randint(1,180),
                stock=rng.randint(0,15),demand=rng.randint(0,15))
                for market in (1,2) for symbol in ("gold","platinum","water","hydrogenfuel")]
            actual = {row["stationA"]["marketId"]:row for row in rank_loops(s,q,f)["results"]}
            for market in (1,2):
                source = {row["commodity"]:row for row in q if row["marketId"]==market}
                target = {row["commodity"]:row for row in q if row["marketId"]!=market}
                possibilities = []
                for symbol,buy in source.items():
                    sell = target[symbol]
                    spread = sell["sellPrice"]-buy["buyPrice"]
                    tonnes = min(f["cargoTonnes"],buy["stock"],sell["demand"],f["budgetCr"]//buy["buyPrice"])
                    if spread<=0 or tonnes<1:
                        continue
                    after = f["budgetCr"]+tonnes*spread
                    for return_symbol,return_buy in target.items():
                        return_sell = source[return_symbol]
                        return_spread = return_sell["sellPrice"]-return_buy["buyPrice"]
                        return_tonnes = min(f["cargoTonnes"],return_buy["stock"],return_sell["demand"],after//return_buy["buyPrice"])
                        if return_spread>0 and return_tonnes>0:
                            possibilities.append((spread+return_spread,tonnes*spread+return_tonnes*return_spread))
                with self.subTest(case=case,market=market):
                    if possibilities:
                        row = actual[market]
                        self.assertEqual((row["unitProfitCr"],row["profitCr"]),max(possibilities))
                    else:
                        self.assertNotIn(market,actual)

    def test_same_station_excluded_but_same_system_different_ports_allowed(self):
        f,s,q=fixture();s[1]["coordinates"]=[0,0,0]
        self.assertEqual(rank_loops(s,q,f)["results"][0]["roundTripLy"],0)
        self.assertEqual(rank_loops(s[:1],q,f)["results"],[])

    def test_sorting_before_limit_and_no_first_hundred_quote_truncation(self):
        f,s,q=fixture(budget=100000)
        # The best destination is deliberately beyond 100 earlier quotes.
        for market in range(3,103):
            s.append(dict(s[1],marketId=market,coordinates=[1,0,0]))
            q.extend(dict(row,marketId=market,sellPrice=11 if row["commodity"]=="gold" else row["sellPrice"])
                     for row in (q[1],q[3]))
        s.append(dict(s[1],marketId=103,coordinates=[2,0,0]))
        q.extend(dict(row,marketId=103,sellPrice=1000 if row["commodity"]=="gold" else row["sellPrice"])
                 for row in (q[1],q[3]))
        result=rank_loops(s,q,f,limit=1)
        self.assertEqual(result["results"][0]["stationB"]["marketId"],103)
        self.assertTrue(result["hasMore"])
        f["sortBy"]="DISTANCE"
        self.assertLess(rank_loops(s,q,f,limit=1)["results"][0]["totalDistanceLy"],4)

    def test_budget_origin_and_timeout_limits(self):
        for kwargs in (dict(origin=[]),dict(budget=0),dict(radius=0),dict(leg_distance=501),dict(age_hours=169),dict(sort_by="bad")):
            args=dict(origin=[0,0,0],radius=50,leg_distance=100,capacity=10,budget=50,age_hours=24,pad="ANY",exclude_carriers=False)
            args.update(kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(MiningMarketError):search_filters(**args)
        f,s,q=fixture()
        with self.assertRaises(MiningMarketError):rank_loops(s,q,f,deadline=time.monotonic()-1)


class TradeRouteClientTests(unittest.TestCase):
    def payload(self):
        f,s,q=fixture();return dict(rank_loops(s,q,f),filters=f,coverage=dict(sampled=False,stations=2,availableStations=2))

    def test_parser_recomputes_budgets_profits_and_geometry(self):
        payload=self.payload();self.assertEqual(len(validate_trade_routes(payload,payload["filters"])["results"]),2)
        for path,value in (("profitCr",9999999),("roundTripLy",5),("finalBudgetCr",1)):
            changed=copy.deepcopy(payload);changed["results"][0][path]=value
            self.assertEqual(len(validate_trade_routes(changed,payload["filters"])["results"]),1)
        for key,value in (("tonnes",10000),("budgetBeforeCr",1),("buyObservedAt","2020-01-01T00:00:00Z"),("demand",0)):
            changed=copy.deepcopy(payload);changed["results"][0]["inbound"][key]=value
            self.assertEqual(len(validate_trade_routes(changed,payload["filters"])["results"]),1)

    def test_request_filters_confirmed_and_old_server_error_clear(self):
        response=Mock();response.json.return_value=self.payload();get=Mock(return_value=response)
        result=fetch_trade_routes(origin=[0,0,0],capacity=10,budget=50,pad="L",get=get)
        self.assertEqual(len(result["results"]),2)
        self.assertEqual(get.call_count,1)
        self.assertEqual(get.call_args.kwargs["params"]["cargo_tonnes"],10)
        self.assertEqual(get.call_args.kwargs["params"]["budget_cr"],50)
        response.json.return_value["filters"]["radiusLy"]=99
        with self.assertRaises(MiningMarketError):fetch_trade_routes(origin=[0,0,0],capacity=10,budget=50,pad="L",get=get)
        response.status_code=404
        with self.assertRaisesRegex(MiningMarketError,"server update"):fetch_trade_routes(origin=[0,0,0],get=get)

    def test_access_age_names_and_carrier_warnings(self):
        payload=self.payload();payload["results"][0]["stationA"]["fleetCarrier"]=True
        payload["results"][0]["stationA"]["prohibited"]=["gold"]
        shown=describe_trade_routes(payload["results"])
        self.assertTrue(shown[0]["carrierWarning"])
        self.assertTrue(shown[0]["prohibitedWarning"])
        self.assertEqual(shown[0]["outbound"]["commodityName"],"Gold")


class TradeRouteControllerTests(unittest.TestCase):
    def test_known_zero_credits_do_not_become_an_invented_purchase_budget(self):
        shell=SimpleNamespace(_state=dict(activeShipFitStats=dict(cargoCapacity=64),
            commanderOverview=dict(credits=dict(known=True,value=0))))
        defaults=TradeRoutesMixin.tradeRouteDefaults.fget(shell)
        self.assertEqual(defaults['budget'],0)
        self.assertTrue(defaults['budgetKnown'])
        self.assertEqual(defaults['capacity'],64)
        shell._state['commanderOverview']['credits']['known']=False
        self.assertEqual(TradeRoutesMixin.tradeRouteDefaults.fget(shell)['budget'],10000000)

    def shell(self):
        shell=SimpleNamespace(_state=dict(system="Sol",currentPosition=[0,0,0]),_profile_generation=1,
            tradeRoutesBusy=False,_edframe_catalog_enabled=True,_start_network_worker=Mock(return_value=True),
            tradeRoutesChanged=Mock(),tradeRoutesFinished=Mock(),_trade_rows=[dict(id="previous")])
        return shell

    def test_manual_origin_resolves_in_worker_and_survives_movement(self):
        shell=self.shell()
        with patch("ed_companion.phase14.controller_trade_routes.fetch_edframe_system_coordinates") as resolve, \
                patch("ed_companion.phase14.controller_trade_routes.fetch_trade_routes") as offers:
            resolve.return_value=dict(system="Cubeo",coordinates=[1,2,3])
            f,s,q=fixture();offers.return_value=dict(rank_loops(s,q,f),filters=f)
            TradeRoutesMixin.searchTradeRoutes(shell,"Cubeo","ALL",10,50,50,100,24,"L",False,"PROFIT")
            resolve.assert_not_called();offers.assert_not_called()
            shell._start_network_worker.call_args.args[0]()
            resolve.assert_called_once()
            self.assertEqual(offers.call_args.kwargs["origin"],[1,2,3])
        shell._state["currentPosition"]=[999,0,0]
        TradeRoutesMixin._finish_trade_routes(shell,shell.tradeRoutesFinished.emit.call_args.args[0])
        self.assertEqual(shell._trade_snapshot["system"],"Cubeo")
        self.assertNotIn("Previous location",TradeRoutesMixin.tradeRouteStatus.fget(shell))

    def test_failure_profile_location_disabled_and_shutdown_retain_previous_routes(self):
        for reason in ("failure","profile","location","disabled","shutdown"):
            shell=self.shell()
            TradeRoutesMixin.searchTradeRoutes(shell,"","ALL",10,50,50,100,24,"L",False,"PROFIT")
            query=shell._trade_request
            if reason=="profile":shell._profile_generation=2
            elif reason=="location":shell._state["currentPosition"]=[9,9,9]
            elif reason=="disabled":shell._edframe_catalog_enabled=False
            elif reason=="shutdown":shell._shutdown_complete=True
            if reason=="shutdown":
                before=shell._start_network_worker.call_count
                TradeRoutesMixin.searchTradeRoutes(shell,"","ALL",10,50,50,100,24,"L",False,"PROFIT")
                self.assertEqual(shell._start_network_worker.call_count,before)
            else:
                TradeRoutesMixin._finish_trade_routes(shell,dict(query,success=False,error="synthetic"))
                self.assertEqual(shell._trade_rows,[dict(id="previous")])

    def test_invalid_inputs_never_start_network(self):
        shell=self.shell()
        TradeRoutesMixin.searchTradeRoutes(shell,"","ALL",10,0,50,100,24,"L",False,"PROFIT")
        shell._start_network_worker.assert_not_called()
