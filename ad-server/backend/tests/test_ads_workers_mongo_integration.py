"""격리된 실제 MongoDB에서 읽기 점검과 작업 재시도를 확인합니다. PostgreSQL 시험은 아닙니다."""

import os
import socket
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest import SkipTest
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri

from domains.ads.budget_service import AdsBudgetService
from domains.ads.service import AdsService
from repositories.ads_policy_mongo import MongoAdsPolicyRepository
from tests.test_ads_mongo_integration import _cleanup_test_database, _image_bytes
from tests.test_ads_runtime_check import CONFIGURATION
from workers.ads_jobs import AdsJob, AdsWorkerGroup
from workers.ads_logs import inspect_logs
from workers.ads_retention import inspect_retention
from workers.ads_runtime_check import expected_collections, inspect_runtime, schema_issues


@override_settings(**CONFIGURATION)
class AdsWorkersMongoIntegrationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if os.environ.get("ADS_RUN_MONGO_TESTS") != "1":
            raise SkipTest("실제 MongoDB 미실행: ADS_RUN_MONGO_TESTS=1이 필요합니다.")
        uri = os.environ["ADS_TEST_MONGODB_URI"]
        parsed = parse_uri(uri)
        if any(host not in {"127.0.0.1", "localhost", "::1"} for host, _ in parsed["nodelist"]):
            raise RuntimeError("격리된 loopback MongoDB만 사용할 수 있습니다.")
        if parsed["options"].get("directConnection") is not True:
            raise RuntimeError("시험 연결은 directConnection=true여야 합니다.")
        cls.mongo_client = MongoClient(
            uri, tz_aware=True, serverSelectionTimeoutMS=5000, timeoutMS=10000
        )
        try:
            hello = cls.mongo_client.admin.command("hello")
            if hello.get("setName") != "ads-rs" or not hello.get("isWritablePrimary"):
                raise RuntimeError("시험 ads-rs primary가 필요합니다.")
        except Exception:
            cls.mongo_client.close()
            raise
        cls.database_name = f"ads_integration_{uuid4().hex}_dev"
        cls.addClassCleanup(_cleanup_test_database, cls.mongo_client, cls.database_name)
        cls.database = cls.mongo_client[cls.database_name]
        for name, spec in expected_collections().items():
            cls.database.create_collection(
                name,
                validator=spec["validator"],
                validationLevel="strict",
                validationAction="error",
            )
            for index in spec["indexes"]:
                options = {key: deepcopy(value) for key, value in index.items() if key != "keys"}
                cls.database[name].create_index(index["keys"], **options)

    def setUp(self):
        for name in expected_collections():
            self.database[name].delete_many({})
        self.now = datetime(2026, 10, 15, tzinfo=UTC)
        self.repository = MongoAdsPolicyRepository(
            self.mongo_client, self.database_name, is_test=False
        )
        manager = AdsService(self.repository, clock=lambda: self.now, is_test=False)
        actor = {"account_id": "isolated-admin", "identity_source": "worker-fixture"}
        asset = manager.upload_asset(
            _image_bytes(),
            actor=actor,
            idempotency_key="image",
            request_id="image",
        )
        self.ad = manager.create_ad(
            {
                "title": "격리 시험 광고",
                "asset_id": asset.body["asset_id"],
                "link_url": "https://example.test",
                "placement": "top",
                "priority": 1,
                "starts_at": self.now,
                "ends_at": self.now + timedelta(days=1),
            },
            actor=actor,
            idempotency_key="ad",
            request_id="ad",
        ).body

    def test_inspection_does_not_mutate_originals_claims_or_metrics(self):
        before = {
            name: list(self.database[name].find({}).sort("_id", 1))
            for name in expected_collections()
        }

        def sink(*args):
            raise AssertionError("sink 호출 금지")

        with self.settings(ADS_LOG_SINK=sink):
            report = inspect_runtime(
                check_database=True,
                repository=self.repository,
                now=self.now + timedelta(seconds=60),
            )
        self.assertEqual(report["database"]["status"], "CHECKS_PASSED")
        self.assertEqual(report["status"], "CHECKS_PASSED")
        pending = report["database"]["logs"]["ad_admin_changes"]
        self.assertEqual(pending["stored"], 2)
        self.assertEqual(pending["sample_checked"], 2)
        self.assertEqual(pending["sample_invalid"], 0)
        self.assertEqual(report["log_storage"], "MONGODB")
        for name in expected_collections():
            self.assertEqual(before[name], list(self.database[name].find({}).sort("_id", 1)))

    def test_real_unique_index_drift_is_reported_without_repair(self):
        collection = self.database.ad_events
        collection.drop_index("public_event_id")
        try:
            collection.create_index([("event_id", 1)], name="public_event_id", unique=False)
            issues = schema_issues(self.database)
            self.assertIn(
                {"collection": "ad_events", "code": "INDEX_MISMATCH", "index": "public_event_id"},
                issues,
            )
            self.assertFalse(collection.index_information()["public_event_id"].get("unique", False))
        finally:
            collection.drop_index("public_event_id")
            collection.create_index([("event_id", 1)], name="public_event_id", unique=True)

    def test_legacy_logs_remain_readable_and_unmodified_under_new_validator(self):
        collection = self.database.ad_admin_changes
        document = collection.find_one({})
        local = document.pop("log_record")
        document["schema_version"] = "phase3-ads-data-20261014.3"
        document["log_relay"] = {
            "log_event_id": local["log_event_id"],
            "payload": local["payload"],
            "payload_hash": local["payload_hash"],
            "status": "PENDING",
            "attempt_count": 2,
            "next_retry_at": None,
            "last_error": "old-error",
            "sent_at": None,
        }
        collection.replace_one({"_id": document["_id"]}, document)
        before = list(collection.find({}).sort("_id", 1))
        report = inspect_logs(self.database, is_test=False)
        self.assertEqual(report["ad_admin_changes"]["legacy_preserved"], 1)
        self.assertEqual(report["ad_admin_changes"]["stored"], 1)
        self.assertEqual(report["ad_admin_changes"]["sample_invalid"], 0)
        self.assertEqual(before, list(collection.find({}).sort("_id", 1)))

    def test_corrupted_log_is_reported_without_repair_or_business_changes(self):
        collection = self.database.ad_admin_changes
        collection.update_one({}, {"$set": {"log_record.payload_hash": "0" * 64}})
        before = list(collection.find({}).sort("_id", 1))
        report = inspect_runtime(check_database=True, repository=self.repository, now=self.now)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["database"]["logs"]["ad_admin_changes"]["sample_invalid"], 1)
        self.assertEqual(before, list(collection.find({}).sort("_id", 1)))

    def test_retention_review_preserves_real_documents_indexes_and_binary_assets(self):
        before = {
            name: list(self.database[name].find({}).sort("_id", 1))
            for name in expected_collections()
        }
        indexes = {name: self.database[name].index_information() for name in expected_collections()}
        report = inspect_retention(
            self.database, is_test=False, now=self.now + timedelta(days=366), limit=1
        )
        self.assertEqual(report["status"], "REVIEW_READY")
        self.assertFalse(report["deletion_allowed"])
        admin = report["collections"]["ad_admin_changes"]
        self.assertTrue(admin["sample_has_more"])
        self.assertEqual(admin["sample_statuses"], {"REVIEW_DUE": 1})
        self.assertEqual(admin["sample_due_with_references"], 1)
        self.assertEqual(report["excluded"]["ad_assets"]["total"], 1)
        isolated = inspect_retention(self.database, is_test=True, now=self.now)
        self.assertTrue(all(row["total"] == 0 for row in isolated["collections"].values()))
        for name in expected_collections():
            self.assertEqual(before[name], list(self.database[name].find({}).sort("_id", 1)))
            self.assertEqual(indexes[name], self.database[name].index_information())

    def test_watch_connection_failure_then_restart_preserves_logs_and_avoids_duplicate_metrics(
        self,
    ):
        mutations = list(self.database.ad_admin_changes.find({}).sort("_id", 1))
        finished = threading.Event()
        with socket.socket() as unused_port:
            unused_port.bind(("127.0.0.1", 0))
            port = unused_port.getsockname()[1]
            client = MongoClient(
                f"mongodb://127.0.0.1:{port}/?directConnection=true",
                serverSelectionTimeoutMS=200,
                connectTimeoutMS=200,
                timeoutMS=500,
                tz_aware=True,
            )
            self.addCleanup(client.close)
            source = [MongoAdsPolicyRepository(client, self.database_name, is_test=False)]

            def refresh():
                try:
                    return AdsBudgetService(source[0], clock=lambda: self.now).run_once()
                finally:
                    finished.set()

            group = AdsWorkerGroup([AdsJob("policy", refresh, 300)])
            try:
                group.start()
                self.assertTrue(finished.wait(3))
            finally:
                self.assertTrue(group.stop(timeout=2))
            self.assertEqual(group.snapshot()["policy"]["status"], "ERROR")
            self.assertEqual(self.database.ad_daily_metrics.count_documents({}), 0)
            source[0] = self.repository
            for _ in range(2):
                finished.clear()
                try:
                    group.start()
                    self.assertTrue(finished.wait(3))
                finally:
                    self.assertTrue(group.stop(timeout=2))
                self.assertEqual(group.snapshot()["policy"]["status"], "OK")
                self.assertIsNone(group.snapshot()["policy"]["error"])
                self.assertEqual(self.database.ad_daily_metrics.count_documents({}), 1)
            self.assertEqual(
                mutations, list(self.database.ad_admin_changes.find({}).sort("_id", 1))
            )
            self.assertEqual(self.database.ad_estimated_usage_ledger.count_documents({}), 0)
