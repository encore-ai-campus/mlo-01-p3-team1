"""공개 저장 어댑터의 트랜잭션/CAS/환경 경계. 실제 replica set 검증은 별도입니다."""

import io
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from pymongo.errors import DuplicateKeyError, OperationFailure

from domains.ads.errors import DatabaseUnavailable, ValidationError, VersionConflict
from domains.ads.public_schema import load_public_manifest
from repositories.ads_mongo import DuplicateMutation
from repositories.ads_public_mongo import (
    MongoPublicAdsRepository,
    _configured_public_repository,
    get_public_ads_repository,
)


@override_settings(ADS_MONGODB_DATABASE="advertising_dev", ADS_IS_TEST=False)
class PublicAdsRepositoryTests(SimpleTestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.admin.command.return_value = {"setName": "team-rs", "isWritablePrimary": True}
        self.database = self.client.get_database.return_value
        self.collections = {}
        self.database.__getitem__.side_effect = lambda name: self.collections.setdefault(
            name, MagicMock()
        )
        self.session = self.client.start_session.return_value.__enter__.return_value
        self.session.with_transaction.side_effect = lambda callback, **kwargs: callback(
            self.session
        )
        self.repository = MongoPublicAdsRepository(self.client, "advertising_dev", is_test=False)
        self.now = datetime(2026, 10, 15, tzinfo=UTC)

    def tearDown(self):
        _configured_public_repository.cache_clear()

    def collection(self, name):
        return self.database[name]

    def test_run_keeps_public_subclass_and_session_for_all_atomic_components(self):
        seen = []

        def mutate(transaction):
            seen.append(transaction)
            transaction.insert_delivery({"_id": "delivery", "is_test": False})
            transaction.insert_event({"_id": "event", "is_test": False})
            transaction.insert_usage_entry({"_id": "event", "is_test": False})

        self.repository.run(mutate)
        self.assertIsInstance(seen[0], MongoPublicAdsRepository)
        for name in ("ad_deliveries", "ad_events", "ad_estimated_usage_ledger"):
            self.assertIs(
                self.collection(name).insert_one.call_args.kwargs["session"], self.session
            )

    def test_candidates_exclude_stopped_wrong_scope_and_end_boundary_with_stable_order(self):
        candidates = [{"_id": "a", "priority": 1}]
        collection = self.collection("ads")
        collection.find.return_value.sort.return_value = candidates
        result = self.repository.list_candidates("top", self.now)
        self.assertEqual(result, candidates)
        result[0]["priority"] = 9
        self.assertEqual(candidates[0]["priority"], 1)
        self.assertEqual(
            collection.find.call_args.args[0],
            {
                "placement": "top",
                "is_test": False,
                "paused": False,
                "starts_at": {"$lte": self.now},
                "ends_at": {"$gt": self.now},
            },
        )
        collection.find.return_value.sort.assert_called_once_with([("priority", -1), ("_id", 1)])

    def test_rotation_initial_insert_then_cas_increments_revision_and_scopes_environment(self):
        collection = self.collection("ad_rotation_state")
        collection.update_one.return_value.matched_count = 1
        self.repository.run(lambda t: t.advance_rotation("top", None, "ad-a", self.now))
        first = collection.insert_one.call_args.args[0]
        self.assertEqual(first["revision"], 1)
        self.assertFalse(first["is_test"])
        self.repository.run(lambda t: t.advance_rotation("top", 1, "ad-b", self.now))
        query, update = collection.update_one.call_args.args
        self.assertEqual(query["_id"], first["_id"])
        self.assertEqual(query["revision"], 1)
        self.assertFalse(query["is_test"])
        self.assertEqual(
            update,
            {"$set": {"last_ad_id": "ad-b", "updated_at": self.now}, "$inc": {"revision": 1}},
        )

    def test_state_insert_collision_reopens_transaction_and_sees_winner(self):
        collection = self.collection("ad_rotation_state")
        collection.find_one.side_effect = [None, {"revision": 1}]
        collection.insert_one.side_effect = DuplicateKeyError("cursor race", 11000)

        def rotate(transaction):
            current = transaction.get_rotation("top")
            if current:
                return current["revision"]
            transaction.advance_rotation("top", None, "a", self.now)

        self.assertEqual(self.repository.run(rotate), 1)
        self.assertEqual(self.client.start_session.call_count, 2)

    def test_failed_state_cas_does_not_upsert_or_overwrite_winner(self):
        self.collection("ad_rotation_state").update_one.return_value.matched_count = 0
        transaction = MongoPublicAdsRepository(
            self.client, "advertising_dev", is_test=False, session=self.session
        )
        with self.assertRaises(DuplicateMutation):
            transaction.advance_rotation("top", 3, "b", self.now)
        self.assertNotIn("upsert", self.collection("ad_rotation_state").update_one.call_args.kwargs)

    def test_repeat_identity_is_per_owner_ad_placement_type_and_environment(self):
        collection = self.collection("ad_repeat_windows")
        inputs = [
            ("owner", "ad", "top", "CLICK"),
            ("other", "ad", "top", "CLICK"),
            ("owner", "ad", "bottom", "CLICK"),
            ("owner", "ad", "top", "VIEWABLE_IMPRESSION"),
        ]
        for parts in inputs:
            self.repository.get_repeat_window(*parts)
        ids = [call.args[0]["_id"] for call in collection.find_one.call_args_list]
        self.assertEqual(len(set(ids)), len(inputs))
        other_scope = MongoPublicAdsRepository(self.client, "advertising_dev", is_test=True)
        other_scope.get_repeat_window(*inputs[0])
        self.assertNotIn(collection.find_one.call_args.args[0]["_id"], ids)
        self.assertTrue(collection.find_one.call_args.args[0]["is_test"])

    def test_repeat_state_initializes_at_one_and_compares_previous_revision(self):
        collection = self.collection("ad_repeat_windows")
        collection.update_one.return_value.matched_count = 1
        args = ("owner", "ad", "top", "CLICK")
        self.repository.run(lambda t: t.advance_repeat_window(*args, None, self.now))
        document = collection.insert_one.call_args.args[0]
        self.assertEqual(document["revision"], 1)
        self.assertEqual(document["accepted_at"], self.now)
        self.repository.run(lambda t: t.advance_repeat_window(*args, 7, self.now))
        self.assertEqual(collection.update_one.call_args.args[0]["revision"], 7)
        self.assertEqual(collection.update_one.call_args.args[1]["$inc"], {"revision": 1})

    def test_unique_event_collision_replays_committed_result_after_new_transaction(self):
        collection = self.collection("ad_events")
        winner = {"response_snapshot": {"result": "COUNTED"}}
        collection.find_one.side_effect = [None, winner]
        collection.insert_one.side_effect = DuplicateKeyError("event race", 11000)

        def record(transaction):
            existing = transaction.get_event("event")
            if existing:
                return existing["response_snapshot"]
            transaction.insert_event({"_id": "event", "is_test": False})

        self.assertEqual(self.repository.run(record), winner["response_snapshot"])
        self.assertEqual(self.client.start_session.call_count, 2)
        self.assertEqual(collection.insert_one.call_count, 1)

    def test_delivery_request_lookup_scopes_nullable_owner_placement_and_hash(self):
        collection = self.collection("ad_deliveries")
        self.repository.get_delivery_request(None, "bottom", "a" * 64)
        self.assertEqual(
            collection.find_one.call_args.args[0],
            {
                "owner_guest_id": None,
                "placement": "bottom",
                "request_key_hash": "a" * 64,
                "is_test": False,
            },
        )

    def test_claim_only_first_type_conditional_and_preserves_other_claim(self):
        collection = self.collection("ad_deliveries")
        collection.update_one.return_value.matched_count = 1
        self.repository.run(
            lambda t: t.claim_delivery_type(
                "delivery", "CLICK", "event", "REPEAT_SUPPRESSED", self.now
            )
        )
        query, update = collection.update_one.call_args.args
        self.assertEqual(
            query, {"_id": "delivery", "is_test": False, "claims.CLICK": {"$exists": False}}
        )
        self.assertEqual(list(update["$set"]), ["claims.CLICK"])
        collection.update_one.return_value.matched_count = 0
        transaction = MongoPublicAdsRepository(
            self.client, "advertising_dev", is_test=False, session=self.session
        )
        with self.assertRaises(DuplicateMutation):
            transaction.claim_delivery_type("delivery", "CLICK", "event", "COUNTED", self.now)

    def test_claim_rejects_untrusted_field_path_and_unconsuming_decision(self):
        for event_type, result in (("CLICK.$set", "COUNTED"), ("CLICK", "DELIVERY_INVALID")):
            with self.subTest(event_type=event_type, result=result):
                with self.assertRaises(ValidationError):
                    self.repository.run(
                        lambda t: t.claim_delivery_type(
                            "delivery", event_type, "event", result, self.now
                        )
                    )
        self.collection("ad_deliveries").update_one.assert_not_called()

    def test_touch_uses_max_to_keep_latest_receive_time(self):
        collection = self.collection("ad_deliveries")
        collection.update_one.return_value.matched_count = 1
        self.repository.run(lambda t: t.touch_delivery("delivery", self.now))
        self.assertEqual(
            collection.update_one.call_args.args[1], {"$max": {"last_received_at": self.now}}
        )

    def test_reconfirmation_updates_usage_time_without_inventing_event_receive_time(self):
        collection = self.collection("ad_deliveries")
        collection.update_one.return_value.matched_count = 1
        self.repository.run(lambda t: t.touch_delivery("delivery", None, used_at=self.now))
        self.assertEqual(
            collection.update_one.call_args.args[1], {"$max": {"last_used_at": self.now}}
        )
        with self.assertRaises(ValidationError):
            self.repository.run(lambda t: t.touch_delivery("delivery", None))

    def test_historical_lookup_uses_server_change_time_and_version_tiebreak(self):
        collection = self.collection("ad_admin_changes")
        snapshot = {"ad_id": "ad", "starts_at": "2026-10-15T00:00:00.000Z"}
        collection.find_one.return_value = {"after_snapshot": snapshot}
        found = self.repository.historical_ad("ad", self.now)
        self.assertEqual(found, snapshot)
        found["ad_id"] = "changed"
        self.assertEqual(snapshot["ad_id"], "ad")
        call = collection.find_one.call_args
        self.assertEqual(call.args[0]["occurred_at"], {"$lte": self.now})
        self.assertFalse(call.args[0]["is_test"])
        self.assertEqual(call.kwargs["sort"], [("occurred_at", -1), ("version_after", -1)])

    def test_ad_lock_restores_unchanged_ad_and_turns_cas_failure_into_retry(self):
        ad = {"_id": "ad", "version": 7}
        with patch.object(MongoPublicAdsRepository, "replace_ad", return_value=True) as write:
            self.repository.run(lambda t: t.lock_ad(ad))
        write.assert_called_once_with("ad", 7, ad)
        self.assertIsNot(write.call_args.args[2], ad)
        transaction = MongoPublicAdsRepository(
            self.client, "advertising_dev", is_test=False, session=self.session
        )
        for failure in (False, VersionConflict()):
            with self.subTest(failure=failure):
                kwargs = (
                    {"side_effect": failure}
                    if isinstance(failure, Exception)
                    else {"return_value": failure}
                )
                with patch.object(MongoPublicAdsRepository, "replace_ad", **kwargs):
                    with self.assertRaises(DuplicateMutation):
                        transaction.lock_ad(ad)

    def test_public_writes_reject_nontransaction_or_wrong_environment(self):
        writes = [
            lambda: self.repository.insert_delivery({"is_test": False}),
            lambda: self.repository.insert_event({"is_test": False}),
            lambda: self.repository.insert_usage_entry({"is_test": False}),
            lambda: self.repository.advance_rotation("top", None, "ad", self.now),
            lambda: self.repository.advance_repeat_window(
                "owner", "ad", "top", "CLICK", None, self.now
            ),
            lambda: self.repository.claim_delivery_type("d", "CLICK", "e", "COUNTED", self.now),
            lambda: self.repository.touch_delivery("d", self.now),
        ]
        for write in writes:
            with self.subTest(write=write):
                with self.assertRaises(RuntimeError):
                    write()
        with self.assertRaises(ValidationError):
            self.repository.run(lambda t: t.insert_delivery({"_id": "d", "is_test": True}))
        self.collection("ad_deliveries").insert_one.assert_not_called()

    def test_driver_write_conflict_label_reaches_driver_callback_retry(self):
        collection = self.collection("ad_events")
        failure = OperationFailure(
            "WriteConflict", 112, {"errorLabels": ["TransientTransactionError"]}
        )
        collection.insert_one.side_effect = failure
        transaction = MongoPublicAdsRepository(
            self.client, "advertising_dev", is_test=False, session=self.session
        )
        with self.assertRaises(OperationFailure) as raised:
            transaction.insert_event({"_id": "e", "is_test": False})
        self.assertIs(raised.exception, failure)
        self.assertTrue(raised.exception.has_error_label("TransientTransactionError"))

    @override_settings(ADS_MONGODB_URI="mongodb://ads.private:27017/?replicaSet=team-rs")
    def test_public_repository_factory_reuses_client_and_returns_public_adapter(self):
        with patch(
            "repositories.ads_public_mongo.MongoClient", return_value=self.client
        ) as factory:
            first = get_public_ads_repository()
            self.assertIs(get_public_ads_repository(), first)
        self.assertIsInstance(first, MongoPublicAdsRepository)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs["readPreference"], "primary")
        self.assertEqual(
            factory.call_args.args[0], "mongodb://ads.private:27017/?replicaSet=team-rs"
        )

    @override_settings(ADS_MONGODB_URI="")
    def test_unconfigured_public_repository_does_not_create_driver(self):
        with patch("repositories.ads_public_mongo.MongoClient") as factory:
            with self.assertRaises(DatabaseUnavailable):
                get_public_ads_repository()
        factory.assert_not_called()


