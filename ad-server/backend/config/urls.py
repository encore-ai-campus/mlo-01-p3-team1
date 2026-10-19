from django.conf import settings
from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from api.ads import (
    AdAssetReadView,
    AdAssetUploadView,
    AdPreviewView,
    AdsCollectionView,
    AdsSummaryView,
    AdStopView,
    AdUpdateView,
)
from api.ads_public import PublicAdEventsView, PublicAdImageView, PublicAdsView
from api.health import HealthView

urlpatterns = [
    path("api/health", HealthView.as_view(), name="health"),
    path("api/ads", PublicAdsView.as_view(), name="ads-public"),
    path("api/ad-events", PublicAdEventsView.as_view(), name="ad-events-public"),
    path(
        "api/ad-deliveries/<str:delivery_id>/image",
        PublicAdImageView.as_view(),
        name="ad-delivery-image",
    ),
    path("api/admin/ads", AdsCollectionView.as_view(), name="ads-management"),
    path("api/admin/ads/summary", AdsSummaryView.as_view(), name="ads-summary"),
    path("api/admin/ads/preview", AdPreviewView.as_view(), name="ads-preview"),
    path("api/admin/ads/<str:ad_id>/stop", AdStopView.as_view(), name="ads-stop"),
    path("api/admin/ads/<str:ad_id>", AdUpdateView.as_view(), name="ads-update"),
    path("api/admin/ad-assets", AdAssetUploadView.as_view(), name="ad-asset-upload"),
    path("api/admin/ad-assets/<str:asset_id>", AdAssetReadView.as_view(), name="ad-asset-read"),
]

if settings.DEBUG:
    urlpatterns.append(path("api/schema", SpectacularAPIView.as_view(), name="schema"))
