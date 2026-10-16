"""확정 보관 기산점과 참조를 읽기 점검합니다. 삭제 가능 판정이나 데이터 변경은 하지 않습니다."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta, timezone

from domains.ads.errors import DomainError
from domains.ads.validation import utc_datetime, utc_string

KST = timezone(timedelta(hours=9))
RETENTION_DAYS = {
    "ad_events": 90,
    "ad_deliveries": 90,
    "ad_admin_changes": 365,
    "ad_estimated_usage_ledger": 365,
    "ad_daily_metrics": 365,
}
UNRESOLVED_COLLECTIONS = {
    "ad_assets": "ASSET_RETENTION_PENDING",
    "ad_budget_states": "BUDGET_HISTORY_RETENTION_PENDING",
    "ads": "CURRENT_CONFIGURATION",
    "ad_rotation_state": "CURRENT_ROTATION_STATE",
    "ad_repeat_windows": "REPEAT_STATE_CLEANUP_PENDING",
}
PROJECTION = {
    "_id": 1,
    "ad_id": 1,
    "asset_id": 1,
    "event_id": 1,
    "received_at": 1,
    "last_used_at": 1,
    "last_received_at": 1,
    "event_expires_at": 1,
    "occurred_at": 1,
    "processed_at": 1,
    "metric_date_kst": 1,
    "changed": 1,
}


def retention_state(collection, document, *, now):
    """기간 도래는 재검토 대상이라는 뜻입니다. 삭제 허용을 반환하지 않습니다."""
    now = utc_datetime(now)
    if collection not in RETENTION_DAYS:
        raise ValueError("확정 보관 기산점이 있는 컬렉션만 검사할 수 있습니다.")
    try:
        if collection == "ad_events":
            base = utc_datetime(document["received_at"])
        elif collection == "ad_deliveries":
            base = utc_datetime(document["last_used_at"])
            if document.get("last_received_at") is not None:
                base = max(base, utc_datetime(document["last_received_at"]))
        elif collection == "ad_admin_changes":
            if type(document.get("changed")) is not bool:
                raise ValueError
            if not document["changed"]:
                return {"status": "POLICY_PENDING", "due_at": None}
            base = utc_datetime(document["occurred_at"])
        elif collection == "ad_estimated_usage_ledger":
            base = utc_datetime(document["processed_at"])
        else:
            value = document["metric_date_kst"]
            day = date.fromisoformat(value)
            if day.isoformat() != value:
                raise ValueError
            # 해당 발생일 다음 KST 자정부터365일. 집계 실행일/as_of로 연장하지 않습니다.
            base = datetime.combine(day + timedelta(days=1), datetime.min.time(), KST)
            base = base.astimezone(UTC)
        if collection != "ad_daily_metrics" and base > now:
            raise ValueError
        due = base + timedelta(days=RETENTION_DAYS[collection])
        return {
            "status": "REVIEW_DUE" if due <= now else "WITHIN_RETENTION",
            "due_at": utc_string(due),
        }
    except (DomainError, KeyError, TypeError, ValueError, OverflowError):
        return {"status": "INVALID_BASIS", "due_at": None}


def reference_observations(database, collection, document, *, is_test, now):
    """참조의 존재만 확인합니다. 기간 연장/삭제 금지를 새 정책으로 확정하지 않습니다."""
    observations = []

    def exists(name, **fields):
        return database[name].find_one({"is_test": is_test, **fields}, {"_id": 1}) is not None

    ad_id = document.get("ad_id")
    if isinstance(ad_id, str) and ad_id and exists("ads", _id=ad_id):
        observations.append("AD_REFERENCE")
    if collection == "ad_admin_changes":
        asset_id = document.get("asset_id")
        if isinstance(asset_id, str) and asset_id and exists("ads", asset_id=asset_id):
            observations.append("ASSET_REFERENCE")
        if isinstance(ad_id, str) and ad_id and exists("ad_deliveries", ad_id=ad_id):
            observations.append("DELIVERY_HISTORY_REFERENCE")
    elif collection == "ad_deliveries":
        identifier = document.get("_id")
        if isinstance(identifier, str) and identifier:
            if exists("ad_events", delivery_id=identifier):
                observations.append("EVENT_REFERENCE")
            if exists("ad_estimated_usage_ledger", delivery_id=identifier):
                observations.append("LEDGER_REFERENCE")
        try:
            if utc_datetime(document["event_expires_at"]) > now:
                observations.append("REPORT_WINDOW_OPEN")
        except (DomainError, KeyError, TypeError, ValueError, OverflowError):
            observations.append("REPORT_DEADLINE_INVALID")
    elif collection == "ad_events":
        event_id = document.get("event_id")
        if (
            isinstance(event_id, str)
            and event_id
            and exists("ad_estimated_usage_ledger", event_id=event_id)
        ):
            observations.append("LEDGER_REFERENCE")
    elif collection == "ad_estimated_usage_ledger":
        if isinstance(ad_id, str) and ad_id and exists("ad_budget_states", ad_id=ad_id):
            observations.append("BUDGET_HISTORY_REFERENCE")
    return observations


def inspect_retention(database, *, is_test, limit=100, now=None):
    if type(is_test) is not bool or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("시험 환경은bool, 표본 수는1~1000 정수여야 합니다.")
    now = utc_datetime(now or datetime.now(UTC))
    report = {
        "scope": "READ_ONLY_RETENTION_REVIEW",
        "checked_at": utc_string(now),
        "is_test": is_test,
        "deletion_allowed": False,
        "snapshot_consistent": False,
        "collections": {},
        "excluded": {},
    }
    for name, days in RETENTION_DAYS.items():
        collection = database[name]
        total = collection.count_documents({"is_test": is_test})
        sample = list(
            collection.find({"is_test": is_test}, PROJECTION).sort("_id", 1).limit(limit + 1)
        )
        statuses, references = Counter(), Counter()
        due_with_references = 0
        for document in sample[:limit]:
            state = retention_state(name, document, now=now)
            statuses[state["status"]] += 1
            if state["status"] == "REVIEW_DUE":
                observed = reference_observations(
                    database, name, document, is_test=is_test, now=now
                )
                references.update(observed)
                due_with_references += int(bool(observed))
        report["collections"][name] = {
            "retention_days": days,
            "total": total,
            "sample_checked": min(limit, len(sample)),
            "sample_document_limit": limit,
            "sample_has_more": len(sample) > limit,
            "sample_statuses": dict(statuses),
            "sample_due_with_references": due_with_references,
            "sample_reference_observations": dict(references),
        }
    for name, reason in UNRESOLVED_COLLECTIONS.items():
        report["excluded"][name] = {
            "total": database[name].count_documents({"is_test": is_test}),
            "reason": reason,
        }
    report["status"] = (
        "INVALID_DATA"
        if any(
            row["sample_statuses"].get("INVALID_BASIS", 0) for row in report["collections"].values()
        )
        else "REVIEW_READY"
    )
    return report
