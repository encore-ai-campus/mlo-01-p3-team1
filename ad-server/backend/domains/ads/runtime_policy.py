"""검증 배치가 저장한 예산 상태와 채택한 배달·소재 정책을 공개 경로에 연결합니다."""

from collections.abc import Mapping
from datetime import timedelta

from .delivery_policy import KST, occurrence_eligible, open_delivery_eligible
from .errors import DomainError, ValidationError
from .public_policy import AdsPublicPolicy
from .validation import utc_datetime

BUDGET_VERIFICATION_MAX_AGE_SECONDS = 300


def _unavailable():
    return DomainError(
        "ADS_POLICY_UNAVAILABLE", "광고 예산 검증 자료의 최신 상태를 확인할 수 없습니다.", 503
    )


def budget_eligible(repository, ad, now):
    """최신 검증 상태만 확인하며 요청마다 사용량 합계를 다시 계산하지 않습니다."""
    if not isinstance(ad, Mapping) or any(
        not isinstance(ad.get(field), int) or isinstance(ad[field], bool) or ad[field] <= 0
        for field in ("daily_budget_tokens", "total_budget_tokens")
    ):
        return False
    version = ad.get("budget_version")
    if not isinstance(version, str) or not version.strip():
        return False
    ad_id = ad.get("_id", ad.get("ad_id"))
    if not isinstance(ad_id, str) or not ad_id.strip():
        return False
    try:
        now = utc_datetime(now)
        metric_date = now.astimezone(KST).date().isoformat()
    except (ValidationError, OverflowError):
        raise _unavailable() from None
    state = repository.get_budget_state(ad_id, version, metric_date)
    today_state = state
    if state is None:
        state = repository.latest_budget_state(ad_id, version)
        if state is None:
            return False
    if not isinstance(state, Mapping):
        raise _unavailable()
    try:
        verified_at = utc_datetime(state.get("verified_at"))
    except ValidationError:
        raise _unavailable() from None
    if verified_at > now or now - verified_at > timedelta(
        seconds=BUDGET_VERIFICATION_MAX_AGE_SECONDS
    ):
        raise _unavailable()
    if today_state is not None and state.get("daily_blocked_at") is not None:
        return False
    return repository.total_budget_cutoff(ad_id, version) is None


def get_public_policy():
    """미확정 일일 자정 단축은 켜지 않고 공유 guest/서명 설정은 외부에 둡니다."""
    return AdsPublicPolicy(
        version="phase3-ads-20261015.1",
        delivery_ttl_seconds=1800,
        budget_eligible=budget_eligible,
        open_delivery_eligible=open_delivery_eligible,
        occurrence_eligible=occurrence_eligible,
        split_deadlines=True,
        cap_at_midnight=False,
        check_budget_history=True,
    )
