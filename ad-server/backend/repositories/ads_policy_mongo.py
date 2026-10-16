"""광고 예산 검증 상태와 불변 예상 원장 기반 일일 집계의 저장 어댑터입니다."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from django.conf import settings
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from domains.ads.errors import DatabaseUnavailable, ValidationError
from domains.ads.service import canonical_hash
from domains.ads.validation import utc_datetime, validate_bson_size
from repositories.ads_mongo import Document, DuplicateMutation
from repositories.ads_public_mongo import MongoPublicAdsRepository

POLICY_SCHEMA_VERSION = "phase3-ads-policy-20261015.2"
KST = timezone(timedelta(hours=9))
METRIC_COUNTERS = ("impressions", "clicks", "estimated_tokens")


def _reference(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(fields={field: "비어 있지 않은 참조 문자열이 필요합니다."})


def _day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError(fields={"metric_date_kst": "YYYY-MM-DD 날짜가 필요합니다."}) from None
    return value


def _integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value < 2**63


class MongoAdsPolicyRepository(MongoPublicAdsRepository):
    """정책 상태·물리 집계 변경은 부모 run의 snapshot 트랜잭션 안에서만 허용합니다."""

    def budget_state_id(self, ad_id: str, budget_version: str, metric_date_kst: str) -> str:
        _reference(ad_id, "ad_id")
        _reference(budget_version, "budget_version")
        return canonical_hash([ad_id, budget_version, _day(metric_date_kst), self._is_test])

    def list_policy_ads(self) -> list[Document]:
        return self._read(
            lambda: deepcopy(
                list(self._database["ads"].find({"is_test": self._is_test}, session=self._session))
            )
        )

    def usage_rows(self, ad_id: str) -> list[Document]:
        _reference(ad_id, "ad_id")
        pipeline = [
            {"$match": {"ad_id": ad_id, "is_test": self._is_test, "status": "ESTIMATED"}},
            {
                "$group": {
                    "_id": {"metric_date_kst": "$metric_date_kst", "placement": "$placement"},
                    "impressions": {
                        "$sum": {"$cond": [{"$eq": ["$event_type", "VIEWABLE_IMPRESSION"]}, 1, 0]}
                    },
                    "clicks": {"$sum": {"$cond": [{"$eq": ["$event_type", "CLICK"]}, 1, 0]}},
                    "estimated_tokens": {"$sum": "$estimated_tokens"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "metric_date_kst": "$_id.metric_date_kst",
                    "placement": "$_id.placement",
                    **{field: 1 for field in METRIC_COUNTERS},
                }
            },
            {"$sort": {"metric_date_kst": 1, "placement": 1}},
        ]
        return self._read(
            lambda: deepcopy(
                list(
                    self._database["ad_estimated_usage_ledger"].aggregate(
                        pipeline, session=self._session
                    )
                )
            )
        )

    def get_budget_state(
        self, ad_id: str, budget_version: str, metric_date_kst: str
    ) -> Document | None:
        return self._get(
            "ad_budget_states",
            {"_id": self.budget_state_id(ad_id, budget_version, metric_date_kst)},
        )

    def latest_budget_state(self, ad_id: str, budget_version: str) -> Document | None:
        return self._read(
            lambda: deepcopy(
                self._database["ad_budget_states"].find_one(
                    {"ad_id": ad_id, "budget_version": budget_version, "is_test": self._is_test},
                    sort=[("verified_at", DESCENDING), ("_id", DESCENDING)],
                    session=self._session,
                )
            )
        )

    def total_budget_cutoff(self, ad_id: str, budget_version: str) -> datetime | None:
        def fetch():
            state = self._database["ad_budget_states"].find_one(
                {
                    "ad_id": ad_id,
                    "budget_version": budget_version,
                    "is_test": self._is_test,
                    "total_blocked_at": {"$type": "date"},
                },
                sort=[("total_blocked_at", ASCENDING), ("_id", ASCENDING)],
                session=self._session,
            )
            return deepcopy(state["total_blocked_at"]) if state else None

        return self._read(fetch)

    def save_budget_state(self, document: Document, expected_revision: int | None) -> None:
        self._require_transaction()
        if document.get("is_test") is not self._is_test:
            raise ValidationError("광고 예산 저장 환경이 일치하지 않습니다.")
        identity = self.budget_state_id(
            document.get("ad_id"), document.get("budget_version"), document.get("metric_date_kst")
        )
        if expected_revision is not None and not _integer(expected_revision, minimum=1):
            raise ValidationError("이전 예산 상태 revision은 양의 정수여야 합니다.")
        if (
            document.get("_id") != identity
            or not _integer(document.get("revision"), minimum=1)
            or document["revision"] != (expected_revision or 0) + 1
        ):
            raise ValidationError("예산 상태 참조 또는 revision이 일치하지 않습니다.")
        validate_bson_size(document)
        if expected_revision is None:
            self._insert("ad_budget_states", document)
            return
        try:
            result = self._database["ad_budget_states"].replace_one(
                {"_id": identity, "is_test": self._is_test, "revision": expected_revision},
                deepcopy(document),
                session=self._session,
            )
        except DuplicateKeyError:
            raise DuplicateMutation from None
        if result.matched_count != 1:
            raise DuplicateMutation

    def replace_daily_metrics(self, ad_id: str, rows: list[Document], as_of: datetime) -> None:
        self._require_transaction()
        _reference(ad_id, "ad_id")
        as_of = utc_datetime(as_of)
        seen = set()
        for row in rows:
            day = _day(row.get("metric_date_kst"))
            placement = row.get("placement")
            if placement not in ("top", "bottom") or (day, placement) in seen:
                raise ValidationError("일일 집계는 날짜·위치별 고유 행이어야 합니다.")
            seen.add((day, placement))
            if any(not _integer(row.get(field)) for field in METRIC_COUNTERS):
                raise ValidationError("일일 집계 값은 BSON int64 범위의 음이 아닌 정수여야 합니다.")
            identity = canonical_hash([ad_id, placement, day, self._is_test])
            document = {
                "_id": identity,
                "schema_version": POLICY_SCHEMA_VERSION,
                "is_test": self._is_test,
                "ad_id": ad_id,
                "placement": placement,
                "metric_date_kst": day,
                **{field: row[field] for field in METRIC_COUNTERS},
                "as_of": as_of,
                "source": "ESTIMATED_LEDGER",
            }
            validate_bson_size(document)
            try:
                self._database["ad_daily_metrics"].replace_one(
                    {"_id": identity, "is_test": self._is_test},
                    document,
                    upsert=True,
                    session=self._session,
                )
            except DuplicateKeyError:
                raise DuplicateMutation from None

    def metrics_summary(self, now: datetime, ad_id: str | None = None) -> Document:
        now = utc_datetime(now)
        day = now.astimezone(KST).date().isoformat()
        if ad_id is not None:
            _reference(ad_id, "ad_id")

        def fetch():
            scope = {"is_test": self._is_test}
            if ad_id is not None:
                scope["ad_id"] = ad_id
            rows = list(self._database["ad_daily_metrics"].find(scope, session=self._session))
            today = [row for row in rows if row["metric_date_kst"] == day]
            ad_scope = {"is_test": self._is_test}
            if ad_id is not None:
                ad_scope["_id"] = ad_id
            ads = list(
                self._database["ads"].find(
                    ad_scope, {"_id": 1, "placement": 1}, session=self._session
                )
            )
            expected = {(ad["_id"], ad["placement"]) for ad in ads}
            covered = {(row["ad_id"], row["placement"]) for row in today} & expected
            complete = bool(today) and covered == expected
            return {
                "metric_date_kst": day,
                "today_valid_impressions": sum(row["impressions"] for row in today)
                if today
                else None,
                "today_valid_clicks": sum(row["clicks"] for row in today) if today else None,
                "today_estimated_tokens": sum(row["estimated_tokens"] for row in today)
                if today
                else None,
                "lifetime_valid_impressions": sum(row["impressions"] for row in rows)
                if rows
                else None,
                "lifetime_valid_clicks": sum(row["clicks"] for row in rows) if rows else None,
                "lifetime_estimated_tokens": sum(row["estimated_tokens"] for row in rows)
                if rows
                else None,
                "as_of": min(row["as_of"] for row in today) if today else None,
                "aggregation_status": "READY" if complete else ("PARTIAL" if today else "PENDING"),
                "coverage": {"covered": len(covered), "expected": len(expected)},
                "coverage_from": min(row["metric_date_kst"] for row in rows) if rows else None,
                "coverage_through": max(row["metric_date_kst"] for row in rows) if rows else None,
                "is_stale": now - min(row["as_of"] for row in today) > timedelta(seconds=300)
                if today
                else None,
            }

        return self._read(fetch)


@lru_cache(maxsize=1)
def _configured_policy_repository(
    uri: str, database: str, is_test: bool
) -> MongoAdsPolicyRepository:
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
        return MongoAdsPolicyRepository(client, database, is_test=is_test)
    except PyMongoError:
        raise DatabaseUnavailable("광고 저장소 연결 설정을 확인해 주세요.") from None


def get_ads_policy_repository() -> MongoAdsPolicyRepository:
    return _configured_policy_repository(
        settings.ADS_MONGODB_URI,
        settings.ADS_MONGODB_DATABASE,
        getattr(settings, "ADS_IS_TEST", True),
    )
