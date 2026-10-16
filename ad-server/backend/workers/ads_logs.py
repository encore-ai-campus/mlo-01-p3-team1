"""광고 MongoDB 내장 로그의 저장 현황과 제한된 표본의 무결성을 읽기 전용으로 점검합니다."""

from domains.ads.errors import DomainError
from domains.ads.service import canonical_hash
from domains.ads.validation import utc_datetime

LOG_COLLECTIONS = ("ad_admin_changes", "ad_events", "ad_budget_states")


def inspect_logs(database, *, is_test, limit=20):
    if type(is_test) is not bool or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("시험 환경은 bool, 표본 수는 1~100 정수여야 합니다.")
    report = {}
    for name in LOG_COLLECTIONS:
        collection = database[name]
        scope = {"is_test": is_test}
        required = dict(scope)
        if name == "ad_budget_states":
            required["$or"] = [
                {"daily_blocked_at": {"$ne": None}},
                {"total_blocked_at": {"$ne": None}},
            ]
        missing = collection.count_documents({**required, "log_record": None, "log_relay": None})
        query = {
            **scope,
            "$or": [{"log_record": {"$ne": None}}, {"log_relay": {"$ne": None}}],
        }
        checked, invalid = 0, 0
        for document in (
            collection.find(query, {"log_record": 1, "log_relay": 1}).sort("_id", 1).limit(limit)
        ):
            for field in ("log_record", "log_relay"):
                record = document.get(field)
                if record is None:
                    continue
                checked += 1
                try:
                    valid = (
                        isinstance(record["payload"], dict)
                        and record["log_event_id"] == record["payload"]["log_event_id"]
                        and record["payload_hash"] == canonical_hash(record["payload"])
                    )
                    if field == "log_record":
                        valid = valid and (
                            record["log_schema_version"] == "ads-mongo-log-20261015.1"
                        )
                        utc_datetime(record["stored_at"])
                    invalid += int(not valid)
                except (DomainError, KeyError, TypeError, ValueError, OverflowError):
                    invalid += 1
        report[name] = {
            "stored": collection.count_documents({**scope, "log_record": {"$ne": None}}),
            "legacy_preserved": collection.count_documents({**scope, "log_relay": {"$ne": None}}),
            "missing_required": missing,
            "sample_checked": checked,
            "sample_invalid": invalid,
            "sample_document_limit": limit,
        }
    return report
