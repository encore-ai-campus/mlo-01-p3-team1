import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or (not DEBUG and SECRET_KEY == "change-me-local-only"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY를 ad-server/backend/.env에 설정하세요.")

ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if value.strip()
]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "domains.ads.apps.AdsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "cafe_common_dev"),
        "USER": os.environ.get("POSTGRES_USER", "cafe_app"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}
DATABASES['default']['OPTIONS'].update({key:os.environ[name] for key,name in
    [('sslmode','POSTGRES_SSLMODE'),('sslrootcert','POSTGRES_SSLROOTCERT')] if os.environ.get(name)})
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "광고 API",
    "DESCRIPTION": (
        "광고 관리·공개 배달·측정 연결. 광고 로그는 MongoDB에 저장합니다. 공유 ADMIN/guest 인증은 "
        "외부 연결입니다. 공개 운영 정책은 명시 서버 어댑터가 제공하며 미연결 시 503입니다."
    ),
    "VERSION": "0.1.0",
    "COMPONENT_SPLIT_REQUEST": True,
}
ADS_MONGODB_URI = os.environ.get("ADS_MONGODB_URI", "")
ADS_MONGODB_DATABASE = os.environ.get("ADS_MONGODB_DATABASE", "advertising_dev")
ADS_IS_TEST = os.environ.get("ADS_IS_TEST", "1" if DEBUG else "0") == "1"
ADS_ADMIN_AUTHORIZER = os.environ.get("ADS_ADMIN_AUTHORIZER", "api.common_bridge.authorize_admin")
# 공통 계약의 이벤트 버전 불일치는 이 설정으로 임의 통합하지 않습니다.
ADS_API_CONTRACT_VERSION = os.environ.get("ADS_API_CONTRACT_VERSION", "")
# 미확정 수명·소재 변경·예산을 환경 기본값으로 확정하지 않습니다.
ADS_GUEST_CONTEXT_PROVIDER = os.environ.get("ADS_GUEST_CONTEXT_PROVIDER", "api.common_bridge.resolve_guest")
ADS_COMMON_API_URL = os.environ.get("ADS_COMMON_API_URL", "")
ADS_INTERNAL_SECRET = os.environ.get("ADS_INTERNAL_SECRET", "")
ADS_PUBLIC_POLICY_PROVIDER = os.environ.get(
    "ADS_PUBLIC_POLICY_PROVIDER", "domains.ads.runtime_policy.get_public_policy"
)
ADS_DELIVERY_SIGNING_KEY = os.environ.get("ADS_DELIVERY_SIGNING_KEY", "")
ADS_PUBLIC_BASE_URL = os.environ.get("ADS_PUBLIC_BASE_URL", "")
