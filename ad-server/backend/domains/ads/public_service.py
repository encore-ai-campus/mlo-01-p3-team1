"""공개 광고 배달·측정의 업무 원자 저장. 화면과 공유 사용자 원본은 관리하지 않습니다."""

import hashlib
import hmac
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from pymongo.errors import PyMongoError

from .budget_service import budget_occurrence_eligible
from .delivery_policy import delivery_deadlines
from .errors import DomainError, IdempotencyConflict, NotFound, ValidationError
from .measurement import ADS_POLICY_VERSION, DeliveryContext, judge_event, validate_event_input
from .public_policy import AdsPublicPolicy
from .selection import AdCandidate, RotationCursor, display_valid_until, select_ad
from .service import ASSET_METADATA_FIELDS, canonical_hash
from .validation import utc_datetime, utc_string, validate_bson_size, validate_image

PUBLIC_SCHEMA_VERSION = "phase3-ads-public-20261015.2"
SNAPSHOT_FIELDS = (
    "title",
    "asset_id",
    "link_url",
    "placement",
    "starts_at",
    "ends_at",
    "priority",
    "paused",
    "version",
    "creative_version",
    "stopped_at",
)


def _reference(value, name, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(fields={name: "비어 있지 않은 문자열이 필요합니다."})


def _context(owner_guest_id, measurement_available, request_id):
    _reference(owner_guest_id, "owner_guest_id", nullable=True)
    _reference(request_id, "request_id")
    if type(measurement_available) is not bool or (
        measurement_available and owner_guest_id is None
    ):
        raise ValidationError("공유 서비스가 검증한 guest 측정 문맥이 필요합니다.")


def _snapshot(ad):
    result = {name: deepcopy(ad[name]) for name in SNAPSHOT_FIELDS}
    result["ad_id"] = ad.get("_id", ad.get("ad_id"))
    for name in ("starts_at", "ends_at", "stopped_at"):
        if result[name] is not None:
            result[name] = utc_datetime(result[name])
    return result


def _active(ad, placement, now):
    return (
        ad["placement"] == placement
        and ad["paused"] is False
        and utc_datetime(ad["starts_at"]) <= now < utc_datetime(ad["ends_at"])
    )


class AdsPublicService:
    def __init__(
        self,
        repository,
        *,
        policy,
        signing_key,
        public_base_url,
        is_test,
        clock=None,
        id_factory=None,
    ):
        if not isinstance(policy, AdsPublicPolicy):
            raise DomainError("ADS_POLICY_UNAVAILABLE", "광고 운영 정책 연결이 필요합니다.", 503)
        if not isinstance(signing_key, str) or not signing_key.strip():
            raise DomainError("ADS_POLICY_UNAVAILABLE", "광고 배달 서명 설정이 필요합니다.", 503)
        try:
            url = urlsplit(public_base_url)
            if (
                not isinstance(public_base_url, str)
                or url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or "\\" in public_base_url
                or any(c.isspace() or ord(c) < 32 for c in public_base_url)
            ):
                raise ValueError
            url.port
        except (TypeError, ValueError, AttributeError):
            raise DomainError(
                "ADS_POLICY_UNAVAILABLE", "광고 공개 HTTPS 주소 설정이 필요합니다.", 503
            ) from None
        if type(is_test) is not bool or repository.is_test != is_test:
            raise ValidationError("광고 저장소와 서버 환경이 일치해야 합니다.")
        self.repository = repository
        self.policy = policy
        self.signing_key = signing_key.encode("utf-8")
        self.public_base_url = public_base_url.rstrip("/")
        self.is_test = is_test
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda: str(uuid4()))

    def _now(self):
        return utc_datetime(self.clock())

    def _policy(self, callback, *args):
        try:
            value = callback(*args)
        except (PyMongoError, DomainError):
            raise
        except Exception:
            raise DomainError(
                "ADS_POLICY_UNAVAILABLE", "광고 운영 자격을 확인할 수 없습니다.", 503
            ) from None
        if type(value) is not bool:
            raise DomainError(
                "ADS_POLICY_UNAVAILABLE", "명시적인 광고 자격 판정이 필요합니다.", 503
            )
        return value

    def _asset(self, repository, asset_id):
        asset = repository.get_asset(asset_id)
        if asset is None:
            return None
        try:
            metadata = validate_image(bytes(asset["image_bytes"]))
            if asset["is_test"] != self.is_test or any(
                metadata[name] != asset[name] for name in ASSET_METADATA_FIELDS
            ):
                return None
        except (ValidationError, KeyError, TypeError):
            return None
        return asset

    def _token(self, delivery):
        signed = {
            name: delivery[name]
            for name in (
                "_id",
                "owner_guest_id",
                "placement",
                "issued_at",
                "event_expires_at",
                "is_test",
            )
        }
        if "display_expires_at" in delivery:
            signed["display_expires_at"] = delivery["display_expires_at"]
        if "budget_policy_version" in delivery:
            signed["budget_policy_version"] = delivery["budget_policy_version"]
        payload = canonical_hash(signed)
        return hmac.new(self.signing_key, payload.encode("ascii"), hashlib.sha256).hexdigest()

    def _verify_delivery(self, repository, delivery_id, token):
        _reference(delivery_id, "delivery_id")
        delivery = repository.get_delivery(delivery_id)
        if (
            delivery is None
            or not isinstance(token, str)
            or not token.isascii()
            or not hmac.compare_digest(self._token(delivery), token)
            or not hmac.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), delivery["token_hash"]
            )
        ):
            raise NotFound("광고 배달 자료를 찾을 수 없습니다.")
        return delivery

    def _owner(self, delivery, owner_guest_id):
        # 쿠키 불가 상태의 proof는 공개 표시만 허용합니다. 운영 측정은 아래에서 제외합니다.
        if (
            owner_guest_id is not None
            and delivery["owner_guest_id"] is not None
            and owner_guest_id != delivery["owner_guest_id"]
        ):
            raise NotFound("광고 배달 자료를 찾을 수 없습니다.")

    def _empty(self, now, measurement_available):
        return {
            "ad": None,
            "evaluated_at": utc_string(now),
            "valid_until": None,
            "measurement_available": measurement_available,
        }

    def _response(self, delivery, now, measurement_available, *, ends_at=None):
        snapshot = delivery["ad_snapshot"]
        until = display_valid_until(
            now,
            min(utc_datetime(snapshot["ends_at"]), utc_datetime(ends_at))
            if ends_at is not None
            else snapshot["ends_at"],
            event_expires_at=delivery.get("display_expires_at", delivery["event_expires_at"]),
        )
        if until is None:
            return self._empty(now, measurement_available)
        token = self._token(delivery)
        return {
            "ad": {
                "ad_id": delivery["ad_id"],
                "creative_version": delivery["creative_version"],
                "placement": delivery["placement"],
                "title": snapshot["title"],
                "image_url": (
                    f"{self.public_base_url}/api/ad-deliveries/{delivery['_id']}"
                    f"/image?delivery_token={token}"
                ),
                "link_url": snapshot["link_url"],
                "delivery_id": delivery["_id"],
                "delivery_token": token,
            },
            "evaluated_at": utc_string(now),
            "valid_until": utc_string(until),
            "measurement_available": measurement_available,
        }

    def _open_ad(self, repository, delivery, now):
        if now >= min(
            utc_datetime(delivery.get("display_expires_at", delivery["event_expires_at"])),
            utc_datetime(delivery["ad_snapshot"]["ends_at"]),
        ):
            return None
        ad = repository.get_ad(delivery["ad_id"])
        if ad is None or not _active(ad, delivery["placement"], now):
            return None
        if not self._policy(self.policy.open_delivery_eligible, delivery, ad, now):
            return None
        if not self._policy(self.policy.budget_eligible, repository, ad, now):
            return None
        if self._asset(repository, delivery["ad_snapshot"]["asset_id"]) is None:
            return None
        repository.lock_ad(ad)
        return ad

    def provide(
        self,
        placement,
        *,
        owner_guest_id,
        measurement_available,
        request_id,
        delivery_id=None,
        delivery_token=None,
        idempotency_key=None,
    ):
        _context(owner_guest_id, measurement_available, request_id)
        if not isinstance(placement, str) or placement not in {"top", "bottom"}:
            raise ValidationError(fields={"placement": "top 또는 bottom이 필요합니다."})
        if idempotency_key is not None:
            _reference(idempotency_key, "Idempotency-Key")
        if delivery_id is None and delivery_token is not None:
            raise ValidationError(
                fields={"delivery_id": "배달 검증 자료에는 delivery_id가 필요합니다."}
            )
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
        request_hash = canonical_hash({"placement": placement}) if key_hash else None
        new_id = self.id_factory()

        def commit(repository):
            now = self._now()
            if delivery_id is not None:
                delivery = self._verify_delivery(repository, delivery_id, delivery_token)
                self._owner(delivery, owner_guest_id)
                if delivery["placement"] != placement:
                    raise NotFound("광고 배달 자료를 찾을 수 없습니다.")
                available = (
                    measurement_available
                    and delivery["measurement_available"]
                    and delivery["owner_guest_id"] == owner_guest_id
                )
                current = self._open_ad(repository, delivery, now)
                if current is None:
                    return self._empty(now, available)
                repository.touch_delivery(delivery_id, None, used_at=now)
                return self._response(delivery, now, available, ends_at=current["ends_at"])
            if key_hash:
                previous = repository.get_delivery_request(owner_guest_id, placement, key_hash)
                if previous is not None:
                    if previous["request_hash"] != request_hash:
                        raise IdempotencyConflict()
                    return deepcopy(previous["response_snapshot"])
            candidates = []
            documents = {}
            for ad in repository.list_candidates(placement, now):
                asset_available = self._asset(repository, ad["asset_id"]) is not None
                budget_eligible = self._policy(self.policy.budget_eligible, repository, ad, now)
                candidate = AdCandidate(
                    ad_id=ad["_id"],
                    placement=ad["placement"],
                    starts_at=ad["starts_at"],
                    ends_at=ad["ends_at"],
                    priority=ad["priority"],
                    paused=ad["paused"],
                    asset_available=asset_available,
                    budget_eligible=budget_eligible,
                    is_test=ad["is_test"],
                )
                candidates.append(candidate)
                documents[ad["_id"]] = ad
            rotation = repository.get_rotation(placement)
            decision = select_ad(
                candidates,
                placement=placement,
                now=now,
                cursor=RotationCursor(placement, rotation["last_ad_id"] if rotation else None),
                is_test=self.is_test,
            )
            if decision.selected is None:
                return self._empty(now, measurement_available)
            ad = documents[decision.selected.ad_id]
            repository.lock_ad(ad)
            try:
                if self.policy.split_deadlines:
                    display_expires, expires = delivery_deadlines(
                        now,
                        ad["ends_at"],
                        self.policy.delivery_ttl_seconds,
                        cap_at_midnight=self.policy.cap_at_midnight,
                    )
                else:
                    display_expires = None
                    expires = now + timedelta(seconds=self.policy.delivery_ttl_seconds)
            except OverflowError:
                raise DomainError(
                    "ADS_POLICY_UNAVAILABLE", "배달 수명 설정의 시간 범위를 확인해 주세요.", 503
                ) from None
            delivery = {
                "_id": new_id,
                "schema_version": PUBLIC_SCHEMA_VERSION,
                "is_test": self.is_test,
                "owner_guest_id": owner_guest_id,
                "measurement_available": measurement_available,
                "ad_id": ad["_id"],
                "ad_version": ad["version"],
                "creative_version": ad["creative_version"],
                "placement": placement,
                "ad_snapshot": _snapshot(ad),
                "issued_at": now,
                "event_expires_at": expires,
                "last_used_at": now,
                "last_received_at": None,
                "claims": {},
                "request_key_hash": key_hash,
                "request_hash": request_hash,
                "policy_version": self.policy.version,
            }
            if display_expires is not None:
                delivery["display_expires_at"] = display_expires
            if self.policy.check_budget_history:
                delivery["budget_policy_version"] = self.policy.version
            token = self._token(delivery)
            delivery["token_hash"] = hashlib.sha256(token.encode()).hexdigest()
            response = self._response(delivery, now, measurement_available)
            delivery["response_snapshot"] = deepcopy(response)
            validate_bson_size(delivery)
            repository.advance_rotation(
                placement, rotation["revision"] if rotation else None, ad["_id"], now
            )
            repository.insert_delivery(delivery)
            return response

        return self.repository.run(commit)

    def _log_record(self, event, decision, delivery, request_id):
        payload = {
            "log_event_id": f"ads-event:{event.event_id}",
            "source_event_id": event.event_id,
            "schema_version": PUBLIC_SCHEMA_VERSION,
            "request_id": request_id,
            "ad_id": delivery["ad_id"],
            "creative_version": delivery["creative_version"],
            "placement": delivery["placement"],
            "event_type": event.event_type,
            "result": decision.result,
            "counted": decision.counted,
            "occurred_at": utc_string(decision.occurred_at),
            "received_at": utc_string(decision.received_at),
            "processed_at": utc_string(decision.processed_at),
            "is_test": self.is_test,
            "estimated_tokens": decision.estimated_tokens,
            "ads_policy_version": decision.ads_policy_version,
        }
        return {
            "log_event_id": payload["log_event_id"],
            "payload": payload,
            "payload_hash": canonical_hash(payload),
            "stored_at": decision.processed_at,
            "log_schema_version": "ads-mongo-log-20261015.1",
        }

    def record_event(
        self,
        data,
        *,
        owner_guest_id,
        measurement_available,
        delivery_token,
        request_id,
    ):
        _context(owner_guest_id, measurement_available, request_id)
        event = validate_event_input(data)
        received_at = self._now()

        def commit(repository):
            delivery = self._verify_delivery(repository, event.delivery_id, delivery_token)
            self._owner(delivery, owner_guest_id)
            previous = repository.get_event(event.event_id)
            if previous is not None:
                if previous["owner_guest_id"] != owner_guest_id:
                    raise NotFound("광고 이벤트 자료를 찾을 수 없습니다.")
                if previous["request_hash"] != event.request_hash:
                    raise IdempotencyConflict()
                return deepcopy(previous["response_snapshot"])
            current_ad = repository.get_ad(delivery["ad_id"])
            if current_ad is not None:
                repository.lock_ad(current_ad)
            historical = repository.historical_ad(delivery["ad_id"], event.occurred_at)
            snapshot = _snapshot(historical) if historical is not None else delivery["ad_snapshot"]
            available = (
                measurement_available
                and delivery["measurement_available"]
                and owner_guest_id is not None
                and delivery["owner_guest_id"] == owner_guest_id
            )
            occurrence_eligible = (
                historical is not None
                and _active(historical, delivery["placement"], event.occurred_at)
                and self._policy(
                    self.policy.occurrence_eligible, delivery, historical, event.occurred_at
                )
            )
            uses_budget_policy = "budget_policy_version" in delivery
            if uses_budget_policy and not self.policy.check_budget_history:
                raise DomainError(
                    "ADS_POLICY_UNAVAILABLE", "배달 당시 예산 정책 연결이 필요합니다.", 503
                )
            if occurrence_eligible and uses_budget_policy:
                occurrence_eligible = budget_occurrence_eligible(
                    repository, historical, event.occurred_at
                )
            context = DeliveryContext(
                delivery_id=delivery["_id"],
                owner_guest_id=delivery["owner_guest_id"],
                ad_id=delivery["ad_id"],
                creative_version=delivery["creative_version"],
                placement=delivery["placement"],
                issued_at=delivery["issued_at"],
                starts_at=snapshot["starts_at"],
                ends_at=snapshot["ends_at"],
                stopped_at=snapshot["stopped_at"],
                is_test=self.is_test,
                display_expires_at=delivery.get("display_expires_at"),
            )
            window = None
            if available:
                window = repository.get_repeat_window(
                    owner_guest_id, delivery["ad_id"], delivery["placement"], event.event_type
                )
            processed_at = self._now()
            outcome = judge_event(
                event,
                delivery=context,
                owner_guest_id=owner_guest_id,
                received_at=received_at,
                processed_at=processed_at,
                delivery_valid=received_at < utc_datetime(delivery["event_expires_at"]),
                occurrence_eligible=bool(occurrence_eligible),
                measurement_available=available,
                delivery_type_consumed=event.event_type in delivery["claims"],
                last_accepted_at=window["accepted_at"] if window else None,
                ads_policy_version=delivery["budget_policy_version"]
                if uses_budget_policy
                else ADS_POLICY_VERSION,
            )
            decision = outcome.decision
            if outcome.consume_delivery_type:
                repository.claim_delivery_type(
                    delivery["_id"], event.event_type, event.event_id, decision.result, processed_at
                )
            if outcome.new_accepted_at is not None:
                repository.advance_repeat_window(
                    owner_guest_id,
                    delivery["ad_id"],
                    delivery["placement"],
                    event.event_type,
                    window["revision"] if window else None,
                    outcome.new_accepted_at,
                )
            response = decision.as_response()
            record = {
                "_id": event.event_id,
                "event_id": event.event_id,
                "schema_version": PUBLIC_SCHEMA_VERSION,
                "is_test": self.is_test,
                "owner_guest_id": owner_guest_id,
                "request_hash": event.request_hash,
                "request_payload": {
                    "event_id": event.event_id,
                    "delivery_id": event.delivery_id,
                    "event_type": event.event_type,
                    "occurred_at": utc_string(event.occurred_at),
                },
                "delivery_id": delivery["_id"],
                "ad_id": delivery["ad_id"],
                "creative_version": delivery["creative_version"],
                "placement": delivery["placement"],
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "received_at": received_at,
                "processed_at": processed_at,
                "accepted_at": decision.accepted_at,
                "result": decision.result,
                "counted": decision.counted,
                "metric_date_kst": decision.metric_date_kst.isoformat()
                if decision.metric_date_kst
                else None,
                "estimated_tokens": decision.estimated_tokens,
                "ads_policy_version": decision.ads_policy_version,
                "response_snapshot": deepcopy(response),
                "retention_due_at": None,
                "log_record": self._log_record(event, decision, delivery, request_id),
            }
            validate_bson_size(record)
            repository.insert_event(record)
            if decision.counted:
                repository.insert_usage_entry(
                    {
                        "_id": f"usage:{event.event_id}",
                        "event_id": event.event_id,
                        "schema_version": PUBLIC_SCHEMA_VERSION,
                        "is_test": self.is_test,
                        "delivery_id": delivery["_id"],
                        "ad_id": delivery["ad_id"],
                        "creative_version": delivery["creative_version"],
                        "placement": delivery["placement"],
                        "event_type": event.event_type,
                        "metric_date_kst": record["metric_date_kst"],
                        "occurred_at": event.occurred_at,
                        "processed_at": processed_at,
                        "ads_policy_version": decision.ads_policy_version,
                        "unit_tokens": decision.estimated_tokens,
                        "estimated_tokens": decision.estimated_tokens,
                        "status": "ESTIMATED",
                        "retention_due_at": None,
                    }
                )
            repository.touch_delivery(delivery["_id"], received_at)
            return response

        return self.repository.run(commit)

    def read_image(self, delivery_id, *, delivery_token):
        def read(repository):
            delivery = self._verify_delivery(repository, delivery_id, delivery_token)
            now = self._now()
            if self._open_ad(repository, delivery, now) is None:
                raise NotFound("게시 가능한 광고 이미지를 찾을 수 없습니다.")
            asset = self._asset(repository, delivery["ad_snapshot"]["asset_id"])
            if asset is None:
                raise NotFound("게시 가능한 광고 이미지를 찾을 수 없습니다.")
            repository.touch_delivery(delivery_id, None, used_at=now)
            return bytes(asset["image_bytes"]), asset["mime_type"]

        return self.repository.run(read)
