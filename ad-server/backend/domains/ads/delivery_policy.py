"""채택한 배달 수명·소재 자격의 순수 규칙. 저장·화면·예산은 변경하지 않습니다."""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from .errors import ValidationError
from .validation import utc_datetime

DELIVERY_TTL_SECONDS = 1800
REPORT_DELAY_SECONDS = 300
KST = timezone(timedelta(hours=9))


def delivery_deadlines(
    issued_at, ends_at, ttl_seconds=DELIVERY_TTL_SECONDS, *, cap_at_midnight=False
) -> tuple[datetime, datetime]:
    """30분·광고 종료 중 이른 표시 마감과 보고 마감을 반환합니다.

    보고 마감은 표시 마감+300초이며, 표시 마감 이후 새 발생을 허용하지 않습니다.
    호출자는 발생 구간과 실제 수신 지연을 별도로 검사해야 합니다. 이 함수는 광고의
    ends_at을 바꾸거나 30분마다 캠페인을 종료하지 않습니다.
    일일 경계는 미확정이므로 KST 자정 단축은 명시적으로 켠 경우에만 적용합니다.
    """
    issued_at = utc_datetime(issued_at)
    ends_at = utc_datetime(ends_at)
    if type(ttl_seconds) is not int or ttl_seconds <= 0:
        raise ValidationError(fields={"ttl_seconds": "양의 정수 초가 필요합니다."})
    if type(cap_at_midnight) is not bool:
        raise ValidationError(fields={"cap_at_midnight": "명시적인 bool이 필요합니다."})
    if ends_at <= issued_at:
        raise ValidationError(fields={"ends_at": "발급 시각보다 이후여야 합니다."})
    try:
        display_expires_at = min(issued_at + timedelta(seconds=ttl_seconds), ends_at)
        if cap_at_midnight:
            local = issued_at.astimezone(KST)
            next_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            display_expires_at = min(display_expires_at, utc_datetime(next_midnight))
        report_expires_at = display_expires_at + timedelta(seconds=REPORT_DELAY_SECONDS)
    except (OverflowError, ValueError):
        raise ValidationError(
            fields={"delivery_deadlines": "배달·보고 마감이 표현 가능한 시각 범위를 벗어났습니다."}
        ) from None
    return display_expires_at, report_expires_at


def _same_creative(delivery, ad):
    if not isinstance(delivery, Mapping) or not isinstance(ad, Mapping):
        return False
    for field in ("creative_version", "placement"):
        value = delivery.get(field)
        if not isinstance(value, str) or not value.strip() or value != ad.get(field):
            return False
    return True


def open_delivery_eligible(delivery, current_ad, now):
    """현재 소재·위치가 같은지 검사합니다. 게시 상태·기간·예산은 호출자 책임입니다."""
    return _same_creative(delivery, current_ad)


def occurrence_eligible(delivery, historical_ad, occurred_at):
    """발생 당시 소재·위치를 검사하여 수정 전 발생을 현재 소재로 덮지 않습니다."""
    return _same_creative(delivery, historical_ad)
