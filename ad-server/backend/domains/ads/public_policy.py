"""미정 운영 정책을 추측하지 않고 서버가 명시한 구현만 연결합니다."""

from dataclasses import dataclass
from typing import Callable

from .errors import DomainError


@dataclass(frozen=True, slots=True)
class AdsPublicPolicy:
    version: str
    delivery_ttl_seconds: int
    budget_eligible: Callable
    open_delivery_eligible: Callable
    occurrence_eligible: Callable
    split_deadlines: bool = False
    cap_at_midnight: bool = False
    check_budget_history: bool = False

    def __post_init__(self):
        if (
            not isinstance(self.version, str)
            or not self.version.strip()
            or type(self.delivery_ttl_seconds) is not int
            or self.delivery_ttl_seconds <= 0
            or type(self.split_deadlines) is not bool
            or type(self.cap_at_midnight) is not bool
            or type(self.check_budget_history) is not bool
            or (self.cap_at_midnight and not self.split_deadlines)
            or not all(
                callable(getattr(self, field))
                for field in ("budget_eligible", "open_delivery_eligible", "occurrence_eligible")
            )
        ):
            raise DomainError(
                "ADS_POLICY_UNAVAILABLE", "명시적인 광고 운영 정책이 필요합니다.", 503
            )
