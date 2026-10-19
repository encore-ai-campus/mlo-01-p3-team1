"""첫 관리 단계의 세 컬렉션을 위한 MongoDB 저장 어댑터."""

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, TypeVar

from django.conf import settings
from pymongo import DESCENDING, MongoClient, ReadPreference, timeout
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from domains.ads.errors import DatabaseUnavailable, ValidationError, VersionConflict

Document = dict[str, Any]
CursorPosition = tuple[datetime, str]
Result = TypeVar("Result")
STATUS_NAMES = ("RESERVED", "ACTIVE", "ENDED", "STOPPED")
IDEMPOTENCY_FIELDS = {
    "identity_source",
    "actor_account_id",
    "operation",
    "resource_scope",
    "idempotency_key_hash",
}


class DuplicateMutation(Exception):
    """멱등 고유키 경합 후 새 트랜잭션에서 최초 성공 기록을 다시 조회합니다."""


def _budget_blocked_expression(now: datetime) -> Document:
    return {
        "$and": [
            {"$eq": [{"$type": "$budget_blocked_at"}, "date"]},
            {"$eq": [{"$type": "$budget_version"}, "string"]},
            {"$eq": ["$budget_version", "$budget_blocked_version"]},
            {"$lte": ["$budget_blocked_at", now]},
            {
                "$or": [
                    {"$eq": [{"$ifNull": ["$budget_blocked_until", None]}, None]},
                    {"$gt": ["$budget_blocked_until", now]},
                ]
            },
        ]
    }


def _status_filter(status: str | None, now: datetime) -> Document:
    if status is None:
        return {}
    if status == "STOPPED":
        return {"paused": True}
    if status == "RESERVED":
        return {
            "paused": False,
            "starts_at": {"$gt": now},
            "$expr": {"$not": [_budget_blocked_expression(now)]},
        }
    if status == "ACTIVE":
        return {
            "paused": False,
            "starts_at": {"$lte": now},
            "ends_at": {"$gt": now},
            "$expr": {"$not": [_budget_blocked_expression(now)]},
        }
    if status == "ENDED":
        return {
            "paused": False,
            "$or": [{"ends_at": {"$lte": now}}, {"$expr": _budget_blocked_expression(now)}],
        }
    raise ValidationError("알 수 없는 광고 상태입니다.")


