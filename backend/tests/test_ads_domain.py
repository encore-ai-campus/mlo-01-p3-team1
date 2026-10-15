import io
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import count

from django.test import SimpleTestCase
from PIL import Image

from domains.ads.errors import (
    DatabaseUnavailable,
    IdempotencyConflict,
    NotFound,
    ValidationError,
    VersionConflict,
)
from domains.ads.service import AdsService, ad_status, canonical_hash
from domains.ads.validation import MAX_IMAGE_BYTES, validate_ad_input, validate_image


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

    def test_log_payload_is_pending_immutable_and_has_no_image_or_auth_secret(self):
        self.create()
        for record in self.repository.mutations.values():
            relay = record["log_relay"]
            self.assertEqual(relay["status"], "PENDING")
            self.assertEqual(relay["payload_hash"], canonical_hash(relay["payload"]))
            self.assertEqual(relay["payload"]["request_id"], "request-first")
            self.assertIsNone(record["retention_due_at"])
            self.assertNotIn("image_bytes", str(relay["payload"]))
            self.assertNotIn("password", str(relay["payload"]))
            self.assertEqual(record["actor_account_id"], "external-admin")
