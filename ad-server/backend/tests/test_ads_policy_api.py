"""공개 운영 provider부터 CSRF·관리 조회까지 연결하는 HTTP 시험. 실제 사용자 DB는 아닙니다."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.middleware.csrf import get_token
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.test import APIClient

from domains.ads.budget_service import AdsBudgetService
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService
from domains.ads.validation import utc_string
from tests.policy_fixtures import MemoryPolicyRepository
from tests.test_ads_domain import image_bytes


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    ADS_IS_TEST=False,
    ADS_GUEST_CONTEXT_PROVIDER="tests.test_ads_public_api.finalized_guest",
    ADS_PUBLIC_POLICY_PROVIDER="domains.ads.runtime_policy.get_public_policy",
    ADS_DELIVERY_SIGNING_KEY="policy-http-fixture-key",
    ADS_PUBLIC_BASE_URL="https://ads.example.test",
    ADS_ADMIN_AUTHORIZER="tests.test_ads_api.allowed_admin",
)
class AdsPolicyApiTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 5, tzinfo=UTC)
        self.origin = self.now
        self.repository = MemoryPolicyRepository(is_test=False)
        manager = AdsService(self.repository, clock=lambda: self.now, is_test=False)
        actor = {"identity_source": "common-auth", "account_id": "http-fixture-admin"}
        asset = manager.upload_asset(
            image_bytes(), actor=actor, idempotency_key="asset", request_id="asset"
        ).body
        manager.create_ad(
            {
                "title": "정책 HTTP 테스트",
                "asset_id": asset["asset_id"],
                "link_url": "https://example.test/cafe",
                "placement": "top",
                "starts_at": self.now,
                "ends_at": self.now + timedelta(hours=1),
                "priority": 1,
                "daily_budget_tokens": 8,
                "total_budget_tokens": 1000,
            },
            actor=actor,
            idempotency_key="create",
            request_id="create",
        )
        self.batch = AdsBudgetService(self.repository, clock=lambda: self.now)
        self.batch.run_once()
        self.client = APIClient(enforce_csrf_checks=True)
        request = RequestFactory().get("/", HTTP_HOST="testserver")
        token = get_token(request)
        self.client.cookies[settings.CSRF_COOKIE_NAME] = request.META["CSRF_COOKIE"]
        self.headers = {"HTTP_X_CSRFTOKEN": token, "HTTP_ORIGIN": "http://testserver"}
        patches = (
            patch("api.ads_public.get_ads_policy_repository", return_value=self.repository),
            patch(
                "api.ads_public.AdsPublicService",
                side_effect=lambda repository, **kwargs: AdsPublicService(
                    repository, clock=lambda: self.now, **kwargs
                ),
            ),
        )
        for mocked in patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def issue(self):
        response = self.client.get("/api/ads", {"placement": "top"})
        self.assertEqual(response.status_code, 200)
        return response.json()["ad"]

    def report(self, ad, kind, occurred_at=None, event_id=None):
        return self.client.post(
            "/api/ad-events",
            {
                "event_id": event_id or str(uuid4()),
                "delivery_id": ad["delivery_id"],
                "event_type": kind,
                "occurred_at": utc_string(occurred_at or self.now),
            },
            format="json",
            HTTP_X_AD_DELIVERY_TOKEN=ad["delivery_token"],
            **self.headers,
        )

    def test_runtime_http_hides_verified_exhaustion_and_replays_first_response(self):
        ad = self.issue()
        event_id = str(uuid4())
        original = self.report(ad, "VIEWABLE_IMPRESSION", event_id=event_id)
        self.assertTrue(original.json()["counted"])
        self.now = self.origin + timedelta(seconds=300)
        self.batch.run_once()
        self.assertIsNone(self.issue())
        replay = self.report(ad, "VIEWABLE_IMPRESSION", occurred_at=self.origin, event_id=event_id)
        self.assertEqual(replay.json(), original.json())
        excluded = self.report(ad, "CLICK")
        self.assertEqual(excluded.json()["result"], "DELIVERY_INVALID")
        accepted = self.report(ad, "CLICK", occurred_at=self.now - timedelta(milliseconds=1))
        self.assertEqual(accepted.json()["result"], "COUNTED")
        self.assertEqual(accepted.json()["ads_policy_version"], "phase3-ads-20261015.1")

    def test_admin_summary_returns_materialized_metrics_without_recalculating_source(self):
        ad = self.issue()
        self.report(ad, "VIEWABLE_IMPRESSION")
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        self.repository.summary = lambda **kwargs: {
            "ENDED": 1,
            "ACTIVE": 0,
            "STOPPED": 0,
            "RESERVED": 0,
        }
        with patch("api.ads.get_ads_repository", return_value=self.repository):
            response = self.client.get("/api/admin/ads/summary")
        self.assertEqual(response.status_code, 200)
        metrics = response.json()["measurement"]
        self.assertEqual(metrics["status"], "READY")
        self.assertEqual(metrics["impressions"], 1)
        self.assertEqual(metrics["estimated_tokens"], 8)
        self.assertEqual(metrics["aggregation_interval_seconds"], 300)
        self.assertIsNotNone(metrics["as_of"])
