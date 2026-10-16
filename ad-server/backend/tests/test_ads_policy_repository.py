"""예산·물리 집계 저장 경계를 검증하며 실제 MongoDB 실행은 별도입니다."""

import io
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from bson import Int64
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from pymongo.errors import DuplicateKeyError

from domains.ads.errors import ValidationError
from domains.ads.management.commands.apply_ads_policy_schema import load_policy_manifest
from repositories.ads_mongo import DuplicateMutation
from repositories.ads_policy_mongo import (
    POLICY_SCHEMA_VERSION,
    MongoAdsPolicyRepository,
)


@override_settings(ADS_MONGODB_DATABASE="advertising_dev", ADS_IS_TEST=False)
class AdsPolicyRepositoryTests(SimpleTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.admin.command.return_value = {"setName": "ads-rs", "isWritablePrimary": True}
        self.database = self.client.get_database.return_value
        self.collections = {}
        self.database.__getitem__.side_effect = lambda name: self.collections.setdefault(
            name, MagicMock()
        )
        self.session = self.client.start_session.return_value.__enter__.return_value
        self.session.with_transaction.side_effect = lambda callback, **kwargs: callback(
            self.session
        )
        self.repository = MongoAdsPolicyRepository(self.client, "advertising_dev", is_test=False)
        self.now = datetime(2026, 10, 15, 15, tzinfo=UTC)
        self.day = "2026-10-16"

    def collection(self, name):
        return self.database[name]

    def state(self, revision=1):
        return {
            "_id": self.repository.budget_state_id("ad-one", "budget-v1", self.day),
            "schema_version": POLICY_SCHEMA_VERSION,
            "is_test": False,
            "ad_id": "ad-one",
            "budget_version": "budget-v1",
            "metric_date_kst": self.day,
            "daily_budget_tokens": 100,
            "total_budget_tokens": 1000,
            "daily_tokens": 8,
            "total_tokens": 8,
            "created_at": self.now,
            "verified_at": self.now,
            "revision": revision,
            "daily_blocked_at": None,
            "total_blocked_at": None,
            "log_relay": None,
        }

    def metric(self, **overrides):
        return {
            "ad_id": "ad-one",
            "placement": "top",
            "metric_date_kst": self.day,
            "impressions": 1,
            "clicks": 0,
            "estimated_tokens": 8,
            "as_of": self.now,
            **overrides,
        }

    def test_run_keeps_policy_subclass_and_one_session_for_both_writes(self):
        seen = []

        def save(transaction):
            seen.append(transaction)
            transaction.save_budget_state(self.state(), None)
            transaction.replace_daily_metrics("ad-one", [self.metric()], self.now)

        self.repository.run(save)
        self.assertIsInstance(seen[0], MongoAdsPolicyRepository)
        self.assertIs(
            self.collection("ad_budget_states").insert_one.call_args.kwargs["session"], self.session
        )
        self.assertIs(
            self.collection("ad_daily_metrics").replace_one.call_args.kwargs["session"],
            self.session,
        )

    def test_all_policy_ads_are_environment_scoped_without_status_filter(self):
        records = [{"_id": "stopped-ad", "paused": True}]
        collection = self.collection("ads")
        collection.find.return_value = records
        returned = self.repository.list_policy_ads()
        self.assertEqual(collection.find.call_args.args[0], {"is_test": False})
        returned[0]["paused"] = False
        self.assertTrue(records[0]["paused"])

    def test_usage_groups_only_estimated_ledger_in_ad_environment(self):
        source = [self.metric()]
        collection = self.collection("ad_estimated_usage_ledger")
        collection.aggregate.return_value = source
        result = self.repository.usage_rows("ad-one")
        pipeline = collection.aggregate.call_args.args[0]
        self.assertEqual(
            pipeline[0], {"$match": {"ad_id": "ad-one", "is_test": False, "status": "ESTIMATED"}}
        )
        grouping = pipeline[1]["$group"]
        self.assertEqual(
            grouping["_id"], {"metric_date_kst": "$metric_date_kst", "placement": "$placement"}
        )
        self.assertEqual(grouping["estimated_tokens"], {"$sum": "$estimated_tokens"})
        result[0]["estimated_tokens"] = 999
        self.assertEqual(source[0]["estimated_tokens"], 8)

    def test_state_identity_scopes_version_day_and_environment_without_delimiter_collision(self):
        identities = {
            self.repository.budget_state_id("ad-one", "budget-v1", self.day),
            self.repository.budget_state_id("ad-one", "budget-v2", self.day),
            self.repository.budget_state_id("ad-one", "budget-v1", "2026-10-15"),
            self.repository.budget_state_id("ad-one:a", "b", self.day),
            self.repository.budget_state_id("ad-one", "a:b", self.day),
        }
        self.assertEqual(len(identities), 5)
        other = MongoAdsPolicyRepository(self.client, "advertising_dev", is_test=True)
        self.assertNotIn(other.budget_state_id("ad-one", "budget-v1", self.day), identities)
        for invalid in ("2026-1-01", "2026-02-30", None, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.repository.budget_state_id("ad-one", "budget-v1", invalid)

    def test_state_lookup_uses_scoped_hash_and_latest_verified_order(self):
        collection = self.collection("ad_budget_states")
        document = self.state()
        collection.find_one.return_value = document
        self.assertEqual(
            self.repository.get_budget_state("ad-one", "budget-v1", self.day), document
        )
        self.assertEqual(
            collection.find_one.call_args.args[0], {"_id": document["_id"], "is_test": False}
        )
        result = self.repository.latest_budget_state("ad-one", "budget-v1")
        self.assertEqual(
            collection.find_one.call_args.kwargs["sort"], [("verified_at", -1), ("_id", -1)]
        )
        result["revision"] = 99
        self.assertEqual(document["revision"], 1)

    def test_total_cutoff_returns_earliest_non_null_without_current_day_filter(self):
        collection = self.collection("ad_budget_states")
        cutoff = self.now - timedelta(days=1)
        collection.find_one.return_value = {"total_blocked_at": cutoff}
        self.assertEqual(self.repository.total_budget_cutoff("ad-one", "budget-v1"), cutoff)
        query = collection.find_one.call_args.args[0]
        self.assertEqual(
            query,
            {
                "ad_id": "ad-one",
                "budget_version": "budget-v1",
                "is_test": False,
                "total_blocked_at": {"$type": "date"},
            },
        )
        self.assertEqual(
            collection.find_one.call_args.kwargs["sort"], [("total_blocked_at", 1), ("_id", 1)]
        )
        collection.find_one.return_value = None
        self.assertIsNone(self.repository.total_budget_cutoff("ad-one", "budget-v1"))

    def test_state_cas_matches_previous_revision_and_does_not_upsert(self):
        collection = self.collection("ad_budget_states")
        collection.replace_one.return_value.matched_count = 1
        document = self.state(revision=2)
        self.repository.run(lambda transaction: transaction.save_budget_state(document, 1))
        call = collection.replace_one.call_args
        self.assertEqual(call.args[0], {"_id": document["_id"], "is_test": False, "revision": 1})
        self.assertNotIn("upsert", call.kwargs)
        self.assertIsNot(call.args[1], document)
        collection.replace_one.return_value.matched_count = 0
        transaction = MongoAdsPolicyRepository(
            self.client, "advertising_dev", is_test=False, session=self.session
        )
        with self.assertRaises(DuplicateMutation):
            transaction.save_budget_state(document, 1)

    def test_first_state_duplicate_reopens_transaction_to_read_winner(self):
        collection = self.collection("ad_budget_states")
        winner = self.state()
        collection.find_one.side_effect = [None, winner]
        collection.insert_one.side_effect = DuplicateKeyError("state race", 11000)

        def verify(transaction):
            existing = transaction.get_budget_state("ad-one", "budget-v1", self.day)
            if existing:
                return existing["revision"]
            transaction.save_budget_state(winner, None)

        self.assertEqual(self.repository.run(verify), 1)
        self.assertEqual(self.client.start_session.call_count, 2)

    def test_budget_writes_require_transaction_correct_environment_identity_and_revision(self):
        with self.assertRaises(RuntimeError):
            self.repository.save_budget_state(self.state(), None)
        with self.assertRaises(RuntimeError):
            self.repository.replace_daily_metrics("ad-one", [], self.now)
        for overrides, expected in (
            ({"is_test": True}, None),
            ({"_id": "forged"}, None),
            ({"revision": True}, None),
            ({"revision": 2}, None),
            ({"revision": 2}, True),
        ):
            with (
                self.subTest(overrides=overrides, expected=expected),
                self.assertRaises(ValidationError),
            ):
                self.repository.run(
                    lambda transaction: transaction.save_budget_state(
                        {**self.state(), **overrides}, expected
                    )
                )
        self.collection("ad_budget_states").insert_one.assert_not_called()
        self.collection("ad_budget_states").replace_one.assert_not_called()

    def test_metrics_replace_grouped_rows_idempotently_without_ledger_writes_or_deletes(self):
        rows = [self.metric()]
        self.repository.run(
            lambda transaction: transaction.replace_daily_metrics("ad-one", rows, self.now)
        )
        collection = self.collection("ad_daily_metrics")
        first = collection.replace_one.call_args
        self.assertTrue(first.kwargs["upsert"])
        document = deepcopy(first.args[1])
        self.assertEqual(document["source"], "ESTIMATED_LEDGER")
        self.assertEqual(document["impressions"], 1)
        self.repository.run(
            lambda transaction: transaction.replace_daily_metrics("ad-one", rows, self.now)
        )
        self.assertEqual(collection.replace_one.call_args.args[1], document)
        collection.delete_many.assert_not_called()
        self.assertNotIn("ad_estimated_usage_ledger", self.collections)

    def test_metrics_allow_explicit_zero_and_reject_negative_boolean_duplicate_groups(self):
        zero = self.metric(impressions=0, clicks=0, estimated_tokens=0)
        self.repository.run(
            lambda transaction: transaction.replace_daily_metrics("ad-one", [zero], self.now)
        )
        self.assertEqual(
            self.collection("ad_daily_metrics").replace_one.call_args.args[1]["estimated_tokens"], 0
        )
        for rows in (
            [self.metric(impressions=-1)],
            [self.metric(clicks=True)],
            [self.metric(estimated_tokens=2**63)],
            [self.metric(placement="side")],
            [self.metric(), self.metric()],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValidationError):
                self.repository.run(
                    lambda transaction: transaction.replace_daily_metrics("ad-one", rows, self.now)
                )

    def test_bson_int64_counts_and_revisions_are_valid_without_accepting_booleans(self):
        rows = [self.metric(impressions=Int64(1), clicks=Int64(0), estimated_tokens=Int64(8))]
        self.repository.run(
            lambda transaction: transaction.replace_daily_metrics("ad-one", rows, self.now)
        )
        self.collection("ad_budget_states").replace_one.return_value.matched_count = 1
        state = self.state(revision=Int64(2))
        self.repository.run(lambda transaction: transaction.save_budget_state(state, Int64(1)))
        self.assertEqual(
            self.collection("ad_budget_states").replace_one.call_args.args[0]["revision"], 1
        )

    def test_empty_metrics_are_pending_instead_of_fabricating_zero(self):
        self.collection("ad_daily_metrics").find.return_value = []
        self.collection("ads").find.return_value = [{"_id": "ad-one", "placement": "top"}]
        summary = self.repository.metrics_summary(self.now)
        self.assertEqual(summary["aggregation_status"], "PENDING")
        self.assertIsNone(summary["today_estimated_tokens"])
        self.assertIsNone(summary["lifetime_estimated_tokens"])
        self.assertIsNone(summary["as_of"])
        self.assertEqual(summary["coverage"], {"covered": 0, "expected": 1})

    def test_summary_reports_today_lifetime_kst_coverage_and_explicit_zero(self):
        self.collection("ads").find.return_value = [{"_id": "ad-one", "placement": "top"}]
        rows = [
            self.metric(impressions=0, estimated_tokens=0),
            self.metric(metric_date_kst="2026-10-15", impressions=2, estimated_tokens=16),
        ]
        self.collection("ad_daily_metrics").find.return_value = rows
        summary = self.repository.metrics_summary(self.now, ad_id="ad-one")
        self.assertEqual(summary["metric_date_kst"], "2026-10-16")
        self.assertEqual(summary["today_estimated_tokens"], 0)
        self.assertEqual(summary["lifetime_estimated_tokens"], 16)
        self.assertEqual(summary["lifetime_valid_impressions"], 2)
        self.assertEqual(summary["aggregation_status"], "READY")
        self.assertEqual(
            self.collection("ad_daily_metrics").find.call_args.args[0],
            {"is_test": False, "ad_id": "ad-one"},
        )
        self.assertEqual(
            self.collection("ads").find.call_args.args[0], {"is_test": False, "_id": "ad-one"}
        )
        self.collection("ads").find.return_value.append({"_id": "ad-two", "placement": "bottom"})
        self.assertEqual(self.repository.metrics_summary(self.now)["aggregation_status"], "PARTIAL")


class AdsPolicySchemaTests(SimpleTestCase):
    def test_manifest_limits_two_collections_strict_fields_positive_limits_and_unique_scopes(self):
        manifest = load_policy_manifest()
        self.assertEqual(set(manifest["collections"]), {"ad_budget_states", "ad_daily_metrics"})
        for name, definition in manifest["collections"].items():
            validator = definition["validator"]
            schema = validator.get("$jsonSchema") or validator["$and"][0]["$jsonSchema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertTrue(
                all("expireAfterSeconds" not in index for index in definition["indexes"])
            )
            index = next(index for index in definition["indexes"] if index.get("unique"))
            self.assertIn(["is_test", 1], index["keys"])
            if name == "ad_budget_states":
                self.assertEqual(schema["properties"]["daily_budget_tokens"]["minimum"], 1)
                self.assertEqual(schema["properties"]["total_budget_tokens"]["minimum"], 1)
                self.assertNotIn("log_relay", schema["required"])
                self.assertEqual(schema["properties"]["log_relay"]["bsonType"], ["object", "null"])

    def test_schema_dry_run_never_opens_database(self):
        output = io.StringIO()
        with patch(
            "domains.ads.management.commands.apply_ads_policy_schema.local_client"
        ) as connect:
            call_command("apply_ads_policy_schema", stdout=output)
        connect.assert_not_called()
        self.assertIn("ad_budget_states", output.getvalue())
        self.assertIn("미적용", output.getvalue())

    def test_apply_rejects_shared_host_or_non_dev_database_before_driver_creation(self):
        for uri, database in (
            ("mongodb://shared.private:27017/?replicaSet=ads-rs", "advertising_dev"),
            ("mongodb://127.0.0.1:27017/?replicaSet=ads-rs", "advertising"),
        ):
            with (
                self.subTest(uri=uri, database=database),
                self.settings(ADS_MONGODB_URI=uri, ADS_MONGODB_DATABASE=database),
                patch("domains.ads.mongo.MongoClient") as create,
            ):
                with self.assertRaises(CommandError):
                    call_command("apply_ads_policy_schema", apply=True, stdout=io.StringIO())
                create.assert_not_called()

    @override_settings(ADS_MONGODB_DATABASE="advertising_dev")
    def test_apply_uses_strict_error_validation_and_requires_ads_primary(self):
        client = MagicMock()
        client.admin.command.return_value = {"setName": "ads-rs", "isWritablePrimary": True}
        database = client.__getitem__.return_value
        database.list_collection_names.return_value = ["ad_budget_states"]
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        with patch("domains.ads.management.commands.apply_ads_policy_schema.local_client", factory):
            call_command("apply_ads_policy_schema", apply=True, stdout=io.StringIO())
        self.assertEqual(database.create_collection.call_count, 1)
        self.assertEqual(database.command.call_args.kwargs["validationLevel"], "strict")
        self.assertEqual(database.command.call_args.kwargs["validationAction"], "error")
        self.assertEqual(database.create_collection.call_args.kwargs["validationLevel"], "strict")
        client.admin.command.return_value = {"setName": "other-rs", "isWritablePrimary": True}
        with patch("domains.ads.management.commands.apply_ads_policy_schema.local_client", factory):
            with self.assertRaises(CommandError):
                call_command("apply_ads_policy_schema", apply=True, stdout=io.StringIO())
