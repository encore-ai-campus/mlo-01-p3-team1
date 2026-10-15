"""선택 실행형 로컬 MongoDB: 검증 시각·늦은 초과 보고·집계/예산 원자성."""

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest import SkipTest
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DatabaseUnavailable, NotFound
from domains.ads.management.commands.apply_ads_policy_schema import load_policy_manifest
from domains.ads.mongo import load_manifest
from domains.ads.public_schema import load_public_manifest
from domains.ads.public_service import AdsPublicService
from domains.ads.runtime_policy import get_public_policy
from domains.ads.service import AdsService, serialize_ad
from repositories.ads_policy_mongo import MongoAdsPolicyRepository
from tests.test_ads_mongo_integration import (
    DEFAULT_TEST_URI,
    INTEGRATION_DB_PATTERN,
    _cleanup_test_database,
    _image_bytes,
)
from workers.ads_log_relay import AdsLogRelay


class AdsPolicyMongoIntegrationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if os.environ.get("ADS_RUN_MONGO_TESTS") != "1":
            raise SkipTest("실제 MongoDB 미실행: ADS_RUN_MONGO_TESTS=1이 필요합니다.")
        uri = os.environ.get("ADS_TEST_MONGODB_URI", DEFAULT_TEST_URI)
        parsed = parse_uri(uri)
        if any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in parsed["nodelist"]):
            raise RuntimeError("정책 시험은 localhost MongoDB만 사용합니다.")
        cls.mongo_client = MongoClient(
            uri, tz_aware=True, serverSelectionTimeoutMS=5000, timeoutMS=10000
        )
        hello = cls.mongo_client.admin.command("hello")
        if hello.get("setName") != "ads-rs" or not hello.get("isWritablePrimary"):
            cls.mongo_client.close()
            raise RuntimeError("정책 시험은 ads-rs primary가 필요합니다.")
        cls.database_name = f"ads_integration_{uuid4().hex}_dev"
        cls.addClassCleanup(_cleanup_test_database, cls.mongo_client, cls.database_name)
        cls.database = cls.mongo_client[cls.database_name]
        definitions = {
            **load_manifest()["collections"],
            **load_public_manifest()["collections"],
            **load_policy_manifest()["collections"],
        }
        cls.collection_names = tuple(definitions)
        for name, definition in definitions.items():
            cls.database.create_collection(
                name,
                validator=definition["validator"],
                validationLevel="strict",
                validationAction="error",
            )
            for index in definition["indexes"]:
                options = {"name": index["name"], "unique": index.get("unique", False)}
                if "partialFilterExpression" in index:
                    options["partialFilterExpression"] = index["partialFilterExpression"]
                cls.database[name].create_index(index["keys"], **options)

    def setUp(self):
        if not INTEGRATION_DB_PATTERN.fullmatch(self.database_name):
            raise RuntimeError("시험 DB 경계가 일치하지 않습니다.")
        for name in self.collection_names:
            self.database[name].delete_many({})
        self.now = datetime(2026, 10, 15, 5, tzinfo=UTC)
        self.origin = self.now
        self.repository = MongoAdsPolicyRepository(
            self.mongo_client, self.database_name, is_test=False
        )
        self.manager = AdsService(self.repository, clock=lambda: self.now, is_test=False)
        self.actor = {"identity_source": "common-auth", "account_id": "isolated-admin"}
        asset = self.manager.upload_asset(
            _image_bytes(), actor=self.actor, idempotency_key="asset", request_id="asset"
        )
        self.body = {
            "title": "정책 시험 광고",
            "asset_id": asset.body["asset_id"],
            "link_url": "https://example.test/ad",
            "placement": "top",
            "starts_at": self.now,
            "ends_at": self.now + timedelta(hours=3),
            "priority": 1,
            "daily_budget_tokens": 8,
            "total_budget_tokens": 1000,
        }
        self.ad = self.manager.create_ad(
            self.body, actor=self.actor, idempotency_key="create", request_id="create"
        ).body
        self.batch = AdsBudgetService(self.repository, clock=lambda: self.now)
        self.public = AdsPublicService(
            self.repository,
            policy=get_public_policy(),
            signing_key="isolated-test-key",
            public_base_url="https://ads.example.test",
            is_test=False,
            clock=lambda: self.now,
        )
        self.batch.run_once()

    def provide(self, **extra):
        return self.public.provide(
            "top",
            owner_guest_id="guest-one",
            measurement_available=True,
            request_id="provide",
            **extra,
        )

    def event(self, delivery, kind="VIEWABLE_IMPRESSION", *, occurred_at=None, event_id=None):
        return self.public.record_event(
            {
                "event_id": event_id or str(uuid4()),
                "delivery_id": delivery["ad"]["delivery_id"],
                "event_type": kind,
                "occurred_at": occurred_at or self.now,
            },
            owner_guest_id="guest-one",
            measurement_available=True,
            delivery_token=delivery["ad"]["delivery_token"],
            request_id="event",
        )

    def state(self):
        return self.database.ad_budget_states.find_one(
            {"ad_id": self.ad["ad_id"]}, sort=[("verified_at", -1)]
        )

    def test_real_usage_can_exceed_limit_before_verification_then_ad_ends(self):
        delivery = self.provide()
        self.assertEqual(self.event(delivery)["result"], "COUNTED")
        self.now += timedelta(seconds=1)
        self.assertEqual(self.event(delivery, "CLICK")["result"], "COUNTED")
        self.assertIsNotNone(self.provide()["ad"])
        self.now = self.origin + timedelta(seconds=300)
        self.batch.run_once()
        self.assertEqual(self.state()["daily_tokens"], 23)
        self.assertEqual(self.state()["daily_blocked_at"], self.now)
        self.assertIsNone(self.provide()["ad"])
        self.assertIsNone(
            self.provide(
                delivery_id=delivery["ad"]["delivery_id"],
                delivery_token=delivery["ad"]["delivery_token"],
            )["ad"]
        )
        with self.assertRaises(NotFound):
            self.public.read_image(
                delivery["ad"]["delivery_id"], delivery_token=delivery["ad"]["delivery_token"]
            )
        ad = self.repository.get_ad(self.ad["ad_id"])
        self.assertEqual(serialize_ad(ad, self.now)["end_reason"], "BUDGET_EXHAUSTED")
        self.assertEqual(self.repository.summary(self.now)["ENDED"], 1)
        rows, _ = self.repository.list_ads(status="ENDED", now=self.now)
        self.assertEqual(len(rows), 1)

    def test_real_cutoff_excludes_boundary_but_accepts_earlier_delayed_excess(self):
        delivery = self.provide()
        first_id = str(uuid4())
        first = self.event(delivery, event_id=first_id)
        self.now = self.origin + timedelta(seconds=300)
        self.batch.run_once()
        cutoff = self.now
        self.now += timedelta(seconds=1)
        invalid = self.event(delivery, "CLICK", occurred_at=cutoff)
        self.assertEqual(invalid["result"], "DELIVERY_INVALID")
        allowed = self.event(delivery, "CLICK", occurred_at=cutoff - timedelta(milliseconds=1))
        self.assertEqual(allowed["result"], "COUNTED")
        self.assertEqual(allowed["ads_policy_version"], "phase3-ads-20261015.1")
        self.assertEqual(self.event(delivery, occurred_at=self.origin, event_id=first_id), first)
        self.batch.run_once()
        self.assertEqual(self.state()["daily_blocked_at"], cutoff)
        summary = self.repository.metrics_summary(self.now)
        self.assertEqual(summary["today_estimated_tokens"], 23)
        self.assertEqual(summary["today_valid_clicks"], 1)
        self.batch.run_once()
        self.assertEqual(self.repository.metrics_summary(self.now)["today_estimated_tokens"], 23)

    def test_real_batch_failure_rolls_back_metrics_state_and_ad_annotation(self):
        self.event(self.provide())
        self.now += timedelta(seconds=300)
        names = ("ads", "ad_budget_states", "ad_daily_metrics")
        before = {name: list(self.database[name].find()) for name in names}
        with patch.object(
            MongoAdsPolicyRepository, "save_budget_state", side_effect=DatabaseUnavailable()
        ):
            with self.assertRaises(DatabaseUnavailable):
                self.batch.run_once()
        self.assertEqual(before, {name: list(self.database[name].find()) for name in names})

    def test_real_budget_increase_revalidates_and_preserves_old_cutoff(self):
        self.event(self.provide())
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        old_state = deepcopy(self.state())
        current = self.repository.get_ad(self.ad["ad_id"])
        updated = self.manager.update_ad(
            current["_id"],
            {**self.body, "daily_budget_tokens": 100, "version": current["version"]},
            actor=self.actor,
            idempotency_key="increase",
            request_id="increase",
        ).body
        self.assertNotEqual(updated["budget_version"], self.ad["budget_version"])
        self.assertIsNone(self.provide()["ad"])
        self.batch.run_once()
        self.assertIsNotNone(self.provide()["ad"])
        self.assertEqual(
            self.database.ad_budget_states.find_one({"_id": old_state["_id"]}), old_state
        )
        self.manager.stop_ad(
            current["_id"],
            {"version": updated["version"]},
            actor=self.actor,
            idempotency_key="stop",
            request_id="stop",
        )
        self.batch.run_once()
        self.assertIsNone(self.provide()["ad"])
        self.assertEqual(self.repository.summary(self.now)["STOPPED"], 1)

    def test_real_event_and_verification_race_is_serialized_without_lost_usage(self):
        delivery = self.provide()
        self.event(delivery)
        self.now += timedelta(seconds=300)
        barrier = Barrier(2)

        def measure():
            barrier.wait(timeout=5)
            return self.event(delivery, "CLICK", occurred_at=self.now - timedelta(seconds=1))

        def verify():
            barrier.wait(timeout=5)
            return self.batch.run_once()

        with ThreadPoolExecutor(max_workers=2) as executor:
            measured = executor.submit(measure)
            verified = executor.submit(verify)
            self.assertEqual(measured.result(timeout=20)["result"], "COUNTED")
            verified.result(timeout=20)
        self.batch.run_once()
        self.assertEqual(self.state()["daily_tokens"], 23)
        self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 2)

    def test_real_zero_metrics_and_budget_relay_retry_remain_distinct(self):
        self.assertEqual(self.repository.metrics_summary(self.now)["today_estimated_tokens"], 0)
        self.assertEqual(self.repository.metrics_summary(self.now)["aggregation_status"], "READY")
        self.event(self.provide())
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        cutoff = self.state()["daily_blocked_at"]
        worker = AdsLogRelay(
            self.database.ad_budget_states,
            lambda *args: False,
            is_test=False,
            clock=lambda: self.now,
        )
        self.assertEqual(worker.run_once()["failed"], 1)
        self.now += timedelta(seconds=31)
        worker.sink = lambda *args: True
        self.assertEqual(worker.run_once()["sent"], 1)
        self.assertEqual(self.state()["daily_blocked_at"], cutoff)
        self.batch.run_once()
        self.assertEqual(self.state()["log_relay"]["status"], "SENT")

    def test_real_ended_cursor_keeps_budget_or_period_filter(self):
        self.event(self.provide())
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        self.now += timedelta(seconds=1)
        active = self.manager.create_ad(
            {**self.body, "daily_budget_tokens": 100},
            actor=self.actor,
            idempotency_key="active",
            request_id="active",
        ).body
        self.now += timedelta(seconds=1)
        period_ended = self.manager.create_ad(
            {**self.body, "ends_at": self.now - timedelta(seconds=1)},
            actor=self.actor,
            idempotency_key="ended",
            request_id="ended",
        ).body
        first, more = self.repository.list_ads(status="ENDED", now=self.now, limit=1)
        self.assertTrue(more)
        self.assertEqual(first[0]["_id"], period_ended["ad_id"])
        second, _ = self.repository.list_ads(
            status="ENDED", now=self.now, limit=1, cursor=(first[0]["updated_at"], first[0]["_id"])
        )
        self.assertEqual(second[0]["_id"], self.ad["ad_id"])
        self.assertNotEqual(second[0]["_id"], active["ad_id"])
