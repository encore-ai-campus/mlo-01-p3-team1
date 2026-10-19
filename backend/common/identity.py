import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user
from django.utils import timezone
from backend.recommendation.errors import require
from .models import Guest
from .admin_roles import permitted


def raw_request(request):
    return getattr(request, '_request', request)


def guest(request, bootstrap=False):
    request = raw_request(request)
    cached = getattr(request, '_common_guest', None)
    if cached is not None:
        return cached
    token = request.COOKIES.get(settings.GUEST_COOKIE_NAME, '')
    found = None
    if token and len(token) <= 200:
        found = Guest.objects.filter(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                     active=True, expires_at__gt=timezone.now()).first()
    if found is None and bootstrap:
        require(settings.GUEST_TTL_SECONDS > 0, 'POLICY_NOT_READY', '익명 문맥 만료 설정이 필요합니다.', 503)
        token = secrets.token_urlsafe(32)
        found = Guest.objects.create(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                     expires_at=timezone.now()+timedelta(seconds=settings.GUEST_TTL_SECONDS))
        request._new_guest_token = token
    request._common_guest = found
    return found


def owner(request):
    found = guest(request, bootstrap=True)
    require(found is not None, 'GUEST_REQUIRED', '방문자 문맥을 확인해 주세요.', 401)
    return found.pk


def admin(request, permission=None):
    user = get_user(raw_request(request))
    require(user.is_authenticated and user.is_active, 'AUTH_REQUIRED', '관리자 로그인이 필요합니다.', 401)
    require(user.is_staff, 'FORBIDDEN', '관리자 권한이 없습니다.', 403)
    if permission:
        require(permitted(user, permission), 'FORBIDDEN', '이 기능의 권한이 없습니다.', 403)
    return user


class GuestCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        token = getattr(request, '_new_guest_token', None)
        if token:
            response.set_cookie(settings.GUEST_COOKIE_NAME, token, max_age=settings.GUEST_TTL_SECONDS,
                                secure=not settings.LOCAL_DEMO, httponly=True, samesite='Lax')
        return response
