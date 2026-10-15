"""정식 URLconf에 포함하지 않는 광고 개발 도구 경로입니다."""

from django.urls import path

from api import ads_sandbox
from config.urls import urlpatterns as api_patterns

urlpatterns = [
    path("", ads_sandbox.home),
    path("dev/ads/", ads_sandbox.dashboard, name="ads-sandbox"),
    path("dev/ads/login", ads_sandbox.login, name="ads-sandbox-login"),
    path("dev/ads/logout", ads_sandbox.logout, name="ads-sandbox-logout"),
    path("dev/ads/status", ads_sandbox.status, name="ads-sandbox-status"),
    path("dev/ads/refresh", ads_sandbox.refresh, name="ads-sandbox-refresh"),
    *api_patterns,
]
