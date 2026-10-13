import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from psycopg import OperationalError
from psycopg.errors import DeadlockDetected, SerializationFailure, UniqueViolation

from edframe_catalog import collector
from edframe_catalog import collector_transactions as tx


class CollectorTransactionTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.operation = MagicMock()
        self.received_at = "2026-10-12T19:00:00Z"

    def run_retry(self):
        return tx.retry_transaction(self.conn, self.operation, schema="commodity/3", received_at=self.received_at)

    def test_success_is_executed_once_without_waiting(self):
        self.operation.return_value = "committed"
        with patch.object(tx.time, "sleep") as sleep:
            self.assertEqual(self.run_retry(), "committed")
        self.operation.assert_called_once_with()
        self.conn.rollback.assert_not_called()
        sleep.assert_not_called()

    def test_deadlock_rolls_back_before_replaying(self):
        order = []
        def operation():
            order.append("operation")
            if len(order) == 1:
                raise DeadlockDetected("synthetic")
            return 7
        self.operation.side_effect = operation
        self.conn.rollback.side_effect = lambda: order.append("rollback")
        with patch.object(tx.time, "sleep") as sleep, patch.object(tx.random, "uniform", return_value=0):
            self.assertEqual(self.run_retry(), 7)
        self.assertEqual(order, ["operation", "rollback", "operation"])
        sleep.assert_called_once_with(0.05)

    def test_serialization_failure_can_recover_on_last_bounded_attempt(self):
        self.operation.side_effect = [SerializationFailure("x") for _ in range(3)] + ["done"]
        with patch.object(tx.time, "sleep") as sleep, patch.object(tx.random, "uniform", return_value=0):
            self.assertEqual(self.run_retry(), "done")
        self.assertEqual(self.operation.call_count, 4)
        self.assertEqual(self.conn.rollback.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.05, 0.1, 0.2])

    def test_exhaustion_remains_an_error_and_does_not_wait_again(self):
        self.operation.side_effect = DeadlockDetected("persistent")
        with patch.object(tx.time, "sleep") as sleep:
            with self.assertRaises(DeadlockDetected):
                self.run_retry()
        self.assertEqual(self.operation.call_count, 4)
        self.assertEqual(self.conn.rollback.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_permanent_invalid_or_uncertain_commit_errors_are_not_replayed(self):
        for error in (UniqueViolation("permanent"), ValueError("invalid frame"), OperationalError("connection lost during COMMIT")):
            with self.subTest(error=type(error).__name__):
                self.operation.reset_mock()
                self.operation.side_effect = error
                with patch.object(tx.time, "sleep") as sleep:
                    with self.assertRaises(type(error)):
                        self.run_retry()
                self.operation.assert_called_once_with()
                sleep.assert_not_called()
        self.conn.rollback.assert_not_called()

    def test_failed_rollback_does_not_replay_on_unusable_connection(self):
        self.operation.side_effect = SerializationFailure("aborted")
        self.conn.rollback.side_effect = OperationalError("broken connection")
        with patch.object(tx.time, "sleep") as sleep:
            with self.assertRaises(OperationalError):
                self.run_retry()
        self.operation.assert_called_once_with()
        sleep.assert_not_called()

    def test_original_payload_and_receipt_are_preserved_after_commit_failure(self):
        payload = {"message":{"timestamp":"2026-10-12T18:59:00Z"}}
        projectors = ("project_system", "project_markets", "project_sites", "project_stations", "projected_systems", "project_state_bgs_snapshot", "project_state_signals", "project_state_sightings", "project_station_offers", "project_powerplay_snapshot")
        upserts = ("upsert_batch", "upsert_state_sighting_batch", "upsert_state_find_batch", "upsert_station_offer_batch", "upsert_powerplay_snapshot")
        self.conn.commit.side_effect = [SerializationFailure("commit conflict"), None]
        with ExitStack() as stack:
            mocks = {name:stack.enter_context(patch.object(collector, name, return_value=[])) for name in projectors}
            for name in upserts:
                stack.enter_context(patch.object(collector, name, return_value=1))
            stack.enter_context(patch.object(collector, "upsert_signal_systems"))
            state = stack.enter_context(patch.object(collector, "record_state"))
            stack.enter_context(patch.object(tx.time, "sleep"))
            tx.retry_transaction(self.conn, lambda:collector._project_and_commit(self.conn,payload,"commodity/3",self.received_at,123), schema="commodity/3", received_at=self.received_at)
            for call in mocks["project_markets"].call_args_list:
                self.assertIs(call.args[0], payload)
                self.assertEqual(call.args[1], self.received_at)
            self.assertEqual(state.call_count, 2)
            for call in state.call_args_list:
                self.assertEqual(call.kwargs["received_at"], self.received_at)
                self.assertEqual(call.kwargs["message_bytes"], 123)
            self.assertEqual(self.conn.commit.call_count, 2)
            self.conn.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
