"""선택 실행하는 로컬 replica set 검증. 무작위 시험 DB만 만들고 정리합니다."""

import io
import os
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest import SkipTest
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.uri_parser import parse_uri

from domains.ads.errors import IdempotencyConflict, VersionConflict
from domains.ads.mongo import load_manifest
from domains.ads.service import AdsService, ad_status, canonical_hash
from repositories.ads_mongo import MongoAdsRepository

INTEGRATION_DB_PATTERN = re.compile(r"^ads_integration_[0-9a-f]{32}_dev$")
DEFAULT_TEST_URI = "mongodb://127.0.0.1:27018/?replicaSet=ads-rs&directConnection=true"


def _cleanup_test_database(mongo_client, database_name):
    if not INTEGRATION_DB_PATTERN.fullmatch(database_name):
        raise RuntimeError("시험 전용 DB 이름을 확인할 수 없어 삭제를 중단합니다.")
    try:
        mongo_client.drop_database(database_name)
    finally:
        mongo_client.close()


def _image_bytes(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(output, format="PNG")
    return output.getvalue()


class AdsMongoIntegrationTests(SimpleTestCase):
    """실제 MongoDB용이며 ADS_RUN_MONGO_TESTS=1일 때에만 실행합니다."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if os.environ.get("ADS_RUN_MONGO_TESTS") != "1":
            raise SkipTest("실제 MongoDB 미실행: ADS_RUN_MONGO_TESTS=1이 필요합니다.")
        uri = os.environ.get("ADS_TEST_MONGODB_URI", DEFAULT_TEST_URI)
        parsed = parse_uri(uri)
        if any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in parsed["nodelist"]):
            raise RuntimeError("통합 시험은 localhost MongoDB에만 연결합니다.")
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
                raise RuntimeError("통합 시험에는 ads-rs replica set primary가 필요합니다.")
        except Exception:
            cls.mongo_client.close()
            raise
        cls.database_name = f"ads_integration_{uuid4().hex}_dev"
        if not INTEGRATION_DB_PATTERN.fullmatch(cls.database_name):
            cls.mongo_client.close()
            raise RuntimeError("시험 전용 DB 이름을 확인할 수 없습니다.")
        cls.addClassCleanup(_cleanup_test_database, cls.mongo_client, cls.database_name)
        cls.database = cls.mongo_client[cls.database_name]
        manifest = load_manifest()
        cls.collection_names = tuple(manifest["collections"])
        for name, definition in manifest["collections"].items():
            cls.database.create_collection(
                name,
                validator=definition["validator"],
                validationLevel="strict",
                validationAction="error",
            )
            for index in definition["indexes"]:
                cls.database[name].create_index(
                    [(key, order) for key, order in index["keys"]],
                    name=index["name"],
                    unique=index.get("unique", False),
                )

    def setUp(self):
        # 이 클래스가 만든 UUID DB의 세 컬렉션만 다음 사례를 위해 비웁니다.
        if not INTEGRATION_DB_PATTERN.fullmatch(self.database_name):
            raise RuntimeError("시험 DB 경계를 확인할 수 없습니다.")
        for name in self.collection_names:
            self.database[name].delete_many({})
        self.now = datetime(2026, 10, 15, 1, 0, tzinfo=UTC)
        self.repository = MongoAdsRepository(self.mongo_client, self.database_name, is_test=True)
        self.service = AdsService(self.repository, clock=lambda: self.now, is_test=True)
        self.context = {
            "actor": {"identity_source": "common-auth", "account_id": "integration-admin"},
            "request_id": "integration-request",
        }
        self.original_bytes = _image_bytes()
        self.asset = self.service.upload_asset(
            self.original_bytes, idempotency_key="asset", **self.context
        )
        self.data = {
            "title": "카페 통합 시험",
            "asset_id": self.asset.body["asset_id"],
            "link_url": "https://example.com/cafe",
            "placement": "top",
            "starts_at": self.now,
            "ends_at": self.now + timedelta(hours=1),
            "priority": 1,
        }

    def create_ad(self):
        return self.service.create_ad(self.data, idempotency_key="create", **self.context)

    def test_real_lifecycle_commits_three_collections_and_pending_audit(self):
        created = self.create_ad()
        ad_id = created.body["ad_id"]
        updated = self.service.update_ad(
            ad_id,
            {**self.data, "title": "수정한 카페 광고", "version": 1},
            idempotency_key="update",
            **self.context,
        )
        stopped = self.service.stop_ad(
            ad_id,
            {"version": 2},
            idempotency_key="stop",
            **self.context,
        )
        self.assertEqual(updated.body["version"], 2)
        self.assertEqual(stopped.body["version"], 3)
        self.assertEqual(stopped.body["status"], "STOPPED")
        self.assertEqual(set(self.database.list_collection_names()), set(self.collection_names))
        self.assertEqual(self.database.ads.count_documents({}), 1)
        self.assertEqual(self.database.ad_assets.count_documents({}), 1)
        self.assertEqual(self.database.ad_admin_changes.count_documents({}), 4)
        for mutation in self.database.ad_admin_changes.find():
            self.assertEqual(mutation["log_relay"]["status"], "PENDING")
            self.assertEqual(
                mutation["log_relay"]["payload_hash"],
                canonical_hash(mutation["log_relay"]["payload"]),
            )
            self.assertNotIn("image_bytes", str(mutation["log_relay"]["payload"]))

    def test_upload_replay_and_replacement_preserve_original_bytes(self):
        replay = self.service.upload_asset(
            self.original_bytes,
            idempotency_key="asset",
            **self.context,
        )
        self.assertEqual(replay, self.asset)
        created = self.create_ad()
        new_asset = self.service.upload_asset(
            _image_bytes("blue"),
            idempotency_key="another-asset",
            **self.context,
        )
        self.assertNotEqual(new_asset.body["asset_id"], self.asset.body["asset_id"])
        self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "asset_id": new_asset.body["asset_id"], "version": 1},
            idempotency_key="replace-asset",
            **self.context,
        )
        original_asset = self.database.ad_assets.find_one({"_id": self.asset.body["asset_id"]})
        self.assertEqual(bytes(original_asset["image_bytes"]), self.original_bytes)
        self.assertEqual(self.database.ad_assets.count_documents({}), 2)

    def test_replay_returns_original_response_after_schedule_end(self):
        created = self.create_ad()
        self.now += timedelta(hours=2)
        replay = self.create_ad()
        self.assertEqual(replay, created)
        self.assertEqual(replay.body["status"], "ACTIVE")
        self.assertEqual(self.database.ads.count_documents({}), 1)
        self.assertEqual(self.database.ad_admin_changes.count_documents({"operation": "CREATE"}), 1)

    def test_stale_snapshot_noop_racing_update_preserves_committed_change(self):
        created = self.create_ad()
        ad_id = created.body["ad_id"]
        original = self.database.ads.find_one({"_id": ad_id})
        self.now += timedelta(minutes=5)
        first_reads = Barrier(2)

        def update_from_worker(noop):
            repository = MongoAdsRepository(self.mongo_client, self.database_name, is_test=True)
            service = AdsService(repository, clock=lambda: self.now, is_test=True)
            original_run = repository.run
            first_read = True

            def synchronized_run(callback):
                def synchronize_snapshot(transaction):
                    original_get_ad = transaction.get_ad

                    def read_then_wait(identifier):
                        nonlocal first_read
                        document = original_get_ad(identifier)
                        if first_read:
                            first_read = False
                            # 두 트랜잭션 모두 version=1 snapshot을 먼저 읽습니다.
                            first_reads.wait(timeout=5)
                        return document

                    with patch.object(transaction, "get_ad", side_effect=read_then_wait):
                        return callback(transaction)

                return original_run(synchronize_snapshot)

            values = {**self.data, "version": 1}
            if not noop:
                values["title"] = "동시에 저장한 새 광고"
            with patch.object(repository, "run", side_effect=synchronized_run):
                try:
                    return service.update_ad(
                        ad_id,
                        values,
                        idempotency_key="racing-noop" if noop else "racing-update",
                        **self.context,
                    )
                except VersionConflict as error:
                    return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            noop_future = pool.submit(update_from_worker, True)
            update_future = pool.submit(update_from_worker, False)
            noop_result = noop_future.result(timeout=15)
            update_result = update_future.result(timeout=15)

        # 무변경이 먼저 커밋하거나 갱신 뒤 409가 됩니다. 실제 갱신을 잃으면 안 됩니다.
        self.assertNotIsInstance(update_result, VersionConflict)
        self.assertTrue(update_result.body["changed"])
        self.assertEqual(update_result.body["version"], 2)
        final = self.database.ads.find_one({"_id": ad_id})
        self.assertEqual(final["title"], "동시에 저장한 새 광고")
        self.assertEqual(final["version"], 2)
        self.assertEqual(final["updated_at"], self.now)
        self.assertEqual(final["created_at"], original["created_at"])
        self.assertFalse(final["paused"])
        if not isinstance(noop_result, VersionConflict):
            self.assertFalse(noop_result.body["changed"])
            self.assertEqual(noop_result.body["version"], 1)
            self.assertEqual(noop_result.body["updated_at"], created.body["updated_at"])
        mutations = list(self.database.ad_admin_changes.find({"operation": "UPDATE"}))
        self.assertEqual(sum(mutation["changed"] for mutation in mutations), 1)
        for mutation in mutations:
            self.assertEqual(mutation["version_before"], 1)
            self.assertEqual(mutation["version_after"], 2 if mutation["changed"] else 1)

    def test_changed_body_idempotency_and_stale_version_conflict(self):
        created = self.create_ad()
        with self.assertRaises(IdempotencyConflict):
            self.service.create_ad(
                {**self.data, "priority": 2},
                idempotency_key="create",
                **self.context,
            )
        self.service.stop_ad(
            created.body["ad_id"],
            {"version": 1},
            idempotency_key="stop",
            **self.context,
        )
        with self.assertRaises(VersionConflict):
            self.service.update_ad(
                created.body["ad_id"],
                {**self.data, "version": 1},
                idempotency_key="stale",
                **self.context,
            )
        self.assertEqual(self.database.ads.find_one()["version"], 2)
        self.assertEqual(self.database.ad_admin_changes.count_documents({}), 3)

    def test_noop_preserves_stored_version_and_updated_at(self):
        created = self.create_ad()
        original = self.database.ads.find_one()
        self.now += timedelta(minutes=5)
        noop = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "version": 1},
            idempotency_key="noop",
            **self.context,
        )
        self.assertFalse(noop.body["changed"])
        self.assertEqual(self.database.ads.find_one(), original)
        self.assertEqual(noop.body["updated_at"], created.body["updated_at"])
        self.assertEqual(self.database.ad_admin_changes.count_documents({"changed": False}), 1)

    def test_database_filters_match_schedule_boundaries(self):
        self.create_ad()
        document = self.database.ads.find_one()
        start = document["starts_at"]
        end = document["ends_at"]
        for moment, expected in (
            (start - timedelta(milliseconds=1), "RESERVED"),
            (start, "ACTIVE"),
            (end, "ENDED"),
        ):
            with self.subTest(moment=moment):
                self.assertEqual(ad_status(document, moment), expected)
                entries, has_more = self.repository.list_ads(status=expected, now=moment)
                self.assertEqual(len(entries), 1)
                self.assertFalse(has_more)

    def test_database_validator_rejects_unknown_targeting_field(self):
        self.create_ad()
        document = self.database.ads.find_one()
        document.update({"_id": str(uuid4()), "target_tag_codes": ["CAFE"]})
        with self.assertRaises(OperationFailure) as error:
            self.database.ads.insert_one(document)
        self.assertEqual(error.exception.code, 121)
        self.assertEqual(self.database.ads.count_documents({}), 1)

    def test_database_validator_rejects_boolean_priority(self):
        self.create_ad()
        document = self.database.ads.find_one()
        document.update({"_id": str(uuid4()), "priority": True})
        with self.assertRaises(OperationFailure) as error:
            self.database.ads.insert_one(document)
        self.assertEqual(error.exception.code, 121)
        self.assertEqual(self.database.ads.count_documents({}), 1)

    def test_callback_failure_rolls_back_ad_and_audit_together(self):
        self.create_ad()
        ad = self.database.ads.find_one()
        change = self.database.ad_admin_changes.find_one({"operation": "CREATE"})
        ad = deepcopy(ad)
        change = deepcopy(change)
        ad["_id"] = str(uuid4())
        change.update({"_id": str(uuid4()), "ad_id": ad["_id"], "idempotency_key_hash": "a" * 64})
        before_ads = self.database.ads.count_documents({})
        before_changes = self.database.ad_admin_changes.count_documents({})

        def fail_after_writes(repository):
            repository.insert_ad(ad)
            repository.insert_mutation(change)
            raise RuntimeError("시험용 트랜잭션 중단")

        with self.assertRaisesRegex(RuntimeError, "시험용"):
            self.repository.run(fail_after_writes)
        self.assertEqual(self.database.ads.count_documents({}), before_ads)
        self.assertEqual(self.database.ad_admin_changes.count_documents({}), before_changes)
        self.assertIsNone(self.database.ads.find_one({"_id": ad["_id"]}))

    def test_simultaneous_same_key_create_returns_one_committed_result(self):
        start = Barrier(2)

        def create_from_worker():
            repository = MongoAdsRepository(self.mongo_client, self.database_name, is_test=True)
            service = AdsService(repository, clock=lambda: self.now, is_test=True)
            start.wait(timeout=5)
            return service.create_ad(self.data, idempotency_key="concurrent", **self.context)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create_from_worker(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.database.ads.count_documents({}), 1)
        self.assertEqual(self.database.ad_admin_changes.count_documents({"operation": "CREATE"}), 1)
