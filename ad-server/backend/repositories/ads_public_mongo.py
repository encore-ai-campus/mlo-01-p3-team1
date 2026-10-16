"""공개 광고의 선정·배달·측정 상태를 한 MongoDB 트랜잭션에 저장합니다."""

from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from json import dumps

from django.conf import settings
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from domains.ads.errors import DatabaseUnavailable, ValidationError, VersionConflict
from repositories.ads_mongo import Document, DuplicateMutation, MongoAdsRepository

PUBLIC_SCHEMA_VERSION = "phase3-ads-public-20261015.2"
EVENT_TYPES = frozenset({"VIEWABLE_IMPRESSION", "CLICK"})


def _state_id(*parts) -> str:
    """배치/반복 상태의 구분자를 충돌 없이 고정하고 원본 guest ID를 키에 노출하지 않습니다."""
    return sha256(dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _event_type(event_type: str) -> None:
    if event_type not in EVENT_TYPES:
        raise ValidationError(fields={"event_type": "지원하지 않는 광고 측정 유형입니다."})


class MongoPublicAdsRepository(MongoAdsRepository):
    """공개 상태 쓰기는 run 콜백 안에서만 실행하며 경합은 새 snapshot에서 재조회합니다."""

    def list_candidates(self, placement: str, now: datetime) -> list[Document]:
        query = {
            "placement": placement,
            "is_test": self._is_test,
            "paused": False,
            "starts_at": {"$lte": now},
            "ends_at": {"$gt": now},
        }
        return self._read(
            lambda: deepcopy(
                list(
                    self._database["ads"]
                    .find(query, session=self._session)
                    .sort([("priority", DESCENDING), ("_id", ASCENDING)])
                )
            )
        )

    def get_rotation(self, placement: str) -> Document | None:
        return self._get("ad_rotation_state", {"_id": _state_id(placement, self._is_test)})

    def advance_rotation(
        self, placement: str, expected_revision: int | None, last_ad_id: str, now: datetime
    ) -> None:
        self._advance_state(
            "ad_rotation_state",
            {"_id": _state_id(placement, self._is_test), "placement": placement},
            expected_revision,
            {"last_ad_id": last_ad_id, "updated_at": now},
        )

    def get_delivery(self, delivery_id: str) -> Document | None:
        return self._get("ad_deliveries", {"_id": delivery_id})

    def get_delivery_request(
        self, owner_guest_id: str | None, placement: str, key_hash: str
    ) -> Document | None:
        return self._get(
            "ad_deliveries",
            {
                "owner_guest_id": owner_guest_id,
                "placement": placement,
                "request_key_hash": key_hash,
            },
        )

    def insert_delivery(self, document: Document) -> None:
        self._insert("ad_deliveries", document)

    def lock_ad(self, ad: Document) -> None:
        """발행/판정과 관리자 변경의 경합을 같은 ads 문서의 실제 쓰기로 직렬화합니다."""
        try:
            matched = self.replace_ad(ad["_id"], ad["version"], deepcopy(ad))
        except VersionConflict:
            raise DuplicateMutation from None
        if not matched:
            raise DuplicateMutation

    def historical_ad(self, ad_id: str, occurred_at: datetime) -> Document | None:
        def fetch():
            change = self._database["ad_admin_changes"].find_one(
                {
                    "ad_id": ad_id,
                    "is_test": self._is_test,
                    "occurred_at": {"$lte": occurred_at},
                    "operation": {"$in": ["CREATE", "UPDATE", "STOP"]},
                },
                sort=[("occurred_at", DESCENDING), ("version_after", DESCENDING)],
                session=self._session,
            )
            return deepcopy(change["after_snapshot"]) if change is not None else None

        return self._read(fetch)

    def get_event(self, event_id: str) -> Document | None:
        return self._get("ad_events", {"_id": event_id})

    def insert_event(self, document: Document) -> None:
        self._insert("ad_events", document)

    def get_repeat_window(
        self, owner_guest_id: str, ad_id: str, placement: str, event_type: str
    ) -> Document | None:
        _event_type(event_type)
        return self._get(
            "ad_repeat_windows",
            {"_id": _state_id(owner_guest_id, ad_id, placement, event_type, self._is_test)},
        )

    def advance_repeat_window(
        self,
        owner_guest_id: str,
        ad_id: str,
        placement: str,
        event_type: str,
        expected_revision: int | None,
        accepted_at: datetime,
    ) -> None:
        _event_type(event_type)
        self._advance_state(
            "ad_repeat_windows",
            {
                "_id": _state_id(owner_guest_id, ad_id, placement, event_type, self._is_test),
                "owner_guest_id": owner_guest_id,
                "ad_id": ad_id,
                "placement": placement,
                "event_type": event_type,
            },
            expected_revision,
            {"accepted_at": accepted_at},
        )

    def claim_delivery_type(
        self,
        delivery_id: str,
        event_type: str,
        event_id: str,
        result: str,
        processed_at: datetime,
    ) -> None:
        self._require_transaction()
        _event_type(event_type)
        if result not in {"COUNTED", "REPEAT_SUPPRESSED"}:
            raise ValidationError("해당 판정은 delivery 유형을 소비할 수 없습니다.")
        claim_path = f"claims.{event_type}"
        updated = self._database["ad_deliveries"].update_one(
            {
                "_id": delivery_id,
                "is_test": self._is_test,
                claim_path: {"$exists": False},
            },
            {
                "$set": {
                    claim_path: {
                        "event_id": event_id,
                        "result": result,
                        "processed_at": processed_at,
                    }
                }
            },
            session=self._session,
        )
        if updated.matched_count != 1:
            raise DuplicateMutation

    def touch_delivery(
        self, delivery_id: str, received_at: datetime | None, *, used_at: datetime | None = None
    ) -> None:
        self._require_transaction()
        timestamps = {}
        if received_at is not None:
            timestamps["last_received_at"] = received_at
        if used_at is not None:
            timestamps["last_used_at"] = used_at
        if not timestamps:
            raise ValidationError("광고 배달의 사용 또는 수신 시각이 필요합니다.")
        updated = self._database["ad_deliveries"].update_one(
            {"_id": delivery_id, "is_test": self._is_test},
            {"$max": timestamps},
            session=self._session,
        )
        if updated.matched_count != 1:
            raise DuplicateMutation

    def insert_usage_entry(self, document: Document) -> None:
        self._insert("ad_estimated_usage_ledger", document)

    def _get(self, collection: str, query: Document) -> Document | None:
        return self._read(
            lambda: deepcopy(
                self._database[collection].find_one(
                    {**query, "is_test": self._is_test}, session=self._session
                )
            )
        )

    def _insert(self, collection: str, document: Document) -> None:
        self._require_transaction()
        if document.get("is_test") is not self._is_test:
            raise ValidationError("광고 저장 환경이 일치하지 않습니다.")
        try:
            self._database[collection].insert_one(deepcopy(document), session=self._session)
        except DuplicateKeyError:
            raise DuplicateMutation from None

    def _advance_state(
        self, collection: str, identity: Document, expected_revision: int | None, values: Document
    ) -> None:
        self._require_transaction()
        scoped = {**identity, "is_test": self._is_test}
        if expected_revision is None:
            self._insert(
                collection,
                {**scoped, "schema_version": PUBLIC_SCHEMA_VERSION, "revision": 1, **values},
            )
            return
        updated = self._database[collection].update_one(
            {**scoped, "revision": expected_revision},
            {"$set": deepcopy(values), "$inc": {"revision": 1}},
            session=self._session,
        )
        if updated.matched_count != 1:
            raise DuplicateMutation


@lru_cache(maxsize=1)
def _configured_public_repository(
    uri: str, database: str, is_test: bool
) -> MongoPublicAdsRepository:
    if not uri:
        raise DatabaseUnavailable("광고 저장소 연결 설정이 필요합니다.")
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            timeoutMS=10000,
            tz_aware=True,
            readPreference="primary",
        )
        return MongoPublicAdsRepository(client, database, is_test=is_test)
    except PyMongoError:
        raise DatabaseUnavailable("광고 저장소 연결 설정을 확인해 주세요.") from None


def get_public_ads_repository() -> MongoPublicAdsRepository:
    return _configured_public_repository(
        settings.ADS_MONGODB_URI,
        settings.ADS_MONGODB_DATABASE,
        getattr(settings, "ADS_IS_TEST", True),
    )
