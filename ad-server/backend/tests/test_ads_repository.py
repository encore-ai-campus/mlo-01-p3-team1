"""드라이버 호출/실패 경계를 검사합니다. 실제 MongoDB 통합 시험을 대신하지 않습니다."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings
from pymongo import ReadPreference
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from domains.ads.errors import DatabaseUnavailable, VersionConflict
from repositories.ads_mongo import MongoAdsRepository


@override_settings(ADS_MONGODB_DATABASE="advertising_dev", ADS_IS_TEST=True)
class AdsRepositoryTests(SimpleTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.admin.command.return_value = {
            "setName": "shared-ads-replica",
            "isWritablePrimary": True,
        }
        self.database = self.client.get_database.return_value
        self.session = self.client.start_session.return_value.__enter__.return_value
        self.session.with_transaction.side_effect = lambda callback, **kwargs: callback(
            self.session
        )
        self.repository = MongoAdsRepository(self.client, "advertising_dev", is_test=True)
        self.now = datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)

    def test_standalone_or_secondary_does_not_run_mutation(self):
        for hello in ({"isWritablePrimary": True}, {"setName": "team-rs"}):
            with self.subTest(hello=hello):
                self.client.admin.command.return_value = hello
                callback = MagicMock()
                with self.assertRaises(DatabaseUnavailable):
                    self.repository.run(callback)
                callback.assert_not_called()
        self.client.start_session.assert_not_called()

    def test_transaction_configuration_and_all_writes_use_one_session(self):
        def mutate(transaction):
            transaction.insert_asset({"_id": "asset-1"})
            transaction.insert_ad({"_id": "ad-1"})
            transaction.insert_mutation({"_id": "change-1"})
            return {"ad_id": "ad-1"}

        self.assertEqual(self.repository.run(mutate), {"ad_id": "ad-1"})
        options = self.session.with_transaction.call_args.kwargs
        self.assertEqual(options["read_concern"].level, "snapshot")
        self.assertEqual(options["write_concern"].document, {"w": "majority"})
        self.assertEqual(options["read_preference"], ReadPreference.PRIMARY)
        for collection in ("ad_assets", "ads", "ad_admin_changes"):
            self.assertIs(
                self.database[collection].insert_one.call_args.kwargs["session"], self.session
            )

    def test_driver_callback_retry_cannot_mutate_service_document(self):
        original = {"_id": "stable-id", "meta": {"version": 1}}

        def driver_write(document, **kwargs):
            document["meta"]["version"] = 9

        self.database["ads"].insert_one.side_effect = driver_write

        def repeat_callback(callback, **kwargs):
            callback(self.session)
            return callback(self.session)

        self.session.with_transaction.side_effect = repeat_callback
        self.repository.run(lambda transaction: transaction.insert_ad(original))
        self.assertEqual(original, {"_id": "stable-id", "meta": {"version": 1}})
        self.assertEqual(self.database["ads"].insert_one.call_count, 2)

    def test_domain_error_keeps_conflict_status(self):
        conflict = VersionConflict()

        def mutate(transaction):
            raise conflict

        with self.assertRaises(VersionConflict) as raised:
            self.repository.run(mutate)
        self.assertIs(raised.exception, conflict)

    def test_failed_commit_returns_no_success_and_hides_driver_details(self):
        def fail_commit(callback, **kwargs):
            callback(self.session)
            raise ConnectionFailure("mongodb://secret:password@private")

        self.session.with_transaction.side_effect = fail_commit
        with self.assertRaises(DatabaseUnavailable) as raised:
            self.repository.run(lambda transaction: "success")
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(raised.exception.http_status, 503)

    def test_idempotency_unique_race_reopens_transaction_and_replays_winner(self):
        winner = {"response_snapshot": {"http_status": 201, "body": {"ad_id": "winner"}}}
        history = self.database["ad_admin_changes"]
        history.find_one.side_effect = [None, winner]
        history.insert_one.side_effect = DuplicateKeyError(
            "duplicate",
            11000,
            {"errmsg": "index: admin_idempotency dup key"},
        )

        def mutate(transaction):
            existing = transaction.get_mutation("shared", "admin", "CREATE", "ads", "hash")
            if existing:
                return existing["response_snapshot"]
            transaction.insert_mutation({"_id": "loser"})

        self.assertEqual(self.repository.run(mutate), winner["response_snapshot"])
        self.assertEqual(self.client.start_session.call_count, 2)
        self.assertEqual(history.insert_one.call_count, 1)

    def test_other_unique_conflict_is_not_replayed(self):
        self.database["ad_admin_changes"].insert_one.side_effect = DuplicateKeyError(
            "duplicate _id", 11000, {"keyPattern": {"_id": 1}}
        )
        with self.assertRaises(DatabaseUnavailable):
            self.repository.run(lambda transaction: transaction.insert_mutation({"_id": "same"}))
        self.assertEqual(self.client.start_session.call_count, 1)

    def test_write_outside_transaction_is_rejected(self):
        for write in (self.repository.insert_ad, self.repository.insert_asset):
            with self.subTest(write=write.__name__):
                with self.assertRaises(RuntimeError):
                    write({"_id": "outside"})

    def test_compare_and_swap_uses_expected_version_and_environment(self):
        collection = self.database["ads"]
        collection.replace_one.return_value.matched_count = 0
        result = self.repository.run(
            lambda transaction: transaction.replace_ad("ad-1", 3, {"_id": "ad-1", "version": 4})
        )
        self.assertFalse(result)
        self.assertEqual(
            collection.replace_one.call_args.args[0],
            {"_id": "ad-1", "version": 3, "is_test": True},
        )

    def test_unchanged_update_locks_with_real_write_and_restores_original(self):
        collection = self.database["ads"]
        for version, temporary_version in ((1, 2), (7, 1)):
            with self.subTest(version=version):
                collection.reset_mock()
                collection.replace_one.side_effect = [
                    SimpleNamespace(matched_count=1, modified_count=0),
                    SimpleNamespace(matched_count=1, modified_count=1),
                ]
                collection.update_one.return_value = SimpleNamespace(
                    matched_count=1, modified_count=1
                )
                original = {"_id": "ad-1", "version": version, "updated_at": self.now}
                result = self.repository.run(
                    lambda transaction: transaction.replace_ad("ad-1", version, original)
                )
                self.assertTrue(result)
                self.assertEqual(
                    collection.update_one.call_args.args,
                    (
                        {"_id": "ad-1", "version": version, "is_test": True},
                        {"$set": {"version": temporary_version}},
                    ),
                )
                restore = collection.replace_one.call_args_list[1]
                self.assertEqual(
                    restore.args[0],
                    {"_id": "ad-1", "version": temporary_version, "is_test": True},
                )
                self.assertEqual(restore.args[1], original)
                self.assertEqual(original["version"], version)
                self.assertEqual(original["updated_at"], self.now)
                self.assertIs(restore.kwargs["session"], self.session)
                self.assertIs(collection.update_one.call_args.kwargs["session"], self.session)

    def test_noop_lock_condition_conflict_aborts_before_restoration(self):
        collection = self.database["ads"]
        collection.replace_one.return_value = SimpleNamespace(matched_count=1, modified_count=0)
        collection.update_one.return_value = SimpleNamespace(matched_count=0, modified_count=0)
        with self.assertRaises(VersionConflict):
            self.repository.run(
                lambda transaction: transaction.replace_ad("ad-1", 1, {"_id": "ad-1", "version": 1})
            )
        self.assertEqual(collection.replace_one.call_count, 1)

    def test_noop_restore_conflict_does_not_return_success(self):
        collection = self.database["ads"]
        collection.replace_one.side_effect = [
            SimpleNamespace(matched_count=1, modified_count=0),
            SimpleNamespace(matched_count=0, modified_count=0),
        ]
        collection.update_one.return_value = SimpleNamespace(matched_count=1, modified_count=1)
        with self.assertRaises(VersionConflict):
            self.repository.run(
                lambda transaction: transaction.replace_ad("ad-1", 1, {"_id": "ad-1", "version": 1})
            )
        self.assertEqual(collection.replace_one.call_count, 2)

    def test_changed_update_does_not_run_noop_lock(self):
        collection = self.database["ads"]
        collection.replace_one.return_value = SimpleNamespace(matched_count=1, modified_count=1)
        result = self.repository.run(
            lambda transaction: transaction.replace_ad("ad-1", 1, {"_id": "ad-1", "version": 2})
        )
        self.assertTrue(result)
        collection.update_one.assert_not_called()

    def test_reads_are_detached_from_driver_and_share_test_scope(self):
        document = {"_id": "ad-1", "snapshot": {"title": "first"}}
        collection = self.database["ads"]
        collection.find_one.return_value = document
        result = self.repository.get_ad("ad-1")
        result["snapshot"]["title"] = "changed"
        self.assertEqual(document["snapshot"]["title"], "first")
        self.assertEqual(collection.find_one.call_args.args[0], {"_id": "ad-1", "is_test": True})

    def test_read_failure_becomes_service_unavailable(self):
        self.database["ad_assets"].find_one.side_effect = OperationFailure("private-driver-detail")
        with self.assertRaises(DatabaseUnavailable) as raised:
            self.repository.get_asset("asset-1")
        self.assertNotIn("private-driver-detail", str(raised.exception))

    def test_list_has_stable_sort_cursor_and_separate_more_flag(self):
        collection = self.database["ads"]
        collection.find.return_value.sort.return_value.limit.return_value = [
            {"_id": "b"},
            {"_id": "a"},
        ]
        documents, has_more = self.repository.list_ads(
            placement="top", status="ACTIVE", now=self.now, limit=1, cursor=(self.now, "c")
        )
        self.assertEqual(documents, [{"_id": "b"}])
        self.assertTrue(has_more)
        query = collection.find.call_args.args[0]
        self.assertEqual(query["starts_at"], {"$lte": self.now})
        self.assertEqual(query["ends_at"], {"$gt": self.now})
        self.assertEqual(query["$or"][1], {"updated_at": self.now, "_id": {"$lt": "c"}})
        collection.find.return_value.sort.assert_called_once_with([("updated_at", -1), ("_id", -1)])
        collection.find.return_value.sort.return_value.limit.assert_called_once_with(2)

    def test_stopped_filter_wins_over_schedule_and_summary_reports_actual_counts(self):
        collection = self.database["ads"]
        collection.find.return_value.sort.return_value.limit.return_value = []
        self.repository.list_ads(status="STOPPED", now=self.now)
        self.assertEqual(collection.find.call_args.args[0], {"is_test": True, "paused": True})
        collection.aggregate.return_value = [{"_id": "STOPPED", "count": 3}]
        self.assertEqual(
            self.repository.summary(self.now),
            {"RESERVED": 0, "ACTIVE": 0, "ENDED": 0, "STOPPED": 3},
        )
        pipeline = collection.aggregate.call_args.args[0]
        self.assertEqual(pipeline[0], {"$match": {"is_test": True}})
        status_expression = pipeline[1]["$group"]["_id"]["$switch"]
        self.assertEqual(status_expression["branches"][0], {"case": "$paused", "then": "STOPPED"})
