from datetime import UTC, datetime, timedelta
from itertools import count
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from django.conf import settings
from django.middleware.csrf import get_token
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.test import APIClient

from api.ads_public_auth import PublicGuestContext
from domains.ads.errors import DatabaseUnavailable, DomainError, NotFound
from domains.ads.measurement import validate_event_input
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService
from tests.public_fixtures import MemoryPublicRepository, fixture_public_policy
from tests.test_ads_domain import image_bytes


def finalized_guest(request, *, bootstrap):
    def finalize(response):
        response.set_cookie("shared_guest_fixture", "server-issued", httponly=True)

    return PublicGuestContext("internal-shared-guest", True, finalize)


def cookieless_guest(request, *, bootstrap):
    return PublicGuestContext(None, False)


def unavailable_guest(request, *, bootstrap):
    raise RuntimeError("secret-guest-provider-error")


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    ADS_GUEST_CONTEXT_PROVIDER="tests.test_ads_public_api.finalized_guest",
    ADS_DELIVERY_SIGNING_KEY="public-api-fixture-signing-key",
    ADS_PUBLIC_BASE_URL="https://ads.example.com",
    ADS_API_CONTRACT_VERSION="",
    ADS_IS_TEST=True,
    CSRF_TRUSTED_ORIGINS=[],
)
class PublicAdsApiTests(SimpleTestCase):
    """DRF·공유 guest 경계·CSRF를 실제 호출하며 DB 원자성은 통합 검사에 위임합니다."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        token_request = RequestFactory().get("/", HTTP_HOST="testserver")
        self.csrf_token = get_token(token_request)
        self.client.cookies[settings.CSRF_COOKIE_NAME] = token_request.META["CSRF_COOKIE"]
        self.headers = {
            "HTTP_X_CSRFTOKEN": self.csrf_token,
            "HTTP_ORIGIN": "http://testserver",
            "HTTP_X_AD_DELIVERY_TOKEN": "server-delivery-proof",
        }
        self.service = Mock()
        self.empty_response = {
            "ad": None,
            "evaluated_at": "2026-10-15T01:00:00Z",
            "valid_until": None,
            "measurement_available": True,
        }
        self.service.provide.return_value = self.empty_response
        self.service.read_image.return_value = (image_bytes(), "image/png")
        self.repository = object()
        self.policy = fixture_public_policy()
        self.repository_patch = patch(
            "api.ads_public.get_public_ads_repository", return_value=self.repository
        )
        self.repository_provider = self.repository_patch.start()
        self.addCleanup(self.repository_patch.stop)
        self.policy_patch = patch("api.ads_public.load_public_policy", return_value=self.policy)
        self.policy_provider = self.policy_patch.start()
        self.addCleanup(self.policy_patch.stop)
        self.service_patch = patch("api.ads_public.AdsPublicService", return_value=self.service)
        self.service_class = self.service_patch.start()
        self.addCleanup(self.service_patch.stop)
        self.event = {
            "event_id": "opaque-event",
            "delivery_id": "opaque-delivery",
            "event_type": "CLICK",
            "occurred_at": "2026-10-15T01:00:00Z",
        }

    def assert_error(self, response, status, code, fields=None):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertEqual(body["request_id"], response["X-Request-ID"])
        self.assertLessEqual(set(body), {"code", "message", "request_id", "details"})
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        if fields is not None:
            self.assertEqual(body["details"]["fields"], fields)

    def test_top_bootstrap_finalizes_guest_cookie_even_without_ad(self):
        provider = Mock(side_effect=finalized_guest)
        with patch("api.ads_public_auth.import_string", return_value=provider):
            response = self.client.get("/api/ads", {"placement": "top"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.empty_response)
        self.assertEqual(response.cookies["shared_guest_fixture"].value, "server-issued")
        self.assertTrue(response.cookies["shared_guest_fixture"]["httponly"])
        self.assertEqual(provider.call_args.kwargs, {"bootstrap": True})
        self.assertFalse(hasattr(provider.call_args.args[0], "_request"))
        self.assertEqual(
            self.service.provide.call_args.kwargs["owner_guest_id"], "internal-shared-guest"
        )
        self.assertTrue(self.service.provide.call_args.kwargs["measurement_available"])

    def test_bottom_reconfirmation_and_event_never_bootstrap_new_guest(self):
        provider = Mock(side_effect=finalized_guest)
        self.service.record_event.return_value = {"result": "COUNTED"}
        with patch("api.ads_public_auth.import_string", return_value=provider):
            self.client.get("/api/ads", {"placement": "bottom"})
            self.client.get(
                "/api/ads",
                {"placement": "top", "delivery_id": "opaque-delivery"},
                **self.headers,
            )
            self.client.post("/api/ad-events", self.event, format="json", **self.headers)
        self.assertEqual(
            [call.kwargs for call in provider.call_args_list],
            [{"bootstrap": False}, {"bootstrap": False}, {"bootstrap": False}],
        )

    def test_factory_uses_only_server_configuration_and_guest_reference(self):
        response = self.client.get(
            "/api/ads",
            {"placement": "top"},
            HTTP_X_OWNER_GUEST_ID="forged-guest",
            HTTP_X_IS_TEST="false",
            HTTP_X_REQUEST_ID="forged-request",
        )
        self.assertEqual(response.status_code, 200)
        self.service_class.assert_called_once_with(
            self.repository,
            policy=self.policy,
            signing_key="public-api-fixture-signing-key",
            public_base_url="https://ads.example.com",
            is_test=True,
        )
        kwargs = self.service.provide.call_args.kwargs
        self.assertEqual(kwargs["owner_guest_id"], "internal-shared-guest")
        self.assertEqual(kwargs["request_id"], response["X-Request-ID"])
        self.assertNotEqual(kwargs["request_id"], "forged-request")

    @override_settings(ADS_GUEST_CONTEXT_PROVIDER="")
    def test_unconnected_guest_fails_closed_before_policy_or_repository(self):
        response = self.client.get("/api/ads", {"placement": "top"})
        self.assert_error(response, 503, "GUEST_UNAVAILABLE")
        self.policy_provider.assert_not_called()
        self.repository_provider.assert_not_called()

    def test_invalid_guest_objects_and_exceptions_are_masked_service_failures(self):
        invalid = (
            {"owner_guest_id": "forged", "measurement_available": True},
            PublicGuestContext("", True),
            PublicGuestContext(1, False),
            PublicGuestContext(None, True),
            PublicGuestContext("server-guest", 1),
            PublicGuestContext("server-guest", True, "not-callable"),
        )
        for context in invalid:
            with (
                self.subTest(context=context),
                patch("api.ads_public_auth.import_string", return_value=Mock(return_value=context)),
            ):
                response = self.client.get("/api/ads", {"placement": "top"})
                self.assert_error(response, 503, "GUEST_UNAVAILABLE")
        with self.settings(
            ADS_GUEST_CONTEXT_PROVIDER="tests.test_ads_public_api.unavailable_guest"
        ):
            response = self.client.get("/api/ads", {"placement": "top"})
        self.assert_error(response, 503, "GUEST_UNAVAILABLE")
        self.assertNotIn("secret-guest-provider-error", response.content.decode())
        self.repository_provider.assert_not_called()

    @override_settings(ADS_GUEST_CONTEXT_PROVIDER="tests.test_ads_public_api.cookieless_guest")
    def test_explicit_cookie_unavailable_context_can_still_request_display(self):
        self.service.provide.return_value = {**self.empty_response, "measurement_available": False}
        response = self.client.get("/api/ads", {"placement": "top"})
        self.assertEqual(response.status_code, 200)
        kwargs = self.service.provide.call_args.kwargs
        self.assertIsNone(kwargs["owner_guest_id"])
        self.assertIs(kwargs["measurement_available"], False)
        self.assertIs(response.json()["measurement_available"], False)

    def test_missing_operational_policy_fails_closed_without_mongo_connection(self):
        self.policy_patch.stop()
        with self.settings(ADS_PUBLIC_POLICY_PROVIDER=""):
            response = self.client.get("/api/ads", {"placement": "top"})
        self.assert_error(response, 503, "ADS_POLICY_UNAVAILABLE")
        self.repository_provider.assert_not_called()

    def test_bad_policy_type_and_provider_exception_are_masked(self):
        self.policy_patch.stop()
        for provider in (
            Mock(return_value={"delivery_ttl_seconds": 300}),
            Mock(side_effect=RuntimeError("secret-policy-error")),
        ):
            with (
                self.subTest(provider=provider),
                self.settings(ADS_PUBLIC_POLICY_PROVIDER="x.y"),
                patch("api.ads_public_auth.import_string", side_effect=[finalized_guest, provider]),
            ):
                response = self.client.get("/api/ads", {"placement": "top"})
            self.assert_error(response, 503, "ADS_POLICY_UNAVAILABLE")
            self.assertNotIn("secret-policy-error", response.content.decode())
        self.repository_provider.assert_not_called()

    def test_query_requires_placement_and_rejects_unknown_or_duplicate_names(self):
        invalid = (
            ({}, ["placement"]),
            ({"placement": ["top", "bottom"]}, ["placement"]),
            ({"placement": "top", "delivery_id": ["one", "two"]}, ["delivery_id"]),
            ({"placement": "top", "owner_guest_id": "forged"}, ["owner_guest_id"]),
            ({"placement": "top", "target_tag_codes": "CAFE"}, ["target_tag_codes"]),
            ({"placement": "top", "delivery_id": ""}, ["delivery_id"]),
        )
        for query, fields in invalid:
            with self.subTest(query=query):
                self.assert_error(
                    self.client.get("/api/ads", query), 422, "VALIDATION_ERROR", fields
                )
        self.service.provide.assert_not_called()

    def test_invalid_placement_uses_shared_option_error(self):
        self.assert_error(
            self.client.get("/api/ads", {"placement": "all"}), 400, "OPTION_INVALID", ["placement"]
        )

    def test_reconfirmation_requires_proof_header_and_passes_opaque_values(self):
        query = {"placement": "top", "delivery_id": "opaque-delivery"}
        self.assert_error(
            self.client.get("/api/ads", query), 422, "VALIDATION_ERROR", ["delivery_token"]
        )
        self.service.provide.assert_not_called()
        response = self.client.get("/api/ads", query, **self.headers)
        self.assertEqual(response.status_code, 200)
        kwargs = self.service.provide.call_args.kwargs
        self.assertEqual(kwargs["delivery_id"], "opaque-delivery")
        self.assertEqual(kwargs["delivery_token"], "server-delivery-proof")

    def test_optional_issue_idempotency_key_is_forwarded_but_blank_rejected(self):
        response = self.client.get("/api/ads", {"placement": "top"}, HTTP_IDEMPOTENCY_KEY="")
        self.assert_error(response, 422, "VALIDATION_ERROR", ["idempotency_key"])
        self.service.provide.assert_not_called()
        response = self.client.get(
            "/api/ads", {"placement": "top"}, HTTP_IDEMPOTENCY_KEY="opaque-issue-key"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.service.provide.call_args.kwargs["idempotency_key"], "opaque-issue-key"
        )

    def test_csrf_and_origin_reject_before_json_parsing_or_context_resolution(self):
        for headers in (
            {"HTTP_ORIGIN": "http://testserver"},
            {**self.headers, "HTTP_ORIGIN": "https://untrusted.example"},
        ):
            with self.subTest(headers=headers):
                response = self.client.generic(
                    "POST", "/api/ad-events", "{", content_type="application/json", **headers
                )
                self.assert_error(response, 403, "FORBIDDEN")
        self.policy_provider.assert_not_called()
        self.repository_provider.assert_not_called()
        self.service.record_event.assert_not_called()

    def test_event_header_required_without_reading_malformed_json(self):
        response = self.client.generic(
            "POST",
            "/api/ad-events",
            "{",
            content_type="application/json",
            **{**self.headers, "HTTP_X_AD_DELIVERY_TOKEN": ""},
        )
        self.assert_error(response, 422, "VALIDATION_ERROR", ["delivery_token"])
        self.service.record_event.assert_not_called()

    def test_event_valid_csrf_malformed_json_uses_common_422(self):
        response = self.client.generic(
            "POST", "/api/ad-events", "{", content_type="application/json", **self.headers
        )
        self.assert_error(response, 422, "VALIDATION_ERROR")
        self.service.record_event.assert_not_called()

    def test_event_query_does_not_accept_server_fields(self):
        response = self.client.post(
            "/api/ad-events?is_test=false", self.event, format="json", **self.headers
        )
        self.assert_error(response, 422, "VALIDATION_ERROR", ["is_test"])
        self.service.record_event.assert_not_called()

    def test_event_forwards_exact_body_and_server_owner_then_returns_original_decision(self):
        decision = {
            **self.event,
            "result": "COUNTED",
            "counted": True,
            "received_at": "2026-10-15T01:00:01Z",
            "processed_at": "2026-10-15T01:00:01Z",
            "ads_policy_version": "phase3-ads-20261014.1",
        }
        self.service.record_event.return_value = decision
        response = self.client.post(
            "/api/ad-events",
            self.event,
            format="json",
            **self.headers,
            HTTP_X_OWNER_GUEST_ID="forged-guest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), decision)
        self.service.record_event.assert_called_once_with(
            self.event,
            owner_guest_id="internal-shared-guest",
            measurement_available=True,
            delivery_token="server-delivery-proof",
            request_id=response["X-Request-ID"],
        )

    def test_strict_event_domain_rejection_preserves_actual_field_names(self):
        self.service.record_event.side_effect = lambda data, **kwargs: validate_event_input(data)
        response = self.client.post(
            "/api/ad-events",
            {**self.event, "is_test": False, "delivery_token": "body-proof"},
            format="json",
            **self.headers,
        )
        self.assert_error(response, 422, "VALIDATION_ERROR", ["delivery_token", "is_test"])

    @override_settings(ADS_GUEST_CONTEXT_PROVIDER="")
    def test_image_capability_returns_original_bytes_without_guest_cookie_or_bootstrap(self):
        response = self.client.get(
            "/api/ad-deliveries/opaque-delivery/image", {"delivery_token": "image-proof"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), image_bytes())
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertNotIn("shared_guest_fixture", response.cookies)
        self.service.read_image.assert_called_once_with(
            "opaque-delivery", delivery_token="image-proof"
        )

    def test_image_requires_one_query_proof_and_rejects_unknown_query(self):
        for query, fields in (
            ({}, ["delivery_token"]),
            ({"delivery_token": ["one", "two"]}, ["delivery_token"]),
            ({"delivery_token": "proof", "asset_id": "asset"}, ["asset_id"]),
        ):
            with self.subTest(query=query):
                response = self.client.get("/api/ad-deliveries/opaque-delivery/image", query)
                self.assert_error(response, 422, "VALIDATION_ERROR", fields)
        self.service.read_image.assert_not_called()

    def test_image_invalid_proof_and_database_failures_use_safe_common_error(self):
        for error, status, code in (
            (NotFound(), 404, "NOT_FOUND"),
            (DatabaseUnavailable(), 503, "DATABASE_UNAVAILABLE"),
        ):
            with self.subTest(code=code):
                self.service.read_image.side_effect = error
                response = self.client.get(
                    "/api/ad-deliveries/opaque-delivery/image", {"delivery_token": "forged-proof"}
                )
                self.assert_error(response, status, code)

    def test_domain_conflict_and_policy_failure_preserve_http_status(self):
        self.service.provide.side_effect = DomainError(
            "IDEMPOTENCY_CONFLICT", "다른 요청입니다.", 409
        )
        self.assert_error(
            self.client.get("/api/ads", {"placement": "top"}), 409, "IDEMPOTENCY_CONFLICT"
        )

    def test_guest_response_finalizer_failure_is_masked(self):
        finalizer = Mock(side_effect=RuntimeError("secret-cookie-error"))
        provider = Mock(return_value=PublicGuestContext("shared-guest", True, finalizer))
        with patch("api.ads_public_auth.import_string", return_value=provider):
            response = self.client.get("/api/ads", {"placement": "top"})
        self.assert_error(response, 503, "GUEST_UNAVAILABLE")
        self.assertNotIn("secret-cookie-error", response.content.decode())

    @override_settings(ADS_API_CONTRACT_VERSION="shared-agreed-version")
    def test_response_headers_apply_contract_only_when_explicitly_configured(self):
        response = self.client.get("/api/ads", {"placement": "top"})
        self.assertEqual(response["X-Contract-Version"], "shared-agreed-version")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("data", response.json())


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    ADS_GUEST_CONTEXT_PROVIDER="tests.test_ads_public_api.finalized_guest",
    ADS_DELIVERY_SIGNING_KEY="public-api-connected-fixture-key",
    ADS_PUBLIC_BASE_URL="https://ads.example.test",
    ADS_IS_TEST=False,
    CSRF_TRUSTED_ORIGINS=[],
)
class PublicAdsConnectedApiTests(SimpleTestCase):
    """실제 공개 서비스까지 연결합니다. 저장소만 메모리 fixture로 대체합니다."""

    def setUp(self):
        self.now = datetime(2026, 10, 15, 14, 59, tzinfo=UTC)
        identifiers = count(1)
        self.identifier = lambda: f"api-connected-{next(identifiers):04d}"
        self.repository = MemoryPublicRepository(is_test=False)
        self.manager = AdsService(
            self.repository, is_test=False, clock=lambda: self.now, id_factory=self.identifier
        )
        self.actor = {"account_id": "shared-admin-fixture", "identity_source": "common-auth"}
        asset = self.manager.upload_asset(
            image_bytes(), actor=self.actor, idempotency_key="asset", request_id="asset-request"
        ).body
        self.ad = self.manager.create_ad(
            {
                "title": "카페 공개 API 연결",
                "asset_id": asset["asset_id"],
                "link_url": "https://example.test/cafe",
                "placement": "top",
                "starts_at": self.now,
                "ends_at": self.now + timedelta(hours=1),
                "priority": 1,
            },
            actor=self.actor,
            idempotency_key="create",
            request_id="create-request",
        ).body
        self.client = APIClient(enforce_csrf_checks=True)
        token_request = RequestFactory().get("/", HTTP_HOST="testserver")
        self.csrf_token = get_token(token_request)
        self.client.cookies[settings.CSRF_COOKIE_NAME] = token_request.META["CSRF_COOKIE"]
        self.headers = {
            "HTTP_X_CSRFTOKEN": self.csrf_token,
            "HTTP_ORIGIN": "http://testserver",
        }
        repository_patch = patch(
            "api.ads_public.get_public_ads_repository", return_value=self.repository
        )
        repository_patch.start()
        self.addCleanup(repository_patch.stop)
        policy_patch = patch(
            "api.ads_public.load_public_policy", return_value=fixture_public_policy()
        )
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        service_patch = patch(
            "api.ads_public.AdsPublicService",
            side_effect=lambda repository, **kwargs: AdsPublicService(
                repository, **kwargs, clock=lambda: self.now, id_factory=self.identifier
            ),
        )
        service_patch.start()
        self.addCleanup(service_patch.stop)

    def test_real_delivery_image_event_and_replay_use_one_atomic_usage_record(self):
        first = self.client.get("/api/ads", {"placement": "top"}, HTTP_IDEMPOTENCY_KEY="issue")
        self.assertEqual(first.status_code, 200)
        ad = first.json()["ad"]
        self.assertEqual(ad["ad_id"], self.ad["ad_id"])
        replay = self.client.get("/api/ads", {"placement": "top"}, HTTP_IDEMPOTENCY_KEY="issue")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(len(self.repository.deliveries), 1)
        image_url = urlsplit(ad["image_url"])
        image = self.client.get(f"{image_url.path}?{image_url.query}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(b"".join(image.streaming_content), image_bytes())
        event = {
            "event_id": "connected-click",
            "delivery_id": ad["delivery_id"],
            "event_type": "CLICK",
            "occurred_at": self.now.isoformat(),
        }
        headers = {**self.headers, "HTTP_X_AD_DELIVERY_TOKEN": ad["delivery_token"]}
        counted = self.client.post("/api/ad-events", event, format="json", **headers)
        self.assertEqual(counted.status_code, 200)
        self.assertEqual(counted.json()["result"], "COUNTED")
        repeated = self.client.post("/api/ad-events", event, format="json", **headers)
        self.assertEqual(repeated.json(), counted.json())
        self.assertEqual(len(self.repository.events), 1)
        self.assertEqual(len(self.repository.usage), 1)
        usage = next(iter(self.repository.usage.values()))
        self.assertEqual(usage["estimated_tokens"], 15)
        self.assertEqual(usage["metric_date_kst"], "2026-10-15")

    def test_real_domain_forbidden_event_fields_save_no_event_or_usage(self):
        ad = self.client.get("/api/ads", {"placement": "top"}).json()["ad"]
        response = self.client.post(
            "/api/ad-events",
            {
                "event_id": "forged",
                "delivery_id": ad["delivery_id"],
                "event_type": "CLICK",
                "occurred_at": self.now.isoformat(),
                "owner_guest_id": "attacker",
                "estimated_tokens": 1,
            },
            format="json",
            **{**self.headers, "HTTP_X_AD_DELIVERY_TOKEN": ad["delivery_token"]},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["details"]["fields"], ["estimated_tokens", "owner_guest_id"]
        )
        self.assertFalse(self.repository.events)
        self.assertFalse(self.repository.usage)

    def test_real_stop_hides_reconfirmed_ad_and_blocks_old_image_capability(self):
        ad = self.client.get("/api/ads", {"placement": "top"}).json()["ad"]
        self.manager.stop_ad(
            ad["ad_id"],
            {"version": self.ad["version"]},
            actor=self.actor,
            idempotency_key="stop",
            request_id="stop-request",
        )
        response = self.client.get(
            "/api/ads",
            {"placement": "top", "delivery_id": ad["delivery_id"]},
            HTTP_X_AD_DELIVERY_TOKEN=ad["delivery_token"],
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["ad"])
        image_url = urlsplit(ad["image_url"])
        self.assertEqual(self.client.get(f"{image_url.path}?{image_url.query}").status_code, 404)
