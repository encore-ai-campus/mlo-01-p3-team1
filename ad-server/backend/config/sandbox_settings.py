"""공유 .env/계정/DB를 읽지 않는 로컬 광고 확인 도구 전용 설정입니다."""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IS_ADS_SANDBOX = True
DEBUG = False
SECRET_KEY = secrets.token_urlsafe(48)
ADS_SANDBOX_ACCESS_TOKEN = secrets.token_urlsafe(32)
ADS_SANDBOX_INSTANCE_ID = secrets.token_hex(16)
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "drf_spectacular",
    "domains.ads.apps.AdsConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "api.ads_sandbox.SandboxMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
ROOT_URLCONF = "config.sandbox_urls"
DATABASES = {"default": {"ENGINE": "django.db.backends.dummy"}}
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {},
    }
]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CSRF_COOKIE_NAME = "ads_sandbox_csrf"
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_FAILURE_VIEW = "api.ads_sandbox.csrf_failure"
SESSION_COOKIE_NAME = "ads_sandbox_unused"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
ADS_MONGODB_URI = os.environ.get(
    "ADS_SANDBOX_MONGODB_URI",
    "mongodb://127.0.0.1:27019/?replicaSet=ads-rs&directConnection=true",
)
ADS_MONGODB_DATABASE = "ads_sandbox_dev"
ADS_IS_TEST = True
ADS_ADMIN_AUTHORIZER = "api.ads_sandbox.sandbox_admin"
ADS_GUEST_CONTEXT_PROVIDER = "api.ads_sandbox.sandbox_guest"
ADS_PUBLIC_POLICY_PROVIDER = "domains.ads.runtime_policy.get_public_policy"
ADS_DELIVERY_SIGNING_KEY = secrets.token_urlsafe(48)
ADS_PUBLIC_BASE_URL = "https://127.0.0.1:8001"
ADS_LOG_SINK = ""
ADS_API_CONTRACT_VERSION = ""
