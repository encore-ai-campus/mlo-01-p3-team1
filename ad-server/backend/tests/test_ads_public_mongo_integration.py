"""공개 광고의 선택 실행형 실제 MongoDB 시험. 운영값·공유 DB에는 접근하지 않습니다."""

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, get_ident
from unittest import SkipTest
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.uri_parser import parse_uri

from domains.ads.errors import DatabaseUnavailable, IdempotencyConflict, NotFound
from domains.ads.mongo import load_manifest
from domains.ads.public_schema import load_public_manifest
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService, canonical_hash
from repositories.ads_public_mongo import MongoPublicAdsRepository
from tests.public_fixtures import fixture_public_policy
from tests.test_ads_mongo_integration import (
    DEFAULT_TEST_URI,
    INTEGRATION_DB_PATTERN,
    _cleanup_test_database,
    _image_bytes,
)
from workers.ads_logs import inspect_logs


class AdsPublicMongoIntegrationTests(SimpleTestCase):
    """ADS_RUN_MONGO_TESTS=1에서만 UUID 개발 DB의 실제 원자성/경합을 확인합니다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if os.environ.get("ADS_RUN_MONGO_TESTS") != "1":
            raise SkipTest("실제 MongoDB 미실행: ADS_RUN_MONGO_TESTS=1이 필요합니다.")
        uri = os.environ.get("ADS_TEST_MONGODB_URI", DEFAULT_TEST_URI)
        parsed = parse_uri(uri)
        if any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in parsed["nodelist"]):
            raise RuntimeError("공개 광고 통합 시험은 localhost MongoDB에만 연결합니다.")
        cls.mongo_client = MongoClient(
            uri,
            tz_aware=True,
            serverSelectionTimeoutMS=5000,
            timeoutMS=10000,
            readPreference="primary",
        )
        try:
            hello = cls.mongo_client.admin.command("hello")
            if hello.get("setName") != "ads-rs" or not hello.get("isWritablePrimary"):
                raise RuntimeError("공개 광고 통합 시험에는 ads-rs primary가 필요합니다.")
        except Exception:
            cls.mongo_client.close()
            raise
        cls.database_name = f"ads_integration_{uuid4().hex}_dev"
        if not INTEGRATION_DB_PATTERN.fullmatch(cls.database_name):
            cls.mongo_client.close()
            raise RuntimeError("통합 시험 DB 경계를 확인할 수 없습니다.")
        cls.addClassCleanup(_cleanup_test_database, cls.mongo_client, cls.database_name)
        cls.database = cls.mongo_client[cls.database_name]
        collections = {**load_manifest()["collections"], **load_public_manifest()["collections"]}
        cls.collection_names = tuple(collections)
        for name, definition in collections.items():
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
                cls.database[name].create_index(
                    [(key, order) for key, order in index["keys"]], **options
                )

    def setUp(self):
        if not INTEGRATION_DB_PATTERN.fullmatch(self.database_name):
            raise RuntimeError("시험 전용 DB 경계를 확인할 수 없습니다.")
        for name in self.collection_names:
            self.database[name].delete_many({})
        self.now = datetime(2026, 10, 15, 14, 59, tzinfo=UTC)
        self.repository = MongoPublicAdsRepository(
            self.mongo_client, self.database_name, is_test=False
        )
        self.manager = AdsService(self.repository, clock=lambda: self.now, is_test=False)
        self.actor = {"identity_source": "common-auth", "account_id": "isolated-test-admin"}
        asset = self.manager.upload_asset(
            _image_bytes(), actor=self.actor, idempotency_key="asset", request_id="asset-request"
        )
        self.asset_id = asset.body["asset_id"]
        self.service = AdsPublicService(
            self.repository,
            policy=fixture_public_policy(),
            signing_key="isolated-integration-fixture-key",
            public_base_url="https://ads.example.test",
            is_test=False,
            clock=lambda: self.now,
        )
        self.ad = self.create_ad()

    def create_ad(self, **overrides):
        return self.manager.create_ad(
            {
                "title": "공개 광고 통합 시험",
                "asset_id": self.asset_id,
                "link_url": "https://example.test/cafe",
                "placement": "top",
                "starts_at": self.now - timedelta(minutes=1),
                "ends_at": self.now + timedelta(hours=1),
                "priority": 1,
                **overrides,
            },
            actor=self.actor,
            idempotency_key=str(uuid4()),
            request_id="create-request",
        ).body

    def provide(self, placement="top", **overrides):
        return self.service.provide(
            placement,
            **{
                "owner_guest_id": "guest-one",
                "measurement_available": True,
                "request_id": "provide-request",
                **overrides,
            },
        )

    def event_data(self, delivery, event_type="VIEWABLE_IMPRESSION", **overrides):
        return {
            "event_id": str(uuid4()),
            "delivery_id": delivery["ad"]["delivery_id"],
            "event_type": event_type,
            "occurred_at": self.now,
            **overrides,
        }

    def record(self, delivery, data, **overrides):
        return self.service.record_event(
            data,
            **{
                "owner_guest_id": "guest-one",
                "measurement_available": True,
                "delivery_token": delivery["ad"]["delivery_token"],
                "request_id": "event-request",
                **overrides,
            },
        )

    def stop(self):
        current = self.database.ads.find_one({"_id": self.ad["ad_id"]})
        return self.manager.stop_ad(
            current["_id"],
            {"version": current["version"]},
            actor=self.actor,
            idempotency_key=str(uuid4()),
            request_id="stop-request",
        )

    def public_state(self):
        return {
            name: list(self.database[name].find().sort("_id", 1))
            for name in load_public_manifest()["collections"]
        }

    def concurrent(self, functions):
        barrier = Barrier(len(functions))

        def execute(function):
            barrier.wait(timeout=5)
            return function()

        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            futures = [executor.submit(execute, function) for function in functions]
            return [future.result(timeout=20) for future in futures]

    def test_real_delivery_atomically_stores_cursor_snapshot_and_explicit_policy(self):
        response = self.provide()
        self.assertEqual(set(self.database.list_collection_names()), set(self.collection_names))
        delivery = self.database.ad_deliveries.find_one({"_id": response["ad"]["delivery_id"]})
        rotation = self.database.ad_rotation_state.find_one({"placement": "top"})
        self.assertEqual(rotation["revision"], 1)
        self.assertEqual(rotation["last_ad_id"], self.ad["ad_id"])
        self.assertEqual(delivery["ad_snapshot"]["ad_id"], self.ad["ad_id"])
        self.assertEqual(delivery["event_expires_at"], self.now + timedelta(seconds=900))
        self.assertEqual(delivery["policy_version"], "FIXTURE/public/v1")
        self.assertEqual(delivery["response_snapshot"], response)
        self.assertEqual(self.database.ads.find_one()["version"], 1)

    def test_real_split_deadlines_keep_old_schema_compatible_and_accept_late_report(self):
        legacy = self.provide()
        self.assertNotIn(
            "display_expires_at",
            self.database.ad_deliveries.find_one({"_id": legacy["ad"]["delivery_id"]}),
        )
        self.service.policy = replace(
            self.service.policy,
            delivery_ttl_seconds=1800,
            split_deadlines=True,
            cap_at_midnight=True,
        )
        response = self.provide()
        delivery = self.database.ad_deliveries.find_one({"_id": response["ad"]["delivery_id"]})
        display_end = datetime(2026, 10, 15, 15, tzinfo=UTC)
        self.assertEqual(delivery["display_expires_at"], display_end)
        self.assertEqual(delivery["event_expires_at"], display_end + timedelta(seconds=300))
        with self.assertRaises(OperationFailure):
            self.database.ad_deliveries.update_one(
                {"_id": delivery["_id"]}, {"$set": {"display_expires_at": delivery["issued_at"]}}
            )
        self.now = display_end + timedelta(seconds=2)
        result = self.record(
            response, self.event_data(response, occurred_at=display_end - timedelta(seconds=1))
        )
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 1)

    def test_real_highest_priority_and_tie_rotation_are_separate_per_placement(self):
        top_leaders = sorted(
            [self.create_ad(priority=10)["ad_id"], self.create_ad(priority=10)["ad_id"]]
        )
        bottom_leaders = sorted(
            [
                self.create_ad(placement="bottom")["ad_id"],
                self.create_ad(placement="bottom")["ad_id"],
            ]
        )
        selected = [
            self.provide()["ad"]["ad_id"],
            self.provide("bottom")["ad"]["ad_id"],
            self.provide()["ad"]["ad_id"],
            self.provide("bottom")["ad"]["ad_id"],
        ]
        self.assertEqual(
            selected, [top_leaders[0], bottom_leaders[0], top_leaders[1], bottom_leaders[1]]
        )
        self.assertEqual(self.provide()["ad"]["ad_id"], top_leaders[0])

    def test_real_counted_event_commits_claim_repeat_ledger_and_local_log_together(self):
        delivery = self.provide()
        data = self.event_data(delivery)
        result = self.record(delivery, data)
        self.assertEqual(result["result"], "COUNTED")
        event = self.database.ad_events.find_one({"_id": data["event_id"]})
        stored_delivery = self.database.ad_deliveries.find_one({"_id": data["delivery_id"]})
        self.assertEqual(
            stored_delivery["claims"][data["event_type"]]["event_id"], data["event_id"]
        )
        self.assertEqual(self.database.ad_repeat_windows.count_documents({}), 1)
        usage = self.database.ad_estimated_usage_ledger.find_one({"event_id": data["event_id"]})
        self.assertEqual(usage["_id"], f"usage:{data['event_id']}")
        self.assertEqual(usage["estimated_tokens"], 8)
        self.assertEqual(usage["status"], "ESTIMATED")
        self.assertEqual(event["metric_date_kst"], "2026-10-15")
        self.assertEqual(event["log_record"]["log_schema_version"], "ads-mongo-log-20261015.1")
        self.assertEqual(
            event["log_record"]["payload_hash"], canonical_hash(event["log_record"]["payload"])
        )
        self.assertNotIn(delivery["ad"]["delivery_token"], str(event["log_record"]))

    def test_real_bottom_impression_and_click_keep_distinct_claims_and_units(self):
        self.create_ad(placement="bottom")
        delivery = self.provide("bottom")
        for event_type in ("VIEWABLE_IMPRESSION", "CLICK"):
            result = self.record(delivery, self.event_data(delivery, event_type))
            self.assertEqual(result["result"], "COUNTED")
        units = {
            row["event_type"]: row["estimated_tokens"]
            for row in self.database.ad_estimated_usage_ledger.find()
        }
        self.assertEqual(units, {"VIEWABLE_IMPRESSION": 5, "CLICK": 15})
        self.assertEqual(len(self.database.ad_deliveries.find_one()["claims"]), 2)

    def test_real_replay_after_stop_and_expiry_preserves_first_response_and_all_state(self):
        delivery = self.provide()
        data = self.event_data(delivery)
        first = self.record(delivery, data)
        self.now += timedelta(seconds=1)
        self.stop()
        self.now += timedelta(hours=2)
        before = self.public_state()
        self.assertEqual(self.record(delivery, data), first)
        self.assertEqual(self.public_state(), before)
        with self.assertRaises(IdempotencyConflict):
            self.record(delivery, {**data, "event_type": "CLICK"})
        self.assertEqual(self.public_state(), before)

    def test_real_concurrent_same_event_id_commits_one_event_and_one_usage(self):
        delivery = self.provide()
        data = self.event_data(delivery)
        responses = self.concurrent([lambda: self.record(delivery, data) for _ in range(4)])
        self.assertTrue(all(response == responses[0] for response in responses))
        self.assertEqual(self.database.ad_events.count_documents({}), 1)
        self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 1)
        self.assertEqual(self.database.ad_repeat_windows.find_one()["revision"], 1)

    def test_real_concurrent_distinct_ids_for_one_delivery_consume_one_type_only(self):
        delivery = self.provide()
        requests = [self.event_data(delivery) for _ in range(4)]
        responses = self.concurrent(
            [lambda data=data: self.record(delivery, data) for data in requests]
        )
        self.assertEqual(
            sorted(response["result"] for response in responses),
            ["COUNTED", "DELIVERY_DUPLICATE", "DELIVERY_DUPLICATE", "DELIVERY_DUPLICATE"],
        )
        self.assertEqual(self.database.ad_events.count_documents({}), 4)
        self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 1)

    def test_real_parallel_deliveries_share_repeat_window_and_suppressed_claim_is_consumed(self):
        deliveries = [self.provide() for _ in range(3)]
        requests = [self.event_data(delivery) for delivery in deliveries]
        responses = self.concurrent(
            [
                lambda delivery=delivery, data=data: self.record(delivery, data)
                for delivery, data in zip(deliveries, requests, strict=True)
            ]
        )
        self.assertEqual(
            sorted(response["result"] for response in responses),
            ["COUNTED", "REPEAT_SUPPRESSED", "REPEAT_SUPPRESSED"],
        )
        self.assertEqual(self.database.ad_repeat_windows.count_documents({}), 1)
        self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 1)
        for delivery in self.database.ad_deliveries.find():
            self.assertIn("VIEWABLE_IMPRESSION", delivery["claims"])

    def test_real_concurrent_request_key_replay_advances_rotation_once(self):
        responses = self.concurrent(
            [lambda: self.provide(idempotency_key="same-concurrent-delivery") for _ in range(4)]
        )
        self.assertTrue(all(response == responses[0] for response in responses))
        self.assertEqual(self.database.ad_deliveries.count_documents({}), 1)
        self.assertEqual(self.database.ad_rotation_state.find_one()["revision"], 1)

    def test_real_ledger_failure_rolls_back_claim_window_event_and_ad_lock(self):
        delivery = self.provide()
        data = self.event_data(delivery)
        public_before = self.public_state()
        ad_before = self.database.ads.find_one({"_id": self.ad["ad_id"]})
        with patch.object(
            MongoPublicAdsRepository,
            "insert_usage_entry",
            side_effect=DatabaseUnavailable("주입한 원장 저장 실패"),
        ):
            with self.assertRaises(DatabaseUnavailable):
                self.record(delivery, data)
        self.assertEqual(self.public_state(), public_before)
        self.assertEqual(self.database.ads.find_one({"_id": self.ad["ad_id"]}), ad_before)
        self.assertEqual(self.record(delivery, data)["result"], "COUNTED")

    def test_real_delayed_event_before_stop_uses_historical_active_snapshot(self):
        delivery = self.provide()
        occurred_at = self.now
        self.now += timedelta(seconds=10)
        self.stop()
        self.now += timedelta(seconds=10)
        result = self.record(delivery, self.event_data(delivery, occurred_at=occurred_at))
        self.assertEqual(result["result"], "COUNTED")
        invalid = self.event_data(delivery, "CLICK", occurred_at=self.now)
        self.assertEqual(self.record(delivery, invalid)["result"], "DELIVERY_INVALID")

    def test_real_stop_winning_after_candidate_read_retries_without_serving_stale_ad(self):
        entered = Event()
        resume = Event()
        public_thread = []
        original = MongoPublicAdsRepository.lock_ad
        blocked_once = []

        def pause_before_lock(repository, ad):
            if public_thread and get_ident() == public_thread[0] and not blocked_once:
                blocked_once.append(True)
                entered.set()
                if not resume.wait(timeout=8):
                    raise RuntimeError("중단 경합 시험 대기 시간이 초과되었습니다.")
            return original(repository, ad)

        def provide():
            public_thread.append(get_ident())
            return self.provide()

        with patch.object(MongoPublicAdsRepository, "lock_ad", pause_before_lock):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(provide)
                try:
                    self.assertTrue(entered.wait(timeout=5))
                    self.now += timedelta(seconds=1)
                    self.stop()
                finally:
                    resume.set()
                response = future.result(timeout=20)
        self.assertIsNone(response["ad"])
        self.assertEqual(self.database.ad_deliveries.count_documents({}), 0)
        self.assertEqual(self.database.ad_rotation_state.count_documents({}), 0)
        current = self.database.ads.find_one({"_id": self.ad["ad_id"]})
        self.assertTrue(current["paused"])
        self.assertEqual(current["version"], 2)

    def test_real_image_requires_proof_and_does_not_expose_owner_or_internal_metadata(self):
        delivery = self.provide()
        public_ad = delivery["ad"]
        self.assertEqual(
            set(public_ad),
            {
                "ad_id",
                "creative_version",
                "placement",
                "title",
                "image_url",
                "link_url",
                "delivery_id",
                "delivery_token",
            },
        )
        with self.assertRaises(NotFound):
            self.service.read_image(public_ad["delivery_id"], delivery_token="tampered")
        image_bytes, mime_type = self.service.read_image(
            public_ad["delivery_id"], delivery_token=public_ad["delivery_token"]
        )
        self.assertEqual(image_bytes, _image_bytes())
        self.assertEqual(mime_type, "image/png")
        with self.assertRaises(NotFound):
            self.record(delivery, self.event_data(delivery), owner_guest_id="guest-two")
        self.assertEqual(self.database.ad_events.count_documents({}), 0)

    def test_real_strict_validators_reject_boolean_revision_extras_and_nonestimated_ledger(self):
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        rotation = self.database.ad_rotation_state.find_one()
        bad_revision = {**rotation, "_id": "bad-revision", "placement": "bottom", "revision": True}
        event = self.database.ad_events.find_one()
        bad_event = {
            **event,
            "_id": "bad-event",
            "event_id": "bad-event",
            "raw_cookie": "forbidden",
        }
        ledger = self.database.ad_estimated_usage_ledger.find_one()
        bad_ledger = {
            **deepcopy(ledger),
            "_id": "bad-usage",
            "event_id": "bad-event",
            "status": "BILLED",
        }
        for collection, document in (
            ("ad_rotation_state", bad_revision),
            ("ad_events", bad_event),
            ("ad_estimated_usage_ledger", bad_ledger),
        ):
            with self.subTest(collection=collection):
                with self.assertRaises(OperationFailure) as raised:
                    self.database[collection].insert_one(document)
                self.assertEqual(raised.exception.code, 121)

    def test_real_log_inspection_and_event_replay_preserve_all_state(self):
        delivery = self.provide()
        data = self.event_data(delivery)
        first = self.record(delivery, data)
        before = self.public_state()
        report = inspect_logs(self.database, is_test=False)
        self.assertEqual(report["ad_events"]["stored"], 1)
        self.assertEqual(report["ad_events"]["sample_invalid"], 0)
        self.assertEqual(self.record(delivery, data), first)
        self.assertEqual(self.public_state(), before)
