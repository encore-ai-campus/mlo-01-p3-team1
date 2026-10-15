import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from bson import Binary

from .errors import DatabaseUnavailable, IdempotencyConflict, NotFound, VersionConflict
from .validation import (
    AD_FIELDS,
    BUDGET_FIELDS,
    utc_datetime,
    utc_string,
    validate_ad_input,
    validate_bson_size,
    validate_image,
    validate_stop_input,
)

SCHEMA_VERSION = "phase3-ads-data-20261014.3"
CREATIVE_FIELDS = frozenset({"title", "asset_id", "link_url"})
AD_RESPONSE_FIELDS = (
    "title",
    "asset_id",
    "creative_version",
    "link_url",
    "placement",
    "starts_at",
    "ends_at",
    "priority",
    "version",
    "paused",
    "stopped_at",
    "created_at",
    "updated_at",
)
ASSET_METADATA_FIELDS = ("mime_type", "byte_size", "width", "height", "sha256")


@dataclass(frozen=True)
class ServiceResult:
    http_status: int
    body: dict


def _json_value(value):
    if isinstance(value, datetime):
        return utc_string(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def canonical_hash(value):
    encoded = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ad_status(ad, now):
    if ad["paused"]:
        return "STOPPED"
    now = utc_datetime(now)
    if now >= utc_datetime(ad["ends_at"]):
        return "ENDED"
    blocked_at = ad.get("budget_blocked_at")
    blocked_until = ad.get("budget_blocked_until")
    if (
        ad.get("budget_version") is not None
        and ad.get("budget_version") == ad.get("budget_blocked_version")
        and blocked_at is not None
        and utc_datetime(blocked_at) <= now
        and (blocked_until is None or now < utc_datetime(blocked_until))
    ):
        return "ENDED"
    if now < utc_datetime(ad["starts_at"]):
        return "RESERVED"
    return "ACTIVE"


def serialize_ad(ad, now):
    values = {field: ad[field] for field in AD_RESPONSE_FIELDS}
    budgets = {field: ad.get(field) for field in (*sorted(BUDGET_FIELDS), "budget_version")}
    status = ad_status(ad, now)
    end_reason = None
    if status == "ENDED":
        end_reason = (
            "PERIOD_ENDED"
            if utc_datetime(now) >= utc_datetime(ad["ends_at"])
            else "BUDGET_EXHAUSTED"
        )
    return _json_value(
        {
            "ad_id": ad["_id"],
            **values,
            **budgets,
            "status": status,
            "end_reason": end_reason,
        }
    )


def serialize_asset(asset):
    return {"asset_id": asset["_id"], **{field: asset[field] for field in ASSET_METADATA_FIELDS}}


class AdsService:
    """첫 광고 관리 단계만 수행합니다. 인증은 공통 서버 경계에서 먼저 검사합니다."""

    def __init__(self, repository, clock=None, id_factory=None, is_test=False):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda: str(uuid4()))
        self.is_test = is_test

    def _context(self, actor, idempotency_key, request_id, operation, scope, data):
        from .errors import ValidationError

        # caller가 검증한 외부 참조만 사용하고 계정/세션 원본은 만들지 않습니다.
        if not isinstance(actor, dict) or any(
            not isinstance(actor.get(field), str) or not actor[field].strip()
            for field in ("identity_source", "account_id")
        ):
            raise ValidationError("서버에서 검증한 관리자 참조가 필요합니다.")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValidationError(fields={"Idempotency-Key": "필수 헤더입니다."})
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValidationError("서버 request_id가 필요합니다.")
        return {
            "actor": {
                "identity_source": actor["identity_source"],
                "account_id": actor["account_id"],
            },
            "key_hash": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
            "request_hash": canonical_hash(data),
            "request_id": request_id,
            "operation": operation,
            "scope": scope,
            "now": utc_datetime(self.clock()),
            "log_id": self.id_factory(),
        }

    def _replay(self, repository, context):
        actor = context["actor"]
        record = repository.get_mutation(
            actor["identity_source"],
            actor["account_id"],
            context["operation"],
            context["scope"],
            context["key_hash"],
        )
        if record is None:
            return None
        if record["request_hash"] != context["request_hash"]:
            raise IdempotencyConflict()
        snapshot = deepcopy(record["response_snapshot"])
        return ServiceResult(snapshot["http_status"], snapshot["body"])

    def _mutation_context(self, context):
        """재시도마다 실제 적용 구간의 시각을 정하고 요청 대기 시각을 소급하지 않습니다."""
        return {**context, "now": utc_datetime(self.clock())}

    def _asset(self, repository, asset_id):
        asset = repository.get_asset(asset_id)
        if asset is None or asset["is_test"] != self.is_test:
            raise NotFound("광고 이미지를 찾을 수 없습니다.")
        from .errors import ValidationError

        try:
            metadata = validate_image(bytes(asset["image_bytes"]))
            if any(asset[field] != metadata[field] for field in ASSET_METADATA_FIELDS):
                raise DatabaseUnavailable("저장된 광고 이미지의 무결성을 확인할 수 없습니다.")
        except (ValidationError, KeyError, TypeError) as exc:
            raise DatabaseUnavailable("저장된 광고 이미지의 무결성을 확인할 수 없습니다.") from exc
        return asset

    def _ad(self, repository, ad_id, version):
        ad = repository.get_ad(ad_id)
        if ad is None or ad["is_test"] != self.is_test:
            raise NotFound()
        if ad["version"] != version:
            raise VersionConflict(fields={"current_version": ad["version"]})
        return ad

    def _record(self, context, *, asset_id, ad_id, before, after, changed, result):
        actor = context["actor"]
        now = context["now"]
        before_snapshot = deepcopy(before)
        after_snapshot = deepcopy(after)
        payload = _json_value(
            {
                "log_event_id": f"ads-management:{context['log_id']}",
                "source_domain": "ADS",
                "source_event_id": context["log_id"],
                "schema_version": SCHEMA_VERSION,
                "operation": context["operation"],
                "identity_source": actor["identity_source"],
                "actor_account_id": actor["account_id"],
                "ad_id": ad_id,
                "asset_id": asset_id,
                "changed": changed,
                "version_before": before.get("version") if before else None,
                "version_after": after.get("version"),
                "before_snapshot": before_snapshot,
                "after_snapshot": after_snapshot,
                "occurred_at": now,
                "processed_at": now,
                "request_id": context["request_id"],
                "result": "CHANGED" if changed else "UNCHANGED",
                "is_test": self.is_test,
            }
        )
        record = {
            "_id": context["log_id"],
            "schema_version": SCHEMA_VERSION,
            "is_test": self.is_test,
            "created_at": now,
            "operation": context["operation"],
            "ad_id": ad_id,
            "asset_id": asset_id,
            "identity_source": actor["identity_source"],
            "actor_account_id": actor["account_id"],
            "resource_scope": context["scope"],
            "idempotency_key_hash": context["key_hash"],
            "request_hash": context["request_hash"],
            "changed": changed,
            "version_before": before.get("version") if before else None,
            "version_after": after.get("version"),
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "reason": None,
            "response_snapshot": {"http_status": result.http_status, "body": deepcopy(result.body)},
            "completed_at": now,
            "occurred_at": now,
            # 감사/멱등 양쪽 기한과 pending 보호를 해제하는 정책은 아직 미정입니다.
            "retention_due_at": None,
            "log_relay": {
                "log_event_id": payload["log_event_id"],
                "payload": payload,
                "payload_hash": canonical_hash(payload),
                "status": "PENDING",
                "attempt_count": 0,
                "next_retry_at": None,
                "last_error": None,
                "sent_at": None,
            },
        }
        validate_bson_size(record)
        return record

    def upload_asset(self, image_bytes, *, actor, idempotency_key, request_id):
        metadata = validate_image(image_bytes)
        context = self._context(
            actor, idempotency_key, request_id, "UPLOAD_ASSET", "assets:upload", metadata
        )
        asset = {
            "_id": self.id_factory(),
            "schema_version": SCHEMA_VERSION,
            "is_test": self.is_test,
            "created_at": context["now"],
            "image_bytes": Binary(image_bytes),
            **metadata,
            "uploaded_by_account_id": context["actor"]["account_id"],
            "identity_source": context["actor"]["identity_source"],
        }
        validate_bson_size(asset)
        result = ServiceResult(201, {**serialize_asset(asset), "changed": True})

        def commit(repository):
            replay = self._replay(repository, context)
            if replay is not None:
                return replay
            write_context = self._mutation_context(context)
            stored_asset = {**deepcopy(asset), "created_at": write_context["now"]}
            record = self._record(
                write_context,
                asset_id=asset["_id"],
                ad_id=None,
                before=None,
                after=serialize_asset(asset),
                changed=True,
                result=result,
            )
            repository.insert_asset(stored_asset)
            repository.insert_mutation(record)
            return ServiceResult(result.http_status, deepcopy(result.body))

        return self.repository.run(commit)

    def create_ad(self, data, *, actor, idempotency_key, request_id):
        values = validate_ad_input(data)
        context = self._context(actor, idempotency_key, request_id, "CREATE", "ads:create", values)
        ad = {
            "_id": self.id_factory(),
            "schema_version": SCHEMA_VERSION,
            "is_test": self.is_test,
            "created_at": context["now"],
            **values,
            **{field: values.get(field) for field in BUDGET_FIELDS},
            "budget_version": self.id_factory() if BUDGET_FIELDS <= values.keys() else None,
            "creative_version": self.id_factory(),
            "version": 1,
            "paused": False,
            "stopped_at": None,
            "created_by_account_id": context["actor"]["account_id"],
            "updated_by_account_id": context["actor"]["account_id"],
            "identity_source": context["actor"]["identity_source"],
            "updated_at": context["now"],
        }
        validate_bson_size(ad)

        def commit(repository):
            replay = self._replay(repository, context)
            if replay is not None:
                return replay
            self._asset(repository, values["asset_id"])
            write_context = self._mutation_context(context)
            stored_ad = {
                **deepcopy(ad),
                "created_at": write_context["now"],
                "updated_at": write_context["now"],
            }
            result = ServiceResult(
                201, {**serialize_ad(stored_ad, write_context["now"]), "changed": True}
            )
            record = self._record(
                write_context,
                asset_id=ad["asset_id"],
                ad_id=ad["_id"],
                before=None,
                after=serialize_ad(stored_ad, write_context["now"]),
                changed=True,
                result=result,
            )
            repository.insert_ad(stored_ad)
            repository.insert_mutation(record)
            return ServiceResult(result.http_status, deepcopy(result.body))

        return self.repository.run(commit)

    def update_ad(self, ad_id, data, *, actor, idempotency_key, request_id):
        values = validate_ad_input(data, with_version=True)
        context = self._context(actor, idempotency_key, request_id, "UPDATE", ad_id, values)
        creative_version = self.id_factory()
        budget_version = self.id_factory() if BUDGET_FIELDS <= values.keys() else None

        def commit(repository):
            replay = self._replay(repository, context)
            if replay is not None:
                return replay
            current = self._ad(repository, ad_id, values["version"])
            self._asset(repository, values["asset_id"])
            if not repository.replace_ad(ad_id, values["version"], deepcopy(current)):
                raise VersionConflict()
            write_context = self._mutation_context(context)
            budget_changed = BUDGET_FIELDS <= values.keys() and any(
                current.get(field) != values[field] for field in BUDGET_FIELDS
            )
            changed = any(current[field] != values[field] for field in AD_FIELDS) or budget_changed
            after = deepcopy(current)
            if changed:
                after.update({field: values[field] for field in AD_FIELDS})
                after["version"] += 1
                after["updated_at"] = write_context["now"]
                after["updated_by_account_id"] = context["actor"]["account_id"]
                if any(current[field] != values[field] for field in CREATIVE_FIELDS):
                    after["creative_version"] = creative_version
                if budget_changed:
                    after.update({field: values[field] for field in BUDGET_FIELDS})
                    after["budget_version"] = budget_version
            validate_bson_size(after)
            result = ServiceResult(
                200,
                {
                    **serialize_ad(after, write_context["now"]),
                    "changed": changed,
                },
            )
            record = self._record(
                write_context,
                asset_id=after["asset_id"],
                ad_id=ad_id,
                before=serialize_ad(current, write_context["now"]),
                after=serialize_ad(after, write_context["now"]),
                changed=changed,
                result=result,
            )
            if changed and not repository.replace_ad(ad_id, values["version"], deepcopy(after)):
                raise VersionConflict()
            repository.insert_mutation(record)
            return result

        return self.repository.run(commit)

    def stop_ad(self, ad_id, data, *, actor, idempotency_key, request_id):
        values = validate_stop_input(data)
        context = self._context(actor, idempotency_key, request_id, "STOP", ad_id, values)

        def commit(repository):
            replay = self._replay(repository, context)
            if replay is not None:
                return replay
            current = self._ad(repository, ad_id, values["version"])
            if not repository.replace_ad(ad_id, values["version"], deepcopy(current)):
                raise VersionConflict()
            write_context = self._mutation_context(context)
            after = deepcopy(current)
            changed = not current["paused"]
            if changed:
                after.update(
                    {
                        "paused": True,
                        "stopped_at": write_context["now"],
                        "version": current["version"] + 1,
                        "updated_at": write_context["now"],
                        "updated_by_account_id": context["actor"]["account_id"],
                    }
                )
            result = ServiceResult(
                200,
                {
                    **serialize_ad(after, write_context["now"]),
                    "changed": changed,
                },
            )
            record = self._record(
                write_context,
                asset_id=after["asset_id"],
                ad_id=ad_id,
                before=serialize_ad(current, write_context["now"]),
                after=serialize_ad(after, write_context["now"]),
                changed=changed,
                result=result,
            )
            if changed and not repository.replace_ad(ad_id, values["version"], deepcopy(after)):
                raise VersionConflict()
            repository.insert_mutation(record)
            return result

        return self.repository.run(commit)
