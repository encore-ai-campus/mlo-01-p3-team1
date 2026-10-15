"""5분 작업의 예산 검증·통계 갱신. 실제 잔액 차감이나 예약은 하지 않습니다."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

from .errors import DatabaseUnavailable
from .service import canonical_hash
from .validation import utc_datetime, utc_string, validate_bson_size

POLICY_SCHEMA_VERSION = "phase3-ads-policy-20261015.1"
POLICY_VERSION = "phase3-ads-20261015.1"
VERIFICATION_INTERVAL_SECONDS = 300
KST = timezone(timedelta(hours=9))


def configured_budget(ad):
    return (
        isinstance(ad.get("budget_version"), str)
        and bool(ad["budget_version"].strip())
        and all(
            isinstance(ad.get(name), int) and not isinstance(ad[name], bool) and ad[name] > 0
            for name in ("daily_budget_tokens", "total_budget_tokens")
        )
    )


def budget_occurrence_eligible(repository, ad, occurred_at):
    """발생일/당시 예산 버전의 최초 소진 확인 시각 전 보고만 검사 대상으로 둡니다."""
    if not configured_budget(ad):
        return False
    occurred_at = utc_datetime(occurred_at)
    try:
        day = occurred_at.astimezone(KST).date().isoformat()
    except OverflowError:
        return False
    ad_id = ad.get("_id", ad.get("ad_id"))
    version = ad["budget_version"]
    daily = repository.get_budget_state(ad_id, version, day)
    # 자정의 날짜 전환은 새 광고 종료가 아닙니다. 최근 검증 자료의 전체 한도는 이어집니다.
    if daily is None and repository.latest_budget_state(ad_id, version) is None:
        return False
    cutoffs = [repository.total_budget_cutoff(ad_id, version)]
    if daily is not None:
        cutoffs.append(daily["daily_blocked_at"])
    return all(value is None or occurred_at < utc_datetime(value) for value in cutoffs)


class AdsBudgetService:
    def __init__(self, repository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self):
        return utc_datetime(self.clock())

    def _stop_log(self, state):
        event_id = f"ads-budget:{state['_id']}:first-stop"
        payload = {
            "log_event_id": event_id,
            "source_domain": "ADS",
            "source_event_id": state["_id"],
            "schema_version": POLICY_SCHEMA_VERSION,
            "ads_policy_version": POLICY_VERSION,
            "ad_id": state["ad_id"],
            "budget_version": state["budget_version"],
            "metric_date_kst": state["metric_date_kst"],
            "daily_tokens": state["daily_tokens"],
            "total_tokens": state["total_tokens"],
            "daily_budget_tokens": state["daily_budget_tokens"],
            "total_budget_tokens": state["total_budget_tokens"],
            "daily_blocked_at": utc_string(state["daily_blocked_at"])
            if state["daily_blocked_at"] is not None
            else None,
            "total_blocked_at": utc_string(state["total_blocked_at"])
            if state["total_blocked_at"] is not None
            else None,
            "processed_at": utc_string(state["verified_at"]),
            "result": "BUDGET_EXHAUSTED",
            "is_test": state["is_test"],
        }
        return {
            "log_event_id": event_id,
            "payload": payload,
            "payload_hash": canonical_hash(payload),
            "status": "PENDING",
            "attempt_count": 0,
            "next_retry_at": None,
            "last_error": None,
            "sent_at": None,
        }

    def _refresh(self, repository, ad_id):
        ad = repository.get_ad(ad_id)
        if ad is None:
            return {"ads_checked": 0, "blocked": 0, "metrics_rows": 0}
        repository.lock_ad(ad)
        rows = repository.usage_rows(ad_id)
        verified_at = self._now()
        day = verified_at.astimezone(KST).date().isoformat()
        metric_rows = deepcopy(rows)
        if not any(
            row["metric_date_kst"] == day and row["placement"] == ad["placement"] for row in rows
        ):
            metric_rows.append(
                {
                    "metric_date_kst": day,
                    "placement": ad["placement"],
                    "impressions": 0,
                    "clicks": 0,
                    "estimated_tokens": 0,
                }
            )
        repository.replace_daily_metrics(ad_id, metric_rows, verified_at)
        counts = {"ads_checked": 1, "blocked": 0, "metrics_rows": len(metric_rows)}
        if not configured_budget(ad):
            return counts
        previous = repository.get_budget_state(ad_id, ad["budget_version"], day)
        total_cutoff = repository.total_budget_cutoff(ad_id, ad["budget_version"])
        daily_tokens = sum(row["estimated_tokens"] for row in rows if row["metric_date_kst"] == day)
        total_tokens = sum(row["estimated_tokens"] for row in rows)
        daily_cutoff = previous["daily_blocked_at"] if previous is not None else None
        was_blocked = daily_cutoff is not None or total_cutoff is not None
        if daily_cutoff is None and daily_tokens >= ad["daily_budget_tokens"]:
            daily_cutoff = verified_at
        if total_cutoff is None and total_tokens >= ad["total_budget_tokens"]:
            total_cutoff = verified_at
        revision = previous["revision"] if previous is not None else None
        state = {
            "_id": repository.budget_state_id(ad_id, ad["budget_version"], day),
            "schema_version": POLICY_SCHEMA_VERSION,
            "is_test": repository.is_test,
            "ad_id": ad_id,
            "budget_version": ad["budget_version"],
            "metric_date_kst": day,
            "daily_budget_tokens": ad["daily_budget_tokens"],
            "total_budget_tokens": ad["total_budget_tokens"],
            "daily_tokens": daily_tokens,
            "total_tokens": total_tokens,
            "verified_at": verified_at,
            "created_at": previous["created_at"] if previous is not None else verified_at,
            "revision": (revision or 0) + 1,
            "daily_blocked_at": daily_cutoff,
            "total_blocked_at": total_cutoff,
            "log_relay": deepcopy(previous["log_relay"]) if previous is not None else None,
        }
        blocked = daily_cutoff is not None or total_cutoff is not None
        if blocked and state["log_relay"] is None:
            state["log_relay"] = self._stop_log(state)
        validate_bson_size(state)
        repository.save_budget_state(state, revision)
        if total_cutoff is not None:
            cutoff = min(total_cutoff, daily_cutoff) if daily_cutoff is not None else total_cutoff
            until, scope = None, "TOTAL"
        elif daily_cutoff is not None:
            local = verified_at.astimezone(KST)
            until = utc_datetime(
                local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            )
            cutoff, scope = daily_cutoff, "DAILY"
        else:
            until, cutoff, scope = None, None, None
        annotation = {
            **deepcopy(ad),
            "budget_blocked_at": cutoff,
            "budget_blocked_until": until,
            "budget_blocked_scope": scope,
            "budget_blocked_version": ad["budget_version"],
        }
        # 자동 조회 판정만 저장합니다. 관리자가 쓴 기간/paused/수정 버전/신원은 바꾸지 않습니다.
        if not repository.replace_ad(ad_id, ad["version"], annotation):
            raise DatabaseUnavailable("광고 예산 검증과 상태 저장 결과를 확인할 수 없습니다.")
        counts["blocked"] = int(blocked and not was_blocked)
        return counts

    def run_once(self):
        """각 광고의 지표와 소진 확인을 같은 트랜잭션으로 갱신합니다."""
        counts = {"ads_checked": 0, "blocked": 0, "metrics_rows": 0}
        for ad in self.repository.list_policy_ads():
            result = self.repository.run(lambda repository: self._refresh(repository, ad["_id"]))
            for name, value in result.items():
                counts[name] += value
        return counts
