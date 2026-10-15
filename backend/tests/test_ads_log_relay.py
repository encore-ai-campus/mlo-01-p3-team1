from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import StringIO
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from pymongo.errors import AutoReconnect

from domains.ads.errors import DatabaseUnavailable, DomainError
from workers.ads_log_relay import AdsLogRelay, run_configured_relay


def _value(document, path):
    for key in path.split("."):
        document = document[key]
    return document


def _matches(document, query):
    for field, expected in query.items():
        if field == "$or":
            if not any(_matches(document, item) for item in expected):
                return False
            continue
        actual = _value(document, field)
        if isinstance(expected, dict):
            if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                return False
        elif actual != expected:
            return False
    return True


def _set(document, path, value):
    parts = path.split(".")
    for key in parts[:-1]:
        document = document[key]
    document[parts[-1]] = value


class MemoryCollection:
    """unit 검증용 단일 문서 CAS입니다. 실제 MongoDB 검증을 대신하지 않습니다."""

    def __init__(self, document):
        self.document = deepcopy(document)
        self.lock = Lock()
        self.fail_next_ack = False

    def find_one_and_update(self, query, update, **kwargs):
        with self.lock:
            if not _matches(self.document, query):
                return None
            for field, value in update.get("$inc", {}).items():
                _set(self.document, field, _value(self.document, field) + value)
            for field, value in update.get("$set", {}).items():
                _set(self.document, field, value)
            return deepcopy(self.document)

    def update_one(self, query, update):
        with self.lock:
            if self.fail_next_ack:
                self.fail_next_ack = False
                raise AutoReconnect("mongodb://secret@private-host")
            if not _matches(self.document, query):
                return SimpleNamespace(matched_count=0)
            for field, value in update["$set"].items():
                _set(self.document, field, value)
            return SimpleNamespace(matched_count=1)


class AdsLogRelayTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
        self.original = {
            "_id": "log-1",
            "is_test": True,
            "created_at": self.now,
            "before_snapshot": {"title": "수정 전"},
            "after_snapshot": {"title": "수정 후"},
            "response_snapshot": {"http_status": 200, "body": {"version": 2}},
            "log_relay": {
                "log_event_id": "ads-admin:log-1",
                "payload": {"operation": "UPDATE", "version": 2},
                "payload_hash": "a" * 64,
                "status": "PENDING",
                "attempt_count": 0,
                "next_retry_at": None,
                "last_error": None,
                "sent_at": None,
            },
        }
        self.collection = MemoryCollection(self.original)

    def worker(self, sink=lambda log_event_id, payload, payload_hash: True):
        return AdsLogRelay(self.collection, sink, clock=lambda: self.now)

    @override_settings(ADS_LOG_SINK=None)
    def test_missing_sink_blocks_before_repository_access(self):
        with patch("workers.ads_log_relay.get_ads_repository") as get_repository:
            with self.assertRaises(DomainError) as caught:
                run_configured_relay()
        self.assertEqual(caught.exception.status, 503)
        get_repository.assert_not_called()

    def test_success_keeps_audit_response_and_payload_immutable(self):
        received = []

        def sink(log_event_id, payload, payload_hash):
            received.append((log_event_id, deepcopy(payload), payload_hash))
            payload["version"] = 99
            return True

        counts = self.worker(sink).run_once()
        self.assertEqual(counts, {"claimed": 1, "sent": 1, "failed": 0, "stale": 0})
        self.assertEqual(received[0][0], "ads-admin:log-1")
        document = self.collection.document
        for field in ("before_snapshot", "after_snapshot", "response_snapshot"):
            self.assertEqual(document[field], self.original[field])
        relay = document["log_relay"]
        self.assertEqual(relay["payload"], self.original["log_relay"]["payload"])
        self.assertEqual(relay["payload_hash"], "a" * 64)
        self.assertEqual(relay["status"], "SENT")
        self.assertEqual(relay["attempt_count"], 1)
        self.assertEqual(relay["sent_at"], self.now)

    def test_sink_exception_keeps_pending_and_only_exception_type(self):
        def failing_sink(*args):
            raise RuntimeError("postgresql://password@host SQL secret")

        counts = self.worker(failing_sink).run_once()
        relay = self.collection.document["log_relay"]
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(relay["status"], "PENDING")
        self.assertEqual(relay["last_error"], "RuntimeError")
        self.assertEqual(relay["next_retry_at"], self.now + timedelta(seconds=30))
        self.assertIsNone(relay["sent_at"])

    def test_false_or_none_does_not_acknowledge_sink_success(self):
        for accepted in (False, None):
            with self.subTest(accepted=accepted):
                self.collection = MemoryCollection(self.original)
                counts = self.worker(lambda *args: accepted).run_once()
                self.assertEqual(counts["failed"], 1)
                self.assertEqual(self.collection.document["log_relay"]["status"], "PENDING")
                self.assertEqual(
                    self.collection.document["log_relay"]["last_error"], "LogSinkRejected"
                )

    def test_only_one_worker_claims_unexpired_record(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: self.worker()._claim(), range(2)))
        self.assertEqual(sum(document is not None for document in claims), 1)
        self.assertEqual(self.collection.document["log_relay"]["attempt_count"], 1)

    def test_expired_claim_can_be_reclaimed_and_late_worker_cannot_ack(self):
        worker = self.worker()
        old_claim = worker._claim()
        self.now += timedelta(seconds=31)
        new_claim = self.worker()._claim()
        self.assertEqual(new_claim["log_relay"]["attempt_count"], 2)
        self.assertFalse(worker._finish(old_claim))
        self.assertEqual(self.collection.document["log_relay"]["status"], "PENDING")
        self.assertTrue(worker._finish(new_claim))

    def test_commit_before_ack_failure_redelivers_same_id_without_duplicate(self):
        persisted = {}
        delivered = []

        def idempotent_sink(log_event_id, payload, payload_hash):
            delivered.append(log_event_id)
            value = (payload, payload_hash)
            if log_event_id in persisted:
                if persisted[log_event_id] != value:
                    raise ValueError("동일 ID의 다른 payload")
            else:
                persisted[log_event_id] = value
            return True

        self.collection.fail_next_ack = True
        with self.assertRaises(DatabaseUnavailable):
            self.worker(idempotent_sink).run_once()
        self.assertEqual(self.collection.document["log_relay"]["status"], "PENDING")
        self.now += timedelta(seconds=31)
        counts = self.worker(idempotent_sink).run_once()
        self.assertEqual(counts["sent"], 1)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(delivered, ["ads-admin:log-1", "ads-admin:log-1"])

    def test_test_mode_does_not_claim_production_record(self):
        self.collection.document["is_test"] = False
        self.assertEqual(self.worker().run_once()["claimed"], 0)

    @override_settings(ADS_LOG_SINK=None)
    def test_command_reports_missing_sink_without_database(self):
        with patch("workers.ads_log_relay.get_ads_repository") as get_repository:
            with self.assertRaises(CommandError):
                call_command("relay_ads_logs", stdout=StringIO())
        get_repository.assert_not_called()

    def test_command_runs_bounded_batch_once(self):
        with patch(
            "domains.ads.management.commands.relay_ads_logs.run_configured_relay",
            return_value={"claimed": 1, "sent": 1, "failed": 0, "stale": 0},
        ) as run_once:
            output = StringIO()
            call_command("relay_ads_logs", limit=5, stdout=output)
        run_once.assert_called_once_with(5)
        self.assertIn("sent=1", output.getvalue())
