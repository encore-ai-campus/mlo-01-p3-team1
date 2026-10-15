"""관리 감사 기록의 불변 로그 사본을 공통 PostgreSQL sink로 재전송합니다."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.utils.module_loading import import_string
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from domains.ads.errors import DatabaseUnavailable, DomainError
from domains.ads.validation import utc_datetime
from repositories.ads_mongo import get_ads_repository


class LogSinkRejected(Exception):
    """sink가 저장 커밋/기존 동일 payload 확인을 명시적으로 승인하지 않았습니다."""


def get_log_sink():
    """서버 설정의 sink만 사용하고 미설정이면 MongoDB claim 전에 차단합니다."""
    configured = getattr(settings, "ADS_LOG_SINK", None)
    if isinstance(configured, str):
        try:
            configured = import_string(configured)
        except (ImportError, AttributeError, ValueError):
            configured = None
    if not callable(configured):
        raise DomainError(
            "LOG_SINK_UNAVAILABLE", "공통 PostgreSQL 로그 저장 연결 설정이 필요합니다.", 503
        )
    return configured


class AdsLogRelay:
    """next_retry_at을 임시 claim 기한으로 사용하며 sink의 멱등 저장에 의존합니다."""

    def __init__(
        self, collection, sink, *, is_test=True, claim_seconds=30, retry_seconds=30, clock=None
    ):
        if not callable(sink):
            raise TypeError("로그 sink는 callable이어야 합니다.")
        for value in (claim_seconds, retry_seconds):
            if type(value) is not int or value < 1:
                raise ValueError("로그 claim/재시도 간격은 1초 이상의 정수여야 합니다.")
        self.collection = collection
        self.sink = sink
        self.is_test = is_test
        self.claim_seconds = claim_seconds
        self.retry_seconds = retry_seconds
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self):
        return utc_datetime(self.clock())

    def _claim(self):
        now = self._now()
        try:
            return self.collection.find_one_and_update(
                {
                    "is_test": self.is_test,
                    "log_relay.status": "PENDING",
                    "$or": [
                        {"log_relay.next_retry_at": None},
                        {"log_relay.next_retry_at": {"$lte": now}},
                    ],
                },
                {
                    "$inc": {"log_relay.attempt_count": 1},
                    "$set": {
                        "log_relay.next_retry_at": now + timedelta(seconds=self.claim_seconds)
                    },
                },
                sort=[("created_at", ASCENDING), ("_id", ASCENDING)],
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError:
            raise DatabaseUnavailable("광고 로그 전달 대상을 조회할 수 없습니다.") from None

    def _finish(self, document, error=None):
        relay = document["log_relay"]
        now = self._now()
        if error is None:
            changes = {
                "log_relay.status": "SENT",
                "log_relay.next_retry_at": None,
                "log_relay.last_error": None,
                "log_relay.sent_at": now,
            }
        else:
            changes = {
                "log_relay.next_retry_at": now + timedelta(seconds=self.retry_seconds),
                # SQL, 연결 URI, 인증값을 포함할 수 있는 exception 메시지는 저장하지 않습니다.
                "log_relay.last_error": type(error).__name__,
            }
        try:
            result = self.collection.update_one(
                {
                    "_id": document["_id"],
                    "is_test": self.is_test,
                    "log_relay.status": "PENDING",
                    "log_relay.attempt_count": relay["attempt_count"],
                    "log_relay.next_retry_at": relay["next_retry_at"],
                },
                {"$set": changes},
            )
        except PyMongoError:
            # PostgreSQL 커밋 후에도 여기서 실패할 수 있습니다. 같은 ID를 다시 전달합니다.
            raise DatabaseUnavailable("광고 로그 전달 상태를 기록할 수 없습니다.") from None
        return result.matched_count == 1

    def run_once(self, limit=20):
        """최대 limit개를 순차 처리하고 성공·실패·만료된 claim 수를 반환합니다."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("로그 전달 batch 크기는 1~100의 정수여야 합니다.")
        counts = {"claimed": 0, "sent": 0, "failed": 0, "stale": 0}
        for _ in range(limit):
            document = self._claim()
            if document is None:
                break
            counts["claimed"] += 1
            relay = document["log_relay"]
            error = None
            try:
                # True는 durable commit 또는 같은 ID/같은 payload 확인만 의미합니다.
                accepted = self.sink(
                    relay["log_event_id"], deepcopy(relay["payload"]), relay["payload_hash"]
                )
                if accepted is not True:
                    raise LogSinkRejected
            except Exception as caught:
                error = caught
            if not self._finish(document, error):
                counts["stale"] += 1
            else:
                counts["sent" if error is None else "failed"] += 1
        return counts


def run_configured_relay(limit=20):
    """sink 설정 확인 후 광고 저장소와 연결해 한 batch만 처리합니다."""
    sink = get_log_sink()
    repository = get_ads_repository()
    relay = AdsLogRelay(
        repository.database["ad_admin_changes"],
        sink,
        is_test=repository.is_test,
        claim_seconds=getattr(settings, "ADS_LOG_RELAY_CLAIM_SECONDS", 30),
        retry_seconds=getattr(settings, "ADS_LOG_RELAY_RETRY_SECONDS", 30),
    )
    return relay.run_once(limit)
