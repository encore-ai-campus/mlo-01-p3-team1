"""공개 측정 로그 전달 연결을 검증합니다. 실제 PostgreSQL 연결은 사용하지 않습니다."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import StringIO
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from domains.ads.errors import DatabaseUnavailable, DomainError
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService
from tests.public_fixtures import MemoryPublicRepository, fixture_public_policy
from tests.test_ads_domain import image_bytes
from tests.test_ads_log_relay import MemoryCollection
from workers.ads_log_relay import AdsLogRelay, run_configured_event_relay


class AdsPublicLogRelayTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, tzinfo=UTC)
        identifiers = count(1)

        def id_factory():
            return f"fixture-relay-{next(identifiers)}"

        self.repository = MemoryPublicRepository(is_test=False)
        manager = AdsService(
            self.repository, clock=lambda: self.now, id_factory=id_factory, is_test=False
        )
        context = {
            "actor": {"identity_source": "common-auth", "account_id": "external-admin"},
            "request_id": "relay-setup",
        }
        asset = manager.upload_asset(image_bytes(), idempotency_key="asset", **context)
        manager.create_ad(
            {
                "title": "카페 광고",
                "asset_id": asset.body["asset_id"],
                "link_url": "https://example.test/cafe",
                "placement": "top",
                "starts_at": self.now,
                "ends_at": self.now + timedelta(hours=1),
                "priority": 1,
            },
            idempotency_key="advertisement",
            **context,
        )
        service = AdsPublicService(
            self.repository,
            policy=fixture_public_policy(),
            signing_key="fixture-public-log-signing-key-only",
            public_base_url="https://ads.example.test",
            is_test=False,
            clock=lambda: self.now,
            id_factory=id_factory,
        )
        delivery = service.provide(
            "top", owner_guest_id="guest-one", measurement_available=True, request_id="display"
        )
        service.record_event(
            {
                "event_id": "public-event-one",
                "delivery_id": delivery["ad"]["delivery_id"],
                "event_type": "VIEWABLE_IMPRESSION",
                "occurred_at": self.now,
            },
            owner_guest_id="guest-one",
            measurement_available=True,
            delivery_token=delivery["ad"]["delivery_token"],
            request_id="record-event",
        )
        self.original = self.repository.get_event("public-event-one")
        self.collection = MemoryCollection(self.original)

    def worker(self, sink):
        return AdsLogRelay(
            self.collection,
            sink,
            is_test=False,
            sort_field="processed_at",
            clock=lambda: self.now,
        )

    @override_settings(ADS_LOG_SINK=None)
    def test_missing_sink_blocks_before_any_ad_repository_access(self):
        with (
            patch("workers.ads_log_relay.get_public_ads_repository") as public_repository,
            patch("workers.ads_log_relay.get_ads_repository") as management_repository,
        ):
            with self.assertRaises(DomainError) as caught:
                run_configured_event_relay()
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.code, "LOG_SINK_UNAVAILABLE")
        public_repository.assert_not_called()
        management_repository.assert_not_called()

    def test_configured_event_relay_uses_public_collection_and_processing_order(self):
        repository = SimpleNamespace(database={"ad_events": self.collection}, is_test=False)
        with (
            override_settings(ADS_LOG_SINK=lambda *args: True),
            patch("workers.ads_log_relay.get_public_ads_repository", return_value=repository),
            patch("workers.ads_log_relay.get_ads_repository") as management_repository,
            patch.object(
                self.collection,
                "find_one_and_update",
                wraps=self.collection.find_one_and_update,
            ) as claim,
        ):
            counts = run_configured_event_relay(limit=1)
        self.assertEqual(counts, {"claimed": 1, "sent": 1, "failed": 0, "stale": 0})
        self.assertEqual(claim.call_args.kwargs["sort"], [("processed_at", 1), ("_id", 1)])
        management_repository.assert_not_called()

    def test_success_preserves_event_decision_response_payload_and_usage(self):
        original_usage = deepcopy(self.repository.usage)
        delivered = []

        def sink(event_id, payload, payload_hash):
            delivered.append((event_id, deepcopy(payload), payload_hash))
            payload["counted"] = False
            payload["estimated_tokens"] = 999
            return True

        counts = self.worker(sink).run_once()
        self.assertEqual(counts["sent"], 1)
        self.assertEqual(delivered[0][0], "ads-event:public-event-one")
        document = self.collection.document
        for field in self.original.keys() - {"log_relay"}:
            self.assertEqual(document[field], self.original[field], field)
        relay = document["log_relay"]
        self.assertEqual(relay["payload"], self.original["log_relay"]["payload"])
        self.assertEqual(relay["payload_hash"], self.original["log_relay"]["payload_hash"])
        self.assertEqual(relay["status"], "SENT")
        self.assertEqual(self.repository.usage, original_usage)
        self.assertEqual(document["result"], "COUNTED")
        self.assertEqual(document["estimated_tokens"], 8)

    def test_failed_sink_retains_pending_and_retry_uses_original_payload(self):
        def failing_sink(*args):
            raise RuntimeError("postgresql://secret@private-host SQL")

        failed = self.worker(failing_sink).run_once()
        self.assertEqual(failed["failed"], 1)
        relay = self.collection.document["log_relay"]
        self.assertEqual(relay["status"], "PENDING")
        self.assertEqual(relay["last_error"], "RuntimeError")
        self.assertIsNone(relay["sent_at"])
        received = []

        def sink(*args):
            received.append(args)
            return True

        self.assertEqual(self.worker(sink).run_once()["claimed"], 0)
        self.now += timedelta(seconds=30)
        self.assertEqual(self.worker(sink).run_once()["sent"], 1)
        self.assertEqual(received[0][0], self.original["log_relay"]["log_event_id"])
        self.assertEqual(received[0][1], self.original["log_relay"]["payload"])
        self.assertEqual(received[0][2], self.original["log_relay"]["payload_hash"])

    def test_commit_before_ack_failure_redelivers_same_event_id_idempotently(self):
        persisted = {}
        deliveries = []

        def sink(event_id, payload, payload_hash):
            deliveries.append(event_id)
            value = deepcopy(payload), payload_hash
            if event_id in persisted:
                if persisted[event_id] != value:
                    raise ValueError("기존 이벤트 ID의 payload가 다릅니다.")
            else:
                persisted[event_id] = value
            return True

        self.collection.fail_next_ack = True
        with self.assertRaises(DatabaseUnavailable):
            self.worker(sink).run_once()
        self.now += timedelta(seconds=31)
        self.assertEqual(self.worker(sink).run_once()["sent"], 1)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(deliveries, ["ads-event:public-event-one"] * 2)

    def test_sort_field_accepts_only_management_or_event_timestamp(self):
        self.assertEqual(AdsLogRelay(self.collection, lambda *args: True).sort_field, "created_at")
        for invalid in ("owner_guest_id", "$natural", None, ["processed_at"]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                AdsLogRelay(self.collection, lambda *args: True, sort_field=invalid)

    @override_settings(ADS_LOG_SINK=None)
    def test_command_reports_missing_sink_without_database_access(self):
        with patch("workers.ads_log_relay.get_public_ads_repository") as get_repository:
            with self.assertRaises(CommandError):
                call_command("relay_ads_event_logs", stdout=StringIO())
        get_repository.assert_not_called()

    def test_command_runs_one_bounded_event_batch(self):
        with patch(
            "domains.ads.management.commands.relay_ads_event_logs.run_configured_event_relay",
            return_value={"claimed": 1, "sent": 1, "failed": 0, "stale": 0},
        ) as run_once:
            output = StringIO()
            call_command("relay_ads_event_logs", limit=5, stdout=output)
        run_once.assert_called_once_with(5)
        self.assertIn("sent=1", output.getvalue())
