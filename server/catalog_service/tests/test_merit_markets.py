import unittest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from edframe_catalog.merit_markets import MeritMarketQuery, search_merit_markets


def query(**changes):
    return MeritMarketQuery(targets=[{'system':'Mine', 'commodities':['platinum','alexandrite']}],
                            power='Aisling Duval', goal='REINFORCE', method='LASER', **changes)


class MeritMarketServerTests(unittest.TestCase):
    def test_bounded_and_unique_request(self):
        for targets in ([{'system':'X','commodities':['platinum']}] * 201,
                        [{'system':'Mine','commodities':['gold']}, {'system':'mine','commodities':['gold']}],
                        [{'system':'Mine','commodities':['fakecommodity']}],
                        [{'system':'   ','commodities':['gold']}]):
            with self.assertRaises(ValidationError):
                MeritMarketQuery(targets=targets, power='Aisling Duval', goal='REINFORCE', method='LASER')

    def test_query_is_exact_method_filtered_readonly_and_retains_unknown(self):
        conn=MagicMock()
        conn.execute.return_value.fetchall.side_effect=[[], [{'system':'Mine','commodity':'platinum'}], []]
        with patch('edframe_catalog.merit_markets.connection') as connect:
            connect.return_value.__enter__.return_value=conn
            result=search_merit_markets(query(landingPad='L'))
        self.assertFalse(result['hasMore'])
        self.assertTrue(result['coverage'][0]['queried'])
        self.assertTrue(result['coverage'][0]['status'].startswith('UNKNOWN'))
        self.assertEqual(result['coverage'][0]['commodities'],['platinum'])
        self.assertIn('SET TRANSACTION READ ONLY',[call.args[0] for call in conn.execute.call_args_list])
        sql, values=conn.execute.call_args_list[4].args
        self.assertIn('DISTINCT ON',sql)
        self.assertIn('LOWER(m.system_name) = t.system',sql)
        self.assertIn('st.fleet_carrier IS NOT TRUE',sql)
        self.assertEqual(values[-1],['L'])

    def test_explicit_ineligible_control_is_excluded(self):
        from datetime import datetime,timezone
        facts=[{'system':'Mine','power':'Felicia Winters','controllingPower':'Felicia Winters',
                'controlKnown':True,'powerState':'Stronghold','powerRelationship':'CONTROL',
                'observedAt':datetime.now(timezone.utc).isoformat()}]
        conn=MagicMock()
        conn.execute.return_value.fetchall.return_value=[{'facts':facts}]
        with patch('edframe_catalog.merit_markets.connection') as connect:
            connect.return_value.__enter__.return_value=conn
            result=search_merit_markets(query())
        self.assertEqual(result['results'],[])
        self.assertFalse(result['coverage'][0]['queried'])
        self.assertEqual(result['powerplay'],facts)
