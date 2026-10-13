import unittest
from unittest.mock import MagicMock
from edframe_catalog.query_performance import read_query_performance, QueryPerformanceUnavailable


class QueryPerformanceTests(unittest.TestCase):
    def test_absent_measurement_is_explicitly_unavailable(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = {"ready":False}
        with self.assertRaises(QueryPerformanceUnavailable):
            read_query_performance(conn)

    def test_output_uses_readonly_transaction_and_hides_sql_by_default(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{"ready":True},{"track":"top"}]
        conn.execute.return_value.fetchall.return_value = [{"query_id":"42","calls":12,"sql":None}]
        result = read_query_performance(conn, limit=3)
        self.assertEqual(result["statements"][0]["calls"], 12)
        self.assertIsNone(result["statements"][0]["sql"])
        self.assertEqual(conn.execute.call_args.args[1], (False,3))
        self.assertEqual(conn.execute.call_args_list[0].args[0], "SET TRANSACTION READ ONLY")

    def test_sql_requires_explicit_operator_option(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [{"ready":True},{}]
        conn.execute.return_value.fetchall.return_value = []
        read_query_performance(conn, include_sql=True)
        self.assertEqual(conn.execute.call_args.args[1], (True,20))

    def test_invalid_limits_are_rejected_before_database_access(self):
        for limit in (0,51,True,"20",-5):
            conn = MagicMock()
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                read_query_performance(conn, limit=limit)
            conn.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
