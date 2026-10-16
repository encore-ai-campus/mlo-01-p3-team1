import io
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import UUID

from django.test import SimpleTestCase
from PIL import Image

from domains.ads.errors import (
    DatabaseUnavailable,
    IdempotencyConflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from domains.ads.service import AdsService, ad_status, canonical_hash, serialize_ad
from domains.ads.validation import (
    AD_FIELDS,
    BUDGET_FIELDS,
    MAX_IMAGE_BYTES,
    validate_ad_input,
    validate_image,
)


class MemoryRepository:
    """업무 로직 검증용 원자적 fixture이며 MongoDB 연결 검증은 아닙니다."""

    def __init__(self):
        self.ads = {}
        self.assets = {}
        self.mutations = {}
        self.fail_audit = False
        self.fail_replace = False

    def run(self, callback):
        before = deepcopy((self.ads, self.assets, self.mutations))
        try:
            return callback(self)
        except Exception:
            self.ads, self.assets, self.mutations = before
            raise

    def get_mutation(self, source, actor, operation, scope, key_hash):
        for record in self.mutations.values():
            if (
                record["identity_source"],
                record["actor_account_id"],
                record["operation"],
                record["resource_scope"],
                record["idempotency_key_hash"],
            ) == (source, actor, operation, scope, key_hash):
                return deepcopy(record)
        return None

    def get_asset(self, asset_id):
        return deepcopy(self.assets.get(asset_id))

    def get_ad(self, ad_id):
        return deepcopy(self.ads.get(ad_id))

    def insert_asset(self, document):
        self.assets[document["_id"]] = deepcopy(document)

    def insert_ad(self, document):
        self.ads[document["_id"]] = deepcopy(document)

    def insert_mutation(self, document):
        if self.fail_audit:
            raise DatabaseUnavailable("감사 기록 저장 실패")
        self.mutations[document["_id"]] = deepcopy(document)

    def replace_ad(self, ad_id, expected_version, document):
        if self.fail_replace or self.ads[ad_id]["version"] != expected_version:
            return False
        self.ads[ad_id] = deepcopy(document)
        return True


def image_bytes(image_format="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format=image_format)
    return output.getvalue()


class AdsDomainTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 1, tzinfo=UTC)
        identifiers = count(1)
        self.repository = MemoryRepository()
        self.service = AdsService(
            self.repository,
            clock=lambda: self.now,
            id_factory=lambda: f"id-{next(identifiers)}",
            is_test=True,
        )
        self.actor = {"identity_source": "common-auth", "account_id": "external-admin"}
        self.context = {"actor": self.actor, "request_id": "request-first"}
        asset = self.service.upload_asset(
            image_bytes(), idempotency_key="asset-first", **self.context
        )
        self.asset_id = asset.body["asset_id"]
        self.data = {
            "title": "카페 광고",
            "asset_id": self.asset_id,
            "link_url": "https://example.com/advertisement",
            "placement": "top",
            "starts_at": self.now,
            "ends_at": self.now + timedelta(hours=1),
            "priority": 1,
        }

    def create(self):
        return self.service.create_ad(self.data, idempotency_key="create-first", **self.context)

    def test_status_inclusive_start_exclusive_end_and_pause(self):
        ad = {"paused": False, "starts_at": self.now, "ends_at": self.now + timedelta(hours=1)}
        self.assertEqual(ad_status(ad, self.now - timedelta(milliseconds=1)), "RESERVED")
        self.assertEqual(ad_status(ad, self.now), "ACTIVE")
        self.assertEqual(ad_status(ad, ad["ends_at"]), "ENDED")
        ad["paused"] = True
        self.assertEqual(ad_status(ad, self.now), "STOPPED")

    def test_create_replay_preserves_original_status_and_does_not_duplicate(self):
        original = self.create()
        self.now += timedelta(hours=2)
        replay = self.create()
        self.assertEqual(replay, original)
        self.assertEqual(replay.body["status"], "ACTIVE")
        self.assertEqual(len(self.repository.ads), 1)
        self.assertEqual(len(self.repository.mutations), 2)

    def test_idempotency_conflict_changes_nothing(self):
        self.create()
        changed = {**self.data, "priority": 2}
        with self.assertRaises(IdempotencyConflict):
            self.service.create_ad(changed, idempotency_key="create-first", **self.context)
        self.assertEqual(len(self.repository.ads), 1)
        self.assertEqual(len(self.repository.mutations), 2)

    def test_update_replay_precedes_version_check_and_snapshot_is_immutable(self):
        created = self.create()
        ad_id = created.body["ad_id"]
        edited = {**self.data, "title": "새 광고", "version": 1}
        original = self.service.update_ad(ad_id, edited, idempotency_key="edit", **self.context)
        replay = self.service.update_ad(ad_id, edited, idempotency_key="edit", **self.context)
        self.assertEqual(original, replay)
        record = next(
            item for item in self.repository.mutations.values() if item["operation"] == "UPDATE"
        )
        self.assertEqual(record["before_snapshot"]["title"], "카페 광고")
        self.assertEqual(record["after_snapshot"]["title"], "새 광고")
        original.body["title"] = "외부 변이"
        self.assertEqual(record["response_snapshot"]["body"]["title"], "새 광고")
        with self.assertRaises(VersionConflict):
            self.service.update_ad(ad_id, edited, idempotency_key="another", **self.context)

    def test_noop_does_not_increment_version_or_updated_at(self):
        created = self.create()
        self.now += timedelta(minutes=2)
        result = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "version": 1},
            idempotency_key="noop",
            **self.context,
        )
        self.assertFalse(result.body["changed"])
        self.assertEqual(result.body["version"], 1)
        self.assertEqual(result.body["updated_at"], created.body["updated_at"])

    def test_stop_and_put_preserve_paused_and_original_asset(self):
        created = self.create()
        ad_id = created.body["ad_id"]
        self.now += timedelta(minutes=1)
        stopped = self.service.stop_ad(
            ad_id, {"version": 1}, idempotency_key="stop", **self.context
        )
        result = self.service.update_ad(
            ad_id,
            {**self.data, "title": "중단 중 수정", "version": 2},
            idempotency_key="stopped-edit",
            **self.context,
        )
        self.assertEqual(result.body["status"], "STOPPED")
        self.assertEqual(result.body["stopped_at"], stopped.body["stopped_at"])
        self.assertEqual(bytes(self.repository.assets[self.asset_id]["image_bytes"]), image_bytes())

    def test_upload_replay_uses_bytes_hash_and_actor_namespace(self):
        first = self.service.upload_asset(
            image_bytes(), idempotency_key="asset-replay", **self.context
        )
        replay = self.service.upload_asset(
            image_bytes(), idempotency_key="asset-replay", **self.context
        )
        self.assertEqual(first, replay)
        with self.assertRaises(IdempotencyConflict):
            self.service.upload_asset(
                image_bytes("JPEG"), idempotency_key="asset-replay", **self.context
            )
        another = self.service.upload_asset(
            image_bytes(),
            actor={**self.actor, "account_id": "another-admin"},
            idempotency_key="asset-replay",
            request_id="another-request",
        )
        self.assertNotEqual(first.body["asset_id"], another.body["asset_id"])

    def test_second_stop_is_noop_and_replay_uses_first_response(self):
        created = self.create()
        ad_id = created.body["ad_id"]
        first = self.service.stop_ad(ad_id, {"version": 1}, idempotency_key="stop", **self.context)
        self.now += timedelta(minutes=3)
        again = self.service.stop_ad(
            ad_id, {"version": 2}, idempotency_key="stop-again", **self.context
        )
        replay = self.service.stop_ad(ad_id, {"version": 1}, idempotency_key="stop", **self.context)
        self.assertEqual(first, replay)
        self.assertFalse(again.body["changed"])
        self.assertEqual(again.body["version"], 2)
        self.assertEqual(again.body["stopped_at"], first.body["stopped_at"])

    def test_audit_failure_rolls_back_ad_and_asset(self):
        self.repository.fail_audit = True
        with self.assertRaises(DatabaseUnavailable):
            self.create()
        self.assertFalse(self.repository.ads)
        self.assertEqual(len(self.repository.mutations), 1)
        with self.assertRaises(DatabaseUnavailable):
            self.service.upload_asset(
                image_bytes("JPEG"), idempotency_key="asset-two", **self.context
            )
        self.assertEqual(len(self.repository.assets), 1)

    def test_conditional_write_failure_rolls_back_and_records_no_success(self):
        created = self.create()
        self.repository.fail_replace = True
        with self.assertRaises(VersionConflict):
            self.service.stop_ad(
                created.body["ad_id"], {"version": 1}, idempotency_key="stop", **self.context
            )
        self.assertFalse(self.repository.ads[created.body["ad_id"]]["paused"])
        self.assertEqual(len(self.repository.mutations), 2)

    def test_unknown_tag_boolean_priority_and_invalid_duration_rejected(self):
        for invalid in (
            {**self.data, "target_tag_codes": ["CAFE"]},
            {**self.data, "priority": True},
            {**self.data, "ends_at": self.now},
            {**self.data, "placement": []},
            {**self.data, "link_url": "http://example.com"},
            {**self.data, "link_url": "https://user:secret@example.com"},
            {**self.data, "starts_at": "2026-10-15T01:00:00"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.service.create_ad(invalid, idempotency_key="invalid", **self.context)
        self.assertFalse(self.repository.ads)

    def test_normalized_utc_inputs_hash_the_same(self):
        first = validate_ad_input({**self.data, "starts_at": "2026-10-15T10:00:00+09:00"})
        second = validate_ad_input({**self.data, "starts_at": "2026-10-15T01:00:00.000Z"})
        self.assertEqual(canonical_hash(first), canonical_hash(second))

    def test_missing_asset_and_tampered_sha_are_not_accepted(self):
        with self.assertRaises(NotFound):
            self.service.create_ad(
                {**self.data, "asset_id": "missing"}, idempotency_key="missing", **self.context
            )
        self.repository.assets[self.asset_id]["sha256"] = "0" * 64
        with self.assertRaises(DatabaseUnavailable):
            self.create()
        self.assertFalse(self.repository.ads)

    def test_image_limit_decode_and_animation_validation(self):
        padded = image_bytes() + b"\0" * (MAX_IMAGE_BYTES - len(image_bytes()))
        self.assertEqual(validate_image(padded)["byte_size"], MAX_IMAGE_BYTES)
        with self.assertRaises(ValidationError):
            validate_image(padded + b"\0")
        with self.assertRaises(ValidationError):
            validate_image(b"not-an-image.png")
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(
            output,
            format="PNG",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
        )
        with self.assertRaises(ValidationError):
            validate_image(output.getvalue())

    def test_log_payload_is_locally_stored_immutable_and_has_no_image_or_auth_secret(self):
        self.create()
        for record in self.repository.mutations.values():
            relay = record["log_record"]
            self.assertEqual(relay["log_schema_version"], "ads-mongo-log-20261015.1")
            self.assertEqual(relay["payload_hash"], canonical_hash(relay["payload"]))
            self.assertEqual(relay["payload"]["request_id"], "request-first")
            self.assertIsNone(record["retention_due_at"])
            self.assertNotIn("image_bytes", str(relay["payload"]))
            self.assertNotIn("password", str(relay["payload"]))
            self.assertEqual(record["actor_account_id"], "external-admin")

    def test_budget_fields_are_optional_pair_and_do_not_expand_required_edit_fields(self):
        self.assertEqual(len(AD_FIELDS), 7)
        self.assertEqual(BUDGET_FIELDS, {"daily_budget_tokens", "total_budget_tokens"})
        self.assertEqual(set(validate_ad_input(self.data)), AD_FIELDS)
        valid = {**self.data, "daily_budget_tokens": 1, "total_budget_tokens": 2**63 - 1}
        original = deepcopy(valid)
        self.assertEqual(validate_ad_input(valid)["total_budget_tokens"], 2**63 - 1)
        self.assertEqual(valid, original)

    def test_budget_pair_missing_one_field_is_rejected_before_storage(self):
        for field in BUDGET_FIELDS:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.service.create_ad(
                    {**self.data, field: 100}, idempotency_key=f"partial-{field}", **self.context
                )
        self.assertFalse(self.repository.ads)
        self.assertEqual(len(self.repository.mutations), 1)

    def test_budgets_are_strict_positive_bson_int64_and_cannot_be_cleared_with_null(self):
        for field in BUDGET_FIELDS:
            for invalid in (True, False, 0, -1, 1.0, "100", None, 2**63):
                data = {
                    **self.data,
                    "daily_budget_tokens": 100,
                    "total_budget_tokens": 1000,
                    field: invalid,
                }
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValidationError):
                    validate_ad_input(data)

    def test_request_cannot_choose_budget_version(self):
        with self.assertRaises(ValidationError):
            validate_ad_input({**self.data, "budget_version": "client-controlled"})

    def test_unconfigured_create_stores_null_budgets_without_inventing_operating_values(self):
        result = self.create()
        ad = self.repository.ads[result.body["ad_id"]]
        for field in (*BUDGET_FIELDS, "budget_version"):
            self.assertIn(field, ad)
            self.assertIsNone(ad[field])
            self.assertIsNone(result.body[field])

    def test_budget_create_records_amounts_and_version_in_immutable_success_and_audit(self):
        result = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        ad = self.repository.ads[result.body["ad_id"]]
        self.assertEqual(ad["daily_budget_tokens"], 100)
        self.assertEqual(ad["total_budget_tokens"], 1000)
        self.assertIsInstance(ad["budget_version"], str)
        record = next(
            item for item in self.repository.mutations.values() if item["operation"] == "CREATE"
        )
        self.assertEqual(record["after_snapshot"]["budget_version"], ad["budget_version"])
        self.assertEqual(record["response_snapshot"]["body"]["daily_budget_tokens"], 100)
        self.assertEqual(
            record["log_record"]["payload"]["after_snapshot"]["total_budget_tokens"], 1000
        )
        self.assertEqual(
            record["log_record"]["payload_hash"], canonical_hash(record["log_record"]["payload"])
        )

    def test_production_id_factory_creates_uuid_budget_version(self):
        service = AdsService(self.repository, clock=lambda: self.now, is_test=True)
        result = service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="uuid-budget",
            **self.context,
        )
        self.assertEqual(str(UUID(result.body["budget_version"])), result.body["budget_version"])

    def test_edit_without_budget_fields_preserves_existing_budget_and_its_version(self):
        created = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        updated = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "title": "소재 변경", "version": 1},
            idempotency_key="creative-edit",
            **self.context,
        )
        for field in (*BUDGET_FIELDS, "budget_version"):
            self.assertEqual(updated.body[field], created.body[field])
        self.assertNotEqual(updated.body["creative_version"], created.body["creative_version"])

    def test_priority_or_period_edit_preserves_budget_version(self):
        created = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        updated = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "priority": 2, "ends_at": self.now + timedelta(hours=2), "version": 1},
            idempotency_key="settings-edit",
            **self.context,
        )
        self.assertEqual(updated.body["budget_version"], created.body["budget_version"])
        self.assertEqual(updated.body["creative_version"], created.body["creative_version"])

    def test_budget_only_edit_changes_version_and_audit_without_changing_creative(self):
        created = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        updated = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "daily_budget_tokens": 200, "total_budget_tokens": 2000, "version": 1},
            idempotency_key="budget-edit",
            **self.context,
        )
        self.assertTrue(updated.body["changed"])
        self.assertEqual(updated.body["version"], 2)
        self.assertNotEqual(updated.body["budget_version"], created.body["budget_version"])
        self.assertEqual(updated.body["creative_version"], created.body["creative_version"])
        record = next(
            item for item in self.repository.mutations.values() if item["operation"] == "UPDATE"
        )
        self.assertEqual(record["before_snapshot"]["daily_budget_tokens"], 100)
        self.assertEqual(record["after_snapshot"]["daily_budget_tokens"], 200)
        self.assertEqual(record["after_snapshot"]["budget_version"], updated.body["budget_version"])

    def test_unchanged_explicit_budget_is_noop_and_keeps_original_budget_version(self):
        values = {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000}
        created = self.service.create_ad(values, idempotency_key="with-budget", **self.context)
        self.now += timedelta(minutes=1)
        updated = self.service.update_ad(
            created.body["ad_id"],
            {**values, "version": 1},
            idempotency_key="same-budget",
            **self.context,
        )
        self.assertFalse(updated.body["changed"])
        for field in ("version", "budget_version", "updated_at"):
            self.assertEqual(updated.body[field], created.body[field])

    def test_legacy_ad_without_budget_fields_can_be_read_and_configured(self):
        created = self.create()
        ad = self.repository.ads[created.body["ad_id"]]
        for field in (*BUDGET_FIELDS, "budget_version"):
            ad.pop(field)
        legacy = serialize_ad(ad, self.now)
        self.assertIsNone(legacy["budget_version"])
        updated = self.service.update_ad(
            ad["_id"],
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000, "version": 1},
            idempotency_key="configure-legacy",
            **self.context,
        )
        self.assertEqual(updated.body["daily_budget_tokens"], 100)
        self.assertIsInstance(updated.body["budget_version"], str)

    def test_legacy_edit_with_omitted_budgets_does_not_backfill_a_budget(self):
        created = self.create()
        ad = self.repository.ads[created.body["ad_id"]]
        for field in (*BUDGET_FIELDS, "budget_version"):
            ad.pop(field)
        self.service.update_ad(
            ad["_id"],
            {**self.data, "title": "구문서 편집", "version": 1},
            idempotency_key="edit-legacy",
            **self.context,
        )
        for field in (*BUDGET_FIELDS, "budget_version"):
            self.assertNotIn(field, self.repository.ads[ad["_id"]])

    def test_budget_update_replay_retains_original_response_after_another_budget_edit(self):
        created = self.create()
        first_input = {
            **self.data,
            "daily_budget_tokens": 100,
            "total_budget_tokens": 1000,
            "version": 1,
        }
        first = self.service.update_ad(
            created.body["ad_id"], first_input, idempotency_key="budget-edit", **self.context
        )
        self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "daily_budget_tokens": 200, "total_budget_tokens": 2000, "version": 2},
            idempotency_key="later-budget",
            **self.context,
        )
        before = deepcopy((self.repository.ads, self.repository.mutations))
        replay = self.service.update_ad(
            created.body["ad_id"], first_input, idempotency_key="budget-edit", **self.context
        )
        self.assertEqual(replay, first)
        self.assertEqual((self.repository.ads, self.repository.mutations), before)

    def test_same_create_key_with_changed_budget_conflicts_without_new_ad(self):
        first = {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000}
        self.service.create_ad(first, idempotency_key="with-budget", **self.context)
        before = deepcopy((self.repository.ads, self.repository.mutations))
        with self.assertRaises(IdempotencyConflict):
            self.service.create_ad(
                {**first, "daily_budget_tokens": 101}, idempotency_key="with-budget", **self.context
            )
        self.assertEqual((self.repository.ads, self.repository.mutations), before)

    def test_budget_change_failure_rolls_back_amounts_version_and_audit(self):
        created = self.create()
        before = deepcopy((self.repository.ads, self.repository.mutations))
        self.repository.fail_audit = True
        with self.assertRaises(DatabaseUnavailable):
            self.service.update_ad(
                created.body["ad_id"],
                {
                    **self.data,
                    "daily_budget_tokens": 100,
                    "total_budget_tokens": 1000,
                    "version": 1,
                },
                idempotency_key="failing-budget",
                **self.context,
            )
        self.assertEqual((self.repository.ads, self.repository.mutations), before)

    def test_budget_changes_preserve_manual_pause_and_record_no_resume(self):
        created = self.create()
        stopped = self.service.stop_ad(
            created.body["ad_id"], {"version": 1}, idempotency_key="stop", **self.context
        )
        updated = self.service.update_ad(
            created.body["ad_id"],
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000, "version": 2},
            idempotency_key="budget-while-paused",
            **self.context,
        )
        self.assertEqual(updated.body["status"], "STOPPED")
        self.assertEqual(updated.body["stopped_at"], stopped.body["stopped_at"])

    def test_automatic_budget_end_uses_current_budget_version_and_effective_interval(self):
        ad = {
            "paused": False,
            "starts_at": self.now,
            "ends_at": self.now + timedelta(hours=1),
            "budget_version": "budget-current",
            "budget_blocked_version": "budget-current",
            "budget_blocked_at": self.now + timedelta(seconds=10),
            "budget_blocked_until": self.now + timedelta(minutes=30),
        }
        self.assertEqual(ad_status(ad, self.now), "ACTIVE")
        self.assertEqual(ad_status(ad, ad["budget_blocked_at"]), "ENDED")
        self.assertEqual(
            ad_status(ad, ad["budget_blocked_until"] - timedelta(milliseconds=1)), "ENDED"
        )
        self.assertEqual(ad_status(ad, ad["budget_blocked_until"]), "ACTIVE")
        self.assertEqual(
            ad_status({**ad, "budget_blocked_version": "old"}, ad["budget_blocked_at"]), "ACTIVE"
        )

    def test_total_budget_end_has_no_automatic_time_release_and_pause_has_priority(self):
        ad = {
            "paused": False,
            "starts_at": self.now,
            "ends_at": self.now + timedelta(days=2),
            "budget_version": "budget-current",
            "budget_blocked_version": "budget-current",
            "budget_blocked_at": self.now,
            "budget_blocked_until": None,
        }
        self.assertEqual(ad_status(ad, self.now + timedelta(days=1)), "ENDED")
        self.assertEqual(ad_status({**ad, "paused": True}, self.now), "STOPPED")

    def test_management_response_distinguishes_budget_end_period_end_and_manual_stop(self):
        created = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        ad = self.repository.ads[created.body["ad_id"]]
        ad.update(
            {
                "budget_blocked_at": self.now,
                "budget_blocked_until": None,
                "budget_blocked_version": ad["budget_version"],
                "budget_blocked_scope": "TOTAL",
            }
        )
        response = serialize_ad(ad, self.now)
        self.assertEqual(response["status"], "ENDED")
        self.assertEqual(response["end_reason"], "BUDGET_EXHAUSTED")
        self.assertFalse(any(field.startswith("budget_blocked_") for field in response))
        self.assertEqual(serialize_ad(ad, ad["ends_at"])["end_reason"], "PERIOD_ENDED")
        ad["paused"] = True
        stopped = serialize_ad(ad, self.now)
        self.assertEqual(stopped["status"], "STOPPED")
        self.assertIsNone(stopped["end_reason"])

    def test_technical_budget_end_is_preserved_by_edit_and_only_new_budget_version_rechecks_it(
        self,
    ):
        created = self.service.create_ad(
            {**self.data, "daily_budget_tokens": 100, "total_budget_tokens": 1000},
            idempotency_key="with-budget",
            **self.context,
        )
        ad = self.repository.ads[created.body["ad_id"]]
        automatic = {
            "budget_blocked_at": self.now,
            "budget_blocked_until": None,
            "budget_blocked_version": ad["budget_version"],
            "budget_blocked_scope": "TOTAL",
        }
        ad.update(automatic)
        edited = self.service.update_ad(
            ad["_id"],
            {**self.data, "priority": 2, "version": 1},
            idempotency_key="edit-blocked",
            **self.context,
        )
        self.assertEqual(edited.body["end_reason"], "BUDGET_EXHAUSTED")
        for field, value in automatic.items():
            self.assertEqual(self.repository.ads[ad["_id"]][field], value)
        changed = self.service.update_ad(
            ad["_id"],
            {**self.data, "daily_budget_tokens": 200, "total_budget_tokens": 2000, "version": 2},
            idempotency_key="change-blocked-budget",
            **self.context,
        )
        self.assertIsNone(changed.body["end_reason"])
        self.assertNotEqual(changed.body["budget_version"], automatic["budget_blocked_version"])
        for field, value in automatic.items():
            self.assertEqual(self.repository.ads[ad["_id"]][field], value)

    def test_automatic_budget_state_and_end_reason_are_server_fields_only(self):
        for field, value in (
            ("budget_blocked_at", self.now),
            ("budget_blocked_until", None),
            ("budget_blocked_version", "forged"),
            ("budget_blocked_scope", "TOTAL"),
            ("end_reason", "PERIOD_ENDED"),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_ad_input({**self.data, field: value})
