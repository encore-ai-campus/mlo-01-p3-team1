"""광고에 필요한 익명 문맥과 미확정 운영 정책의 서버 연결 경계입니다."""

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string
from domains.ads.public_policy import AdsPublicPolicy

from domains.ads.errors import DomainError


@dataclass(frozen=True)
class PublicGuestContext:
    owner_guest_id: str | None
    measurement_available: bool
    response_finalizer: Callable | None = None


def resolve_guest(request, *, bootstrap: bool) -> PublicGuestContext:
    """쿠키/문맥은 공통 서버 어댑터가 확인하며 클라이언트 ID 헤더를 읽지 않습니다."""
    path = settings.ADS_GUEST_CONTEXT_PROVIDER
    try:
        if not path:
            raise ValueError
        context = import_string(path)(request._request, bootstrap=bootstrap)
        if not isinstance(context, PublicGuestContext):
            raise ValueError
        if type(context.measurement_available) is not bool:
            raise ValueError
        if context.owner_guest_id is not None and (
            not isinstance(context.owner_guest_id, str) or not context.owner_guest_id.strip()
        ):
            raise ValueError
        if context.measurement_available and context.owner_guest_id is None:
            raise ValueError
        if context.response_finalizer is not None and not callable(context.response_finalizer):
            raise ValueError
    except Exception:
        raise DomainError(
            "GUEST_UNAVAILABLE", "공유 방문자 문맥을 확인할 수 없습니다.", 503
        ) from None
    return context


def load_public_policy() -> AdsPublicPolicy:
    """수명·예산·소재 수정 정책에 기본 운영값을 만들어 넣지 않습니다."""
    path = settings.ADS_PUBLIC_POLICY_PROVIDER
    try:
        if not path:
            raise ValueError
        policy = import_string(path)()
        if not isinstance(policy, AdsPublicPolicy):
            raise ValueError
    except Exception:
        raise DomainError(
            "ADS_POLICY_UNAVAILABLE", "공개 광고 운영 정책이 연결되지 않았습니다.", 503
        ) from None
    return policy
