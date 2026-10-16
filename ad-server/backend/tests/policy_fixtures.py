"""광고 정책 통합 시험의 메모리 저장소. 운영 설정이나 실제 MongoDB가 아닙니다."""

from copy import deepcopy
from datetime import date

from domains.ads.delivery_policy import KST
from domains.ads.errors import DatabaseUnavailable, ValidationError
from domains.ads.service import canonical_hash
from domains.ads.validation import utc_datetime
from repositories.ads_mongo import DuplicateMutation
from tests.public_fixtures import MemoryPublicRepository

POLICY_SCHEMA_VERSION = "phase3-ads-policy-20261015.1"
COUNTERS = ("impressions", "clicks", "estimated_tokens")


class MemoryPolicyRepository(MemoryPublicRepository):
    STATE_NAMES = (*MemoryPublicRepository.STATE_NAMES, "budget_states", "metrics")

    def __init__(self, *, is_test=False):
        super().__init__(is_test=is_test)
        self.budget_states = {}
        self.metrics = {}
        self.fail_budget_state = False
        self.fail_metrics = False

    def budget_state_id(self, ad_id, budget_version, metric_date_kst):
        if (
            not isinstance(ad_id, str)
            or not ad_id.strip()
            or not isinstance(budget_version, str)
            or not budget_version.strip()
            or not isinstance(metric_date_kst, str)
        ):
            raise ValidationError("정책 fixture의 참조가 올바르지 않습니다.")
        try:
            if date.fromisoformat(metric_date_kst).isoformat() != metric_date_kst:
                raise ValueError
        except ValueError:
            raise ValidationError("정책 fixture의 날짜가 올바르지 않습니다.") from None
        return canonical_hash([ad_id, budget_version, metric_date_kst, self.is_test])

    def list_policy_ads(self):
        return deepcopy([ad for ad in self.ads.values() if ad["is_test"] is self.is_test])

    def usage_rows(self, ad_id):
        grouped = {}
        for entry in self.usage.values():
            if (
                entry["ad_id"] != ad_id
                or entry["is_test"] is not self.is_test
                or entry["status"] != "ESTIMATED"
            ):
                continue
            key = entry["metric_date_kst"], entry["placement"]
            row = grouped.setdefault(
                key,
                {
                    "metric_date_kst": key[0],
                    "placement": key[1],
                    "impressions": 0,
                    "clicks": 0,
                    "estimated_tokens": 0,
                },
            )
            row["impressions"] += int(entry["event_type"] == "VIEWABLE_IMPRESSION")
            row["clicks"] += int(entry["event_type"] == "CLICK")
            row["estimated_tokens"] += entry["estimated_tokens"]
        return deepcopy([grouped[key] for key in sorted(grouped)])

    def get_budget_state(self, ad_id, budget_version, metric_date_kst):
        identity = self.budget_state_id(ad_id, budget_version, metric_date_kst)
        return deepcopy(self.budget_states.get(identity))

    def latest_budget_state(self, ad_id, budget_version):
        states = [
            state
            for state in self.budget_states.values()
            if state["ad_id"] == ad_id
            and state["budget_version"] == budget_version
            and state["is_test"] is self.is_test
        ]
        return (
            deepcopy(max(states, key=lambda state: (state["verified_at"], state["_id"])))
            if states
            else None
        )

    def total_budget_cutoff(self, ad_id, budget_version):
        cutoffs = [
            state["total_blocked_at"]
            for state in self.budget_states.values()
            if state["ad_id"] == ad_id
            and state["budget_version"] == budget_version
            and state["is_test"] is self.is_test
            and state["total_blocked_at"] is not None
        ]
        return min(cutoffs) if cutoffs else None

    def save_budget_state(self, document, expected_revision):
        if self.fail_budget_state:
            raise DatabaseUnavailable("정책 fixture의 상태 저장 실패")
        identity = self.budget_state_id(
            document.get("ad_id"), document.get("budget_version"), document.get("metric_date_kst")
        )
        if document.get("_id") != identity or document.get("is_test") is not self.is_test:
            raise ValidationError("정책 fixture의 저장 환경/참조가 다릅니다.")
        current = self.budget_states.get(identity)
        actual_revision = current["revision"] if current else None
        if actual_revision != expected_revision:
            raise DuplicateMutation
        if document.get("revision") != (expected_revision or 0) + 1:
            raise ValidationError("정책 fixture의 revision이 다릅니다.")
        self.budget_states[identity] = deepcopy(document)

    def replace_daily_metrics(self, ad_id, rows, as_of):
        if self.fail_metrics:
            raise DatabaseUnavailable("정책 fixture의 집계 저장 실패")
        seen = set()
        for row in rows:
            key = row["metric_date_kst"], row["placement"]
            if key in seen or key[1] not in {"top", "bottom"}:
                raise ValidationError("정책 fixture의 집계가 중복되거나 위치가 다릅니다.")
            seen.add(key)
            identity = canonical_hash([ad_id, key[1], key[0], self.is_test])
            self.metrics[identity] = {
                "_id": identity,
                "schema_version": POLICY_SCHEMA_VERSION,
                "is_test": self.is_test,
                "ad_id": ad_id,
                "placement": key[1],
                "metric_date_kst": key[0],
                **{name: row[name] for name in COUNTERS},
                "as_of": utc_datetime(as_of),
                "source": "ESTIMATED_LEDGER",
            }

    def metrics_summary(self, now, ad_id=None):
        day = utc_datetime(now).astimezone(KST).date().isoformat()
        rows = [
            row
            for row in self.metrics.values()
            if row["is_test"] is self.is_test and (ad_id is None or row["ad_id"] == ad_id)
        ]
        today = [row for row in rows if row["metric_date_kst"] == day]
        ads = [ad for ad in self.list_policy_ads() if ad_id is None or ad["_id"] == ad_id]
        expected = {(ad["_id"], ad["placement"]) for ad in ads}
        covered = {(row["ad_id"], row["placement"]) for row in today} & expected
        complete = bool(today) and covered == expected
        return {
            "metric_date_kst": day,
            "today_valid_impressions": sum(row["impressions"] for row in today) if today else None,
            "today_valid_clicks": sum(row["clicks"] for row in today) if today else None,
            "today_estimated_tokens": sum(row["estimated_tokens"] for row in today)
            if today
            else None,
            "lifetime_valid_impressions": sum(row["impressions"] for row in rows) if rows else None,
            "lifetime_valid_clicks": sum(row["clicks"] for row in rows) if rows else None,
            "lifetime_estimated_tokens": sum(row["estimated_tokens"] for row in rows)
            if rows
            else None,
            "as_of": min(row["as_of"] for row in today) if today else None,
            "aggregation_status": "READY" if complete else ("PARTIAL" if today else "PENDING"),
            "coverage": {"covered": len(covered), "expected": len(expected)},
        }
