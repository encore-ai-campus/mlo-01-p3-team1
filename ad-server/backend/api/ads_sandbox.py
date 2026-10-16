"""loopback·시험 DB 전용 확인 화면. 정식 ADMIN/guest 인증은 변경하지 않습니다."""

import ipaddress
import json
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.exceptions import DisallowedHost
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from api.ads_auth import AdminIdentity
from api.ads_public_auth import PublicGuestContext
from domains.ads import sandbox_runtime
from domains.ads.errors import DomainError

ADMIN_COOKIE = "ads_sandbox_admin"
GUEST_COOKIE = "ads_sandbox_guest"
ADMIN_SALT = "ads-sandbox-admin-v1"
GUEST_SALT = "ads-sandbox-guest-v1"
COOKIE_SECONDS = 8 * 60 * 60
PRESENTATION_DIR = Path(__file__).resolve().parents[1] / "presentation" / "ads"
PRESENTATION_ASSETS = {
    "ads.css": (PRESENTATION_DIR / "ads.css", "text/css"),
    "ads-page.mjs": (PRESENTATION_DIR / "ads-page.mjs", "text/javascript"),
    "ads-api.mjs": (PRESENTATION_DIR / "ads-api.mjs", "text/javascript"),
    "time.mjs": (PRESENTATION_DIR / "time.mjs", "text/javascript"),
    "penguin.png": (
        PRESENTATION_DIR.parents[3] / "docs" / "assets" / "penguin" / "penguin-guide-first.png",
        "image/png",
    ),
}


def presentation_context(request):
    """문구를 요청마다 읽어 총괄 담당자의 수정이 새로고침에 반영되게 합니다."""
    content = json.loads((PRESENTATION_DIR / "content.json").read_text(encoding="utf-8"))
    if not isinstance(content, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in content.items()
    ):
        raise ValueError("광고 presentation 문구는 문자열 키·값이어야 합니다.")
    return {"presentation": content, "csp_nonce": request.csp_nonce}


@require_GET
def presentation_asset(request, name):
    """고정 허용 목록만 제공합니다. 원본 저장소의 임의 파일은 열지 않습니다."""
    asset = PRESENTATION_ASSETS.get(name)
    if asset is None or not asset[0].is_file():
        raise Http404
    return FileResponse(asset[0].open("rb"), content_type=asset[1])


def local_guard(request):
    try:
        sandbox_runtime.require_sandbox()
        remote = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
        host = urlsplit("http://" + request.get_host()).hostname
        return remote.is_loopback and host in {"127.0.0.1", "localhost", "::1"}
    except (DomainError, DisallowedHost, ValueError):
        return False


def _cookie(request, name, salt):
    try:
        return signing.loads(request.COOKIES.get(name, ""), salt=salt, max_age=COOKIE_SECONDS)
    except (signing.BadSignature, TypeError, ValueError):
        return None


def read_admin(request):
    return local_guard(request) and _cookie(request, ADMIN_COOKIE, ADMIN_SALT) == {
        "kind": "ads-sandbox-admin",
        "instance": settings.ADS_SANDBOX_INSTANCE_ID,
    }


def _set_cookie(response, name, value, salt):
    response.set_cookie(
        name,
        signing.dumps(value, salt=salt),
        max_age=COOKIE_SECONDS,
        httponly=True,
        secure=False,
        samesite="Strict",
    )


def sandbox_admin(request, action):
    if not read_admin(request):
        return None
    return AdminIdentity("ads-sandbox-admin", "LOCAL_SANDBOX", "ADMIN", True, True)


def sandbox_guest(request, *, bootstrap):
    if not read_admin(request):
        return PublicGuestContext(None, False)
    guest = _cookie(request, GUEST_COOKIE, GUEST_SALT)
    if isinstance(guest, dict) and guest.get("instance") == settings.ADS_SANDBOX_INSTANCE_ID:
        guest_id = guest.get("guest_id")
        if isinstance(guest_id, str) and len(guest_id) == 32:
            return PublicGuestContext(guest_id, True)
    if not bootstrap:
        return PublicGuestContext(None, False)
    guest = {"instance": settings.ADS_SANDBOX_INSTANCE_ID, "guest_id": uuid4().hex}

    def finalize(response):
        _set_cookie(response, GUEST_COOKIE, guest, GUEST_SALT)

    return PublicGuestContext(guest["guest_id"], True, finalize)


class SandboxMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(18)
        if not local_guard(request):
            response = JsonResponse({"code": "SANDBOX_LOCAL_ONLY"}, status=403)
        elif (
            request.path != "/dev/ads/login"
            and request.path not in {f"/dev/ads/assets/{name}" for name in PRESENTATION_ASSETS}
            and not read_admin(request)
        ):
            response = (
                JsonResponse(
                    {"code": "AUTH_REQUIRED", "message": "로컬 로그인이 필요합니다."}, status=401
                )
                if request.path.startswith("/api/")
                or request.path.endswith(("/status", "/refresh"))
                else redirect("/dev/ads/login")
            )
        else:
            response = self.get_response(request)
        nonce = request.csp_nonce
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; "
            "img-src 'self' blob: data:; connect-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        response["Cache-Control"] = "no-store"
        # no-referrer는 일반 HTML POST의 Origin까지 null로 만들어 CSRF와 충돌합니다.
        # 같은 출처의 로그인/제어는 유지하고 외부 출처로는 Referer를 보내지 않습니다.
        response["Referrer-Policy"] = "same-origin"
        response["X-Frame-Options"] = "DENY"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def csrf_failure(request, reason=""):
    if reason == "CSRF cookie not set.":
        message = "CSRF 쿠키가 없습니다. 브라우저에서 같은 주소를 다시 열어 주세요."
    elif reason.startswith("Origin checking failed"):
        message = "요청 출처가 다릅니다. 127.0.0.1의 같은 포트에서 사용해 주세요."
    else:
        message = "요청 출처 또는 CSRF 검증에 실패했습니다. 로그인 화면을 다시 열어 주세요."
    return JsonResponse({"code": "FORBIDDEN", "message": message}, status=403)


@require_GET
def home(request):
    return redirect("/dev/ads/")


@never_cache
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def login(request):
    error = ""
    if request.method == "POST":
        code = request.POST.get("access_code", "")
        if constant_time_compare(code, settings.ADS_SANDBOX_ACCESS_TOKEN):
            rotate_token(request)
            response = redirect("/dev/ads/")
            _set_cookie(
                response,
                ADMIN_COOKIE,
                {"kind": "ads-sandbox-admin", "instance": settings.ADS_SANDBOX_INSTANCE_ID},
                ADMIN_SALT,
            )
            return response
        error = "접근 코드가 올바르지 않습니다. 실행 시 생성된 access.txt를 확인하세요."
    return render(
        request,
        "ads_sandbox_login.html",
        {"error": error, **presentation_context(request)},
        status=401 if error else 200,
    )


@never_cache
@ensure_csrf_cookie
@require_GET
def dashboard(request):
    return render(request, "ads_sandbox.html", presentation_context(request))


@require_POST
def logout(request):
    response = JsonResponse({"redirect": "/dev/ads/login"})
    response.delete_cookie(ADMIN_COOKIE, samesite="Strict")
    response.delete_cookie(GUEST_COOKIE, samesite="Strict")
    rotate_token(request)
    return response


@require_GET
def status(request):
    return JsonResponse(
        {
            "budget_worker": sandbox_runtime.worker_status(),
            "database": settings.ADS_MONGODB_DATABASE,
            "is_test": settings.ADS_IS_TEST,
            "log_storage": "MONGODB",
        }
    )


@require_POST
def refresh(request):
    try:
        return JsonResponse(sandbox_runtime.refresh_policy())
    except DomainError as exc:
        return JsonResponse({"code": exc.code, "message": exc.message}, status=exc.http_status)
    except Exception:
        return JsonResponse(
            {
                "code": "SANDBOX_REFRESH_FAILED",
                "message": "집계에 실패했습니다. MongoDB 상태를 확인하세요.",
            },
            status=503,
        )