class MongoAdsRepository:
    """서비스 콜백 하나를 snapshot/majority/primary 트랜잭션으로 실행합니다."""

    def __init__(self, client=None, database_name=None, *, is_test=None, session=None):
        self._session = session
        self._is_test = getattr(settings, "ADS_IS_TEST", True) if is_test is None else is_test
        database_name = database_name or settings.ADS_MONGODB_DATABASE
        try:
            if client is None:
                uri = settings.ADS_MONGODB_URI
                if not uri:
                    raise DatabaseUnavailable("광고 저장소 연결 설정이 필요합니다.")
                client = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    timeoutMS=10000,
                    tz_aware=True,
                    readPreference="primary",
                )
            self._client = client
            self._database_name = database_name
            self._database = client.get_database(
                database_name,
                read_preference=ReadPreference.PRIMARY,
                read_concern=ReadConcern("majority"),
                write_concern=WriteConcern("majority"),
            )
        except PyMongoError:
            raise DatabaseUnavailable("광고 저장소 연결 설정을 확인해 주세요.") from None

    def _require_primary(self) -> None:
        hello = self._client.admin.command("hello")
        if not hello.get("setName") or not hello.get("isWritablePrimary"):
            raise DatabaseUnavailable("광고 저장소의 replica set primary에 연결할 수 없습니다.")

    @property
    def database(self):
        """로그 전달 작업자가 같은 광고 저장소에 접근할 때 primary를 확인합니다."""
        return self._read(lambda: self._database)

    @property
    def is_test(self) -> bool:
        return self._is_test

    def run(self, callback: Callable[["MongoAdsRepository"], Result]) -> Result:
        """driver 재시도 후 커밋된 결과만 반환하고 멱등 고유키 경합은 한 번 재조회합니다."""
        if self._session is not None:
            raise RuntimeError("광고 트랜잭션을 중첩해서 실행할 수 없습니다.")
        try:
            with timeout(10):
                self._require_primary()
                for attempt in range(2):
                    try:
                        with self._client.start_session() as session:
                            transaction_repository = type(self)(
                                self._client,
                                self._database_name,
                                is_test=self._is_test,
                                session=session,
                            )
                            return session.with_transaction(
                                lambda active: callback(transaction_repository),
                                read_concern=ReadConcern("snapshot"),
                                write_concern=WriteConcern("majority"),
                                read_preference=ReadPreference.PRIMARY,
                            )
                    except DuplicateMutation:
                        if attempt:
                            raise DatabaseUnavailable("광고 저장 요청의 처리 결과를 확인해 주세요.")
                raise DatabaseUnavailable("광고 저장 요청을 처리할 수 없습니다.")
        except PyMongoError:
            # 트랜잭션 내부에서는 driver의 transient/unknown-commit 라벨을 보존합니다.
            raise DatabaseUnavailable(
                "광고 저장소에 연결할 수 없습니다. 같은 요청으로 재시도해 주세요."
            ) from None

    def _read(self, operation: Callable[[], Result]) -> Result:
        try:
            if self._session is None:
                self._require_primary()
            return operation()
        except PyMongoError:
            if self._session is not None:
                raise
            raise DatabaseUnavailable("광고 저장소를 조회할 수 없습니다.") from None

    def _require_transaction(self) -> None:
        if self._session is None:
            raise RuntimeError("광고 변경은 run 콜백의 트랜잭션 안에서만 허용됩니다.")

    def get_mutation(
        self,
        identity_source: str,
        actor_account_id: str,
        operation: str,
        resource_scope: str,
        idempotency_key_hash: str,
    ) -> Document | None:
        query = {
            "identity_source": identity_source,
            "actor_account_id": actor_account_id,
            "operation": operation,
            "resource_scope": resource_scope,
            "idempotency_key_hash": idempotency_key_hash,
            "is_test": self._is_test,
        }
        return self._read(
            lambda: deepcopy(
                self._database["ad_admin_changes"].find_one(query, session=self._session)
            )
        )

    def get_ad(self, ad_id: str) -> Document | None:
        return self._read(
            lambda: deepcopy(
                self._database["ads"].find_one(
                    {"_id": ad_id, "is_test": self._is_test}, session=self._session
                )
            )
        )

    def get_asset(self, asset_id: str) -> Document | None:
        return self._read(
            lambda: deepcopy(
                self._database["ad_assets"].find_one(
                    {"_id": asset_id, "is_test": self._is_test}, session=self._session
                )
            )
        )

    def insert_asset(self, document: Document) -> None:
        self._require_transaction()
        self._database["ad_assets"].insert_one(deepcopy(document), session=self._session)

    def insert_ad(self, document: Document) -> None:
        self._require_transaction()
        self._database["ads"].insert_one(deepcopy(document), session=self._session)

    def replace_ad(self, ad_id: str, expected_version: int, document: Document) -> bool:
        self._require_transaction()
        collection = self._database["ads"]
        query = {"_id": ad_id, "version": expected_version, "is_test": self._is_test}
        result = collection.replace_one(
            query,
            deepcopy(document),
            session=self._session,
        )
        if result.matched_count != 1:
            return False
        if result.modified_count == 0:
            # 동일 문서 쓰기는 잠금을 보장하지 않습니다. 실제 쓰기와 복원을 한
            # 트랜잭션에서 수행하여 최종 업무 version/updated_at은 그대로 유지합니다.
            temporary_version = 1 if expected_version != 1 else 2
            locked = collection.update_one(
                query,
                {"$set": {"version": temporary_version}},
                session=self._session,
            )
            if locked.matched_count != 1 or locked.modified_count != 1:
                raise VersionConflict()
            restored = collection.replace_one(
                {"_id": ad_id, "version": temporary_version, "is_test": self._is_test},
                deepcopy(document),
                session=self._session,
            )
            if restored.matched_count != 1 or restored.modified_count != 1:
                raise VersionConflict()
        return True

    def insert_mutation(self, document: Document) -> None:
        self._require_transaction()
        try:
            self._database["ad_admin_changes"].insert_one(deepcopy(document), session=self._session)
        except DuplicateKeyError as error:
            details = error.details or {}
            key_pattern = details.get("keyPattern", {})
            if set(key_pattern) == IDEMPOTENCY_FIELDS or "admin_idempotency" in str(
                details.get("errmsg", "")
            ):
                raise DuplicateMutation from None
            raise

    def list_ads(
        self,
        *,
        placement: str | None = None,
        status: str | None = None,
        now: datetime | None = None,
        limit: int = 20,
        cursor: CursorPosition | None = None,
    ) -> tuple[list[Document], bool]:
        now = now or datetime.now(timezone.utc)
        query = {"is_test": self._is_test, **_status_filter(status, now)}
        if placement is not None:
            query["placement"] = placement
        if cursor is not None:
            updated_at, ad_id = cursor
            page_condition = {
                "$or": [
                    {"updated_at": {"$lt": updated_at}},
                    {"updated_at": updated_at, "_id": {"$lt": ad_id}},
                ]
            }
            if "$or" in query:
                query["$and"] = [{"$or": query.pop("$or")}, page_condition]
            else:
                query.update(page_condition)

        def fetch():
            documents = list(
                self._database["ads"]
                .find(query, session=self._session)
                .sort([("updated_at", DESCENDING), ("_id", DESCENDING)])
                .limit(limit + 1)
            )
            return deepcopy(documents[:limit]), len(documents) > limit

        return self._read(fetch)

    def summary(self, now: datetime) -> dict[str, int]:
        pipeline = [
            {"$match": {"is_test": self._is_test}},
            {
                "$group": {
                    "_id": {
                        "$switch": {
                            "branches": [
                                {"case": "$paused", "then": "STOPPED"},
                                {"case": {"$lte": ["$ends_at", now]}, "then": "ENDED"},
                                {"case": _budget_blocked_expression(now), "then": "ENDED"},
                                {"case": {"$gt": ["$starts_at", now]}, "then": "RESERVED"},
                            ],
                            "default": "ACTIVE",
                        }
                    },
                    "count": {"$sum": 1},
                }
            },
        ]

        def fetch():
            counts = dict.fromkeys(STATUS_NAMES, 0)
            for item in self._database["ads"].aggregate(pipeline, session=self._session):
                counts[item["_id"]] = item["count"]
            return counts

        return self._read(fetch)

    def metrics_summary(self, now: datetime, ad_id: str | None = None) -> Document:
        from repositories.ads_policy_mongo import MongoAdsPolicyRepository

        repository = MongoAdsPolicyRepository(
            self._client, self._database_name, is_test=self._is_test, session=self._session
        )
        return repository.metrics_summary(now, ad_id=ad_id)


@lru_cache(maxsize=1)
def _configured_repository(uri: str, database: str, is_test: bool) -> MongoAdsRepository:
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
        return MongoAdsRepository(client, database, is_test=is_test)
    except PyMongoError:
        raise DatabaseUnavailable("광고 저장소 연결 설정을 확인해 주세요.") from None


def get_ads_repository() -> MongoAdsRepository:
    return _configured_repository(
        settings.ADS_MONGODB_URI,
        settings.ADS_MONGODB_DATABASE,
        getattr(settings, "ADS_IS_TEST", True),
    )
