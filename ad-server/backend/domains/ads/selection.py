"""광고 공개 연결 전의 순수 선정 규칙입니다. 저장소나 delivery를 변경하지 않습니다.

소재·예산·환경 판정은 서버가 공급한 검증 결과만 받습니다. 실제 공개 제공에는
동일 delivery 재확인, 요청 멱등, MongoDB 원자적 커서/배달 저장을 별도로 연결해야 합니다.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .errors import ValidationError
from .validation import utc_datetime

PLACEMENTS = frozenset({"top", "bottom"})
DISPLAY_MAX_AGE = timedelta(seconds=3)


def _validate_placement(value):
    if not isinstance(value, str) or value not in PLACEMENTS:
        raise ValidationError(fields={"placement": "top 또는 bottom이 필요합니다."})


def _validate_id(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(fields={field: "비어 있지 않은 문자열이 필요합니다."})


def _validate_flag(value, field):
    if type(value) is not bool:
        raise ValidationError(fields={field: "서버가 판정한 명시적 bool 값이 필요합니다."})


@dataclass(frozen=True, slots=True)
class AdCandidate:
    """서버가 검증한 선정 입력입니다. 미확인 예산에 기본 허용값을 부여하지 않습니다."""

    ad_id: str
    placement: str
    starts_at: datetime
    ends_at: datetime
    priority: int
    paused: bool
    asset_available: bool
    budget_eligible: bool
    is_test: bool

    def __post_init__(self):
        _validate_id(self.ad_id, "ad_id")
        _validate_placement(self.placement)
        if (
            not isinstance(self.priority, int)
            or isinstance(self.priority, bool)
            or not -(2**63) <= self.priority < 2**63
        ):
            raise ValidationError(fields={"priority": "BSON int64 범위의 정수가 필요합니다."})
        for field in ("paused", "asset_available", "budget_eligible", "is_test"):
            _validate_flag(getattr(self, field), field)
        for field in ("starts_at", "ends_at"):
            object.__setattr__(self, field, utc_datetime(getattr(self, field)))
        if self.starts_at >= self.ends_at:
            raise ValidationError(fields={"ends_at": "시작 시각보다 이후여야 합니다."})


@dataclass(frozen=True, slots=True)
class RotationCursor:
    """광고 위치별 마지막 선정 ID입니다. 외부 저장·원자적 갱신은 호출자 책임입니다."""

    placement: str
    last_ad_id: str | None = None

    def __post_init__(self):
        _validate_placement(self.placement)
        if self.last_ad_id is not None:
            _validate_id(self.last_ad_id, "last_ad_id")


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    """후보와 적용할 다음 커서를 반환하며 현재 커서를 직접 바꾸지 않습니다."""

    selected: AdCandidate | None
    next_cursor: RotationCursor
    cursor_changed: bool


def select_ad(
    candidates: Iterable[AdCandidate],
    *,
    placement: str,
    now: datetime,
    cursor: RotationCursor,
    is_test: bool,
    advance_cursor: bool = True,
) -> SelectionDecision:
    """적격 최고 우선순위에서 ID 코드포인트 순으로 후속 광고를 고릅니다.

    기간은 [starts_at, ends_at)이며 위치별 커서를 사용합니다. last_ad_id가 후보에서
    제거되어도 그 ID보다 큰 첫 후보를 선택하고, 없으면 첫 ID로 순환합니다.
    advance_cursor=True는 새 delivery용 결정에만 사용해야 합니다. False는 순수 계산에
    커서 이동을 제안하지 않으며, 기존 delivery와 같은 광고임을 보장하는 재확인 API나
    공개 미리보기를 구현하지 않습니다. 실제 배달·중복 요청의 원자성은 후속 범위입니다.
    """
    _validate_placement(placement)
    _validate_flag(is_test, "is_test")
    _validate_flag(advance_cursor, "advance_cursor")
    evaluated_at = utc_datetime(now)
    if not isinstance(cursor, RotationCursor) or cursor.placement != placement:
        raise ValidationError(fields={"cursor": "요청 위치와 같은 위치의 커서가 필요합니다."})
    try:
        items = tuple(candidates)
    except TypeError as exc:
        raise ValidationError(fields={"candidates": "AdCandidate 목록이 필요합니다."}) from exc
    seen_ids = set()
    eligible = []
    for candidate in items:
        if not isinstance(candidate, AdCandidate):
            raise ValidationError(fields={"candidates": "AdCandidate 목록이 필요합니다."})
        if candidate.ad_id in seen_ids:
            raise ValidationError(fields={"ad_id": "중복 광고 ID는 허용하지 않습니다."})
        seen_ids.add(candidate.ad_id)
        if (
            candidate.placement == placement
            and candidate.starts_at <= evaluated_at < candidate.ends_at
            and not candidate.paused
            and candidate.asset_available
            and candidate.budget_eligible
            and candidate.is_test == is_test
        ):
            eligible.append(candidate)
    if not eligible:
        return SelectionDecision(None, cursor, False)
    highest_priority = max(candidate.priority for candidate in eligible)
    leaders = sorted(
        (candidate for candidate in eligible if candidate.priority == highest_priority),
        key=lambda candidate: candidate.ad_id,
    )
    selected = next(
        (
            candidate
            for candidate in leaders
            if cursor.last_ad_id is None or candidate.ad_id > cursor.last_ad_id
        ),
        leaders[0],
    )
    next_cursor = RotationCursor(placement, selected.ad_id) if advance_cursor else cursor
    return SelectionDecision(selected, next_cursor, next_cursor != cursor)


def display_valid_until(
    evaluated_at: datetime,
    ends_at: datetime,
    *,
    event_expires_at: datetime,
) -> datetime | None:
    """확인+3초·광고 종료·명시 이벤트 만료 중 가장 이른 표시 상한을 계산합니다.

    종료/만료된 경우 None이며 이벤트 TTL은 임의로 정하지 않습니다. 순수 시각 계산이므로
    실제 중단 후 3초 안의 브라우저 제거·서버 재확인·네트워크 지연 처리를 보장하지 않습니다.
    """
    evaluated_at = utc_datetime(evaluated_at)
    boundary = min(utc_datetime(ends_at), utc_datetime(event_expires_at))
    if boundary <= evaluated_at:
        return None
    # datetime.max 부근에서도 +3초 계산의 overflow 없이 같은 최소값을 구합니다.
    if boundary - evaluated_at <= DISPLAY_MAX_AGE:
        return boundary
    return evaluated_at + DISPLAY_MAX_AGE