class PublicAdsSchemaTests(SimpleTestCase):
    def test_manifest_adds_only_five_public_collections_without_ttl_or_extra_business_fields(self):
        manifest = load_public_manifest()
        self.assertEqual(
            set(manifest["collections"]),
            {
                "ad_rotation_state",
                "ad_deliveries",
                "ad_events",
                "ad_repeat_windows",
                "ad_estimated_usage_ledger",
            },
        )
        for name, definition in manifest["collections"].items():
            self.assertTrue(
                all("expireAfterSeconds" not in index for index in definition["indexes"])
            )
            validator = definition["validator"]
            schema = validator.get("$jsonSchema") or validator["$and"][0]["$jsonSchema"]
            self.assertFalse(schema["additionalProperties"])
            optional = (
                {"display_expires_at", "budget_policy_version"}
                if name == "ad_deliveries"
                else set()
            )
            if name == "ad_events":
                optional |= {"log_record", "log_relay"}
                self.assertEqual(
                    schema["anyOf"],
                    [{"required": ["log_record"]}, {"required": ["log_relay"]}],
                )
            self.assertEqual(set(schema["required"]), set(schema["properties"]) - optional)

    def test_delivery_optional_idempotency_key_has_partial_unique_index(self):
        indexes = load_public_manifest()["collections"]["ad_deliveries"]["indexes"]
        unique = next(index for index in indexes if index.get("unique"))
        self.assertEqual(
            unique["partialFilterExpression"], {"request_key_hash": {"$type": "string"}}
        )
        self.assertEqual(
            unique["keys"],
            [["owner_guest_id", 1], ["placement", 1], ["request_key_hash", 1], ["is_test", 1]],
        )

    def test_schema_dry_run_does_not_open_database(self):
        output = io.StringIO()
        with patch(
            "domains.ads.management.commands.apply_ads_public_schema.local_client"
        ) as factory:
            call_command("apply_ads_public_schema", stdout=output)
        factory.assert_not_called()
        self.assertIn("ad_events", output.getvalue())
        self.assertIn("미적용", output.getvalue())

    @override_settings(
        ADS_MONGODB_URI="mongodb://shared.private:27017/?replicaSet=ads-rs",
        ADS_MONGODB_DATABASE="advertising_dev",
    )
    def test_apply_refuses_shared_host_before_driver_creation(self):
        with patch("domains.ads.mongo.MongoClient") as factory:
            with self.assertRaises(CommandError):
                call_command("apply_ads_public_schema", apply=True, stdout=io.StringIO())
        factory.assert_not_called()

    @override_settings(ADS_MONGODB_DATABASE="advertising_dev")
    def test_apply_forwards_partial_unique_index_and_strict_validation(self):
        client = MagicMock()
        client.admin.command.return_value = {"setName": "ads-rs", "isWritablePrimary": True}
        database = client.__getitem__.return_value
        database.list_collection_names.return_value = []
        factory = MagicMock()
        factory.return_value.__enter__.return_value = client
        with patch("domains.ads.management.commands.apply_ads_public_schema.local_client", factory):
            call_command("apply_ads_public_schema", apply=True, stdout=io.StringIO())
        self.assertEqual(database.create_collection.call_count, 5)
        for call in database.create_collection.call_args_list:
            self.assertEqual(call.kwargs["validationLevel"], "strict")
            self.assertEqual(call.kwargs["validationAction"], "error")
        calls = database.__getitem__.return_value.create_index.call_args_list
        unique = next(call for call in calls if call.kwargs["name"] == "public_delivery_request")
        self.assertEqual(
            unique.kwargs["partialFilterExpression"], {"request_key_hash": {"$type": "string"}}
        )
        self.assertTrue(unique.kwargs["unique"])
