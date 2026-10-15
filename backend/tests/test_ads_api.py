from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.middleware.csrf import get_token
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from api.ads_auth import AdminIdentity
from domains.ads.errors import DatabaseUnavailable
from domains.ads.service import AdsService
from tests.test_ads_domain import MemoryRepository, image_bytes


def allowed_admin(request, action):
    """테스트 전용 공유 인증 어댑터입니다. 요청의 임의 역할/ID를 사용하지 않습니다."""
    return AdminIdentity("shared-admin", "common-auth", "ADMIN", True, True)


def missing_admin(request, action):
    return None


def user_identity(request, action):
    return AdminIdentity("shared-user", "common-auth", "USER", True, True)


def inactive_admin(request, action):
    return AdminIdentity("shared-admin", "common-auth", "ADMIN", False, True)


def forbidden_admin(request, action):
    return AdminIdentity("shared-admin", "common-auth", "ADMIN", True, False)


def unavailable_auth(request, action):
    raise RuntimeError("secret-auth-provider-error")


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    ADS_ADMIN_AUTHORIZER="tests.test_ads_api.allowed_admin",
    ADS_IS_TEST=True,
    ADS_API_CONTRACT_VERSION="",
    CSRF_TRUSTED_ORIGINS=[],
)
class AdsApiTests(SimpleTestCase):
    """실제 DRF/CSRF와 도메인을 연결합니다. DB 통합/운영 인증 검증은 아닙니다."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        token_request = RequestFactory().get("/", HTTP_HOST="testserver")
        self.csrf_token = get_token(token_request)
        self.client.cookies[settings.CSRF_COOKIE_NAME] = token_request.META["CSRF_COOKIE"]
        self.headers = {
            "HTTP_X_CSRFTOKEN": self.csrf_token,
            "HTTP_ORIGIN": "http://testserver",
            "HTTP_IDEMPOTENCY_KEY": "api-first",
        }
        self.repository = MemoryRepository()
        self.repository.list_ads = Mock(return_value=([], False))
        self.repository.summary = Mock(return_value={"active": 0, "reserved": 0})
        self.repository_patch = patch("api.ads.get_ads_repository", return_value=self.repository)
        self.repository_provider = self.repository_patch.start()
        self.addCleanup(self.repository_patch.stop)
        self.now = timezone.now()
        self.actor = {"account_id": "shared-admin", "identity_source": "common-auth"}
        self.service = AdsService(self.repository, clock=lambda: self.now, is_test=True)
        asset = self.service.upload_asset(
            image_bytes(),
            actor=self.actor,
            idempotency_key="fixture-asset",
            request_id="fixture-request",
        )
        self.data = {
            "title": "카페 광고",
            "asset_id": asset.body["asset_id"],
            "link_url": "https://example.com/ads",
            "placement": "top",
            "starts_at": (self.now - timedelta(hours=1)).isoformat(),
            "ends_at": (self.now + timedelta(hours=1)).isoformat(),
            "priority": 1,
        }

    def post_json(self, path, data, **headers):
        return self.client.post(path, data, format="json", **{**self.headers, **headers})

    def assert_error(self, response, status, code, fields=None):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertTrue(body["message"])
        self.assertEqual(body["request_id"], response["X-Request-ID"])
        self.assertLessEqual(set(body), {"code", "message", "request_id", "details"})
        self.assertEqual(response["Cache-Control"], "no-store")
        if fields is not None:
            self.assertEqual(body["details"]["fields"], fields)

    @override_settings(ADS_ADMIN_AUTHORIZER="")
    def test_unconnected_auth_fails_closed_and_ignores_client_identity_headers(self):
        response = self.client.generic(
            "POST",
            "/api/admin/ads",
            "{",
            content_type="application/json",
            HTTP_X_ROLE="ADMIN",
            HTTP_X_ACCOUNT_ID="forged-admin",
        )
        self.assert_error(response, 503, "AUTH_UNAVAILABLE")
        self.repository_provider.assert_not_called()

    def test_shared_provider_controls_401_403_and_503_before_body_parsing(self):
        providers = (
            ("missing_admin", 401, "AUTH_REQUIRED"),
            ("inactive_admin", 401, "AUTH_REQUIRED"),
            ("user_identity", 403, "FORBIDDEN"),
            ("forbidden_admin", 403, "FORBIDDEN"),
            ("unavailable_auth", 503, "AUTH_UNAVAILABLE"),
        )
        for provider, status, code in providers:
            with self.subTest(provider=provider), self.settings(
                ADS_ADMIN_AUTHORIZER=f"tests.test_ads_api.{provider}"
            ):
                response = self.client.generic(
                    "POST", "/api/admin/ads", "{", content_type="application/json"
                )
                self.assert_error(response, status, code)
                self.assertNotIn("secret-auth-provider-error", response.content.decode())
        self.repository_provider.assert_not_called()

    def test_invalid_shared_identity_is_service_failure(self):
        provider = Mock(return_value={"role": "ADMIN", "active": True})
        with patch("api.ads_auth.import_string", return_value=provider):
            response = self.client.get("/api/admin/ads")
        self.assert_error(response, 503, "AUTH_UNAVAILABLE")
        self.repository_provider.assert_not_called()

    def test_csrf_missing_token_rejects_before_malformed_json(self):
        response = self.client.generic(
            "POST",
            "/api/admin/ads",
            "{",
            content_type="application/json",
            HTTP_ORIGIN="http://testserver",
        )
        self.assert_error(response, 403, "FORBIDDEN")
        self.repository_provider.assert_not_called()

    def test_untrusted_origin_rejects_before_malformed_json_even_with_csrf(self):
        response = self.client.generic(
            "POST",
            "/api/admin/ads",
            "{",
            content_type="application/json",
            **{**self.headers, "HTTP_ORIGIN": "https://untrusted.example"},
        )
        self.assert_error(response, 403, "FORBIDDEN")
        self.repository_provider.assert_not_called()

    def test_valid_csrf_and_auth_allow_json_parse_error_as_422(self):
        response = self.client.generic(
            "POST", "/api/admin/ads", "{", content_type="application/json", **self.headers
        )
        self.assert_error(response, 422, "VALIDATION_ERROR")

    def test_unknown_fields_report_actual_sorted_names_and_save_nothing(self):
        response = self.post_json(
            "/api/admin/ads", {**self.data, "target_tag_codes": ["CAFE"], "role": "ADMIN"}
        )
        self.assert_error(response, 422, "VALIDATION_ERROR", ["role", "target_tag_codes"])
        self.assertFalse(self.repository.ads)
        self.assertEqual(len(self.repository.mutations), 1)

    def test_priority_rejects_bool_string_and_float_without_coercion(self):
        for value in (True, "1", 1.0):
            with self.subTest(value=value):
                response = self.post_json("/api/admin/ads", {**self.data, "priority": value})
                self.assert_error(response, 422, "VALIDATION_ERROR", ["priority"])
        self.assertFalse(self.repository.ads)

    def test_idempotency_header_required(self):
        response = self.post_json("/api/admin/ads", self.data, HTTP_IDEMPOTENCY_KEY="")
        self.assert_error(response, 422, "VALIDATION_ERROR", ["idempotency_key"])
        self.assertFalse(self.repository.ads)

    def test_create_replay_uses_server_actor_and_original_body_with_new_request_header(self):
        original = self.post_json(
            "/api/admin/ads",
            self.data,
            HTTP_X_ROLE="USER",
            HTTP_X_ACCOUNT_ID="forged-actor",
            HTTP_X_REQUEST_ID="forged-request",
        )
        self.assertEqual(original.status_code, 201)
        replay = self.post_json("/api/admin/ads", self.data)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), original.json())
        self.assertNotEqual(replay["X-Request-ID"], original["X-Request-ID"])
        self.assertNotEqual(original["X-Request-ID"], "forged-request")
        self.assertEqual(len(self.repository.ads), 1)
        record = next(
            row for row in self.repository.mutations.values() if row["operation"] == "CREATE"
        )
        self.assertEqual(record["actor_account_id"], "shared-admin")
        self.assertEqual(record["identity_source"], "common-auth")
        self.assertEqual(record["log_relay"]["payload"]["request_id"], original["X-Request-ID"])
        self.assertEqual(record["response_snapshot"]["body"], original.json())

    def test_same_key_different_body_returns_conflict(self):
        original = self.post_json("/api/admin/ads", self.data)
        response = self.post_json("/api/admin/ads", {**self.data, "title": "다른 광고"})
        self.assert_error(response, 409, "IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.repository.ads[original.json()["ad_id"]]["title"], "카페 광고")

    def test_update_and_stop_preserve_stop_and_replay_before_old_version(self):
        created = self.post_json("/api/admin/ads", self.data).json()
        update_path = f"/api/admin/ads/{created['ad_id']}"
        edited = {**self.data, "title": "수정 광고", "version": 1}
        first = self.client.put(
            update_path, edited, format="json", **{**self.headers, "HTTP_IDEMPOTENCY_KEY": "edit"}
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["version"], 2)
        replay = self.client.put(
            update_path, edited, format="json", **{**self.headers, "HTTP_IDEMPOTENCY_KEY": "edit"}
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), first.json())
        stale = self.client.put(
            update_path, edited, format="json", **{**self.headers, "HTTP_IDEMPOTENCY_KEY": "stale"}
        )
        self.assert_error(stale, 409, "VERSION_CONFLICT")
        stopped = self.post_json(
            f"{update_path}/stop", {"version": 2}, HTTP_IDEMPOTENCY_KEY="stop"
        )
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["status"], "STOPPED")
        self.assertEqual(stopped.json()["version"], 3)
        updated = self.client.put(
            update_path,
            {**self.data, "title": "중단 후 수정", "version": 3},
            format="json",
            **{**self.headers, "HTTP_IDEMPOTENCY_KEY": "edit-stopped"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["paused"])
        self.assertEqual(updated.json()["status"], "STOPPED")
        replay_stop = self.post_json(
            f"{update_path}/stop", {"version": 2}, HTTP_IDEMPOTENCY_KEY="stop"
        )
        self.assertEqual(replay_stop.json(), stopped.json())

    def test_upload_multipart_replays_original_asset_without_extra_file(self):
        before = len(self.repository.assets)
        responses = []
        for filename in ("first.png", "replayed-name.png"):
            image = SimpleUploadedFile(filename, image_bytes(), content_type="image/png")
            responses.append(
                self.client.post("/api/admin/ad-assets", {"image": image}, **self.headers)
            )
        self.assertEqual(responses[0].status_code, 201)
        self.assertEqual(responses[1].status_code, 201)
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(len(self.repository.assets), before + 1)

    def test_upload_rejects_non_image_and_extra_fields(self):
        image = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        response = self.client.post("/api/admin/ad-assets", {"image": image}, **self.headers)
        self.assert_error(response, 422, "VALIDATION_ERROR", ["image"])
        image = SimpleUploadedFile("valid.png", image_bytes(), content_type="image/png")
        response = self.client.post(
            "/api/admin/ad-assets", {"image": image, "role": "ADMIN"}, **self.headers
        )
        self.assert_error(response, 422, "VALIDATION_ERROR", ["image"])

    def test_preview_uses_read_authority_and_creates_no_operational_data(self):
        provider = Mock(side_effect=allowed_admin)
        before = deepcopy((self.repository.ads, self.repository.assets, self.repository.mutations))
        with patch("api.ads_auth.import_string", return_value=provider):
            response = self.post_json("/api/admin/ads/preview", self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(provider.call_args.args[1], "read")
        self.assertFalse(response.json()["operational_delivery"])
        self.assertNotIn("delivery_id", response.json())
        self.assertEqual(response.json()["desktop"]["height"], 120)
        self.assertEqual(response.json()["mobile"], {"width": 390, "height": 120})
        self.assertEqual(
            before, (self.repository.ads, self.repository.assets, self.repository.mutations)
        )

    def test_asset_read_returns_original_bytes_with_admin_auth(self):
        response = self.client.get(f"/api/admin/ad-assets/{self.data['asset_id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), image_bytes())

    def test_summary_distinguishes_real_counts_and_unconnected_measurement(self):
        self.repository.summary.return_value = {"active": 2, "reserved": 1}
        response = self.client.get("/api/admin/ads/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"], {"active": 2, "reserved": 1})
        measurement = response.json()["measurement"]
        self.assertEqual(measurement["status"], "PENDING")
        self.assertEqual(measurement["message"], "연동 대기")
        for key in ("impressions", "clicks", "estimated_tokens"):
            self.assertIsNone(measurement[key])

    def test_list_accepts_filters_and_returns_signed_cursor_bound_to_them(self):
        created = self.service.create_ad(
            self.data, actor=self.actor, idempotency_key="fixture-ad", request_id="fixture-ad"
        )
        row = self.repository.ads[created.body["ad_id"]]
        self.repository.list_ads.return_value = ([row], True)
        query = {"placement": "top", "status": "ACTIVE", "page_size": "1"}
        response = self.client.get("/api/admin/ads", query)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"][0]["ad_id"], created.body["ad_id"])
        self.assertNotIn("image_bytes", body["items"][0])
        cursor = body["next_cursor"]
        self.assertTrue(cursor)
        self.repository.list_ads.return_value = ([], False)
        continued = self.client.get("/api/admin/ads", {**query, "cursor": cursor})
        self.assertEqual(continued.status_code, 200)
        self.assertEqual(continued.json()["as_of"], body["as_of"])
        self.assertEqual(
            self.repository.list_ads.call_args.kwargs["cursor"], (row["updated_at"], row["_id"])
        )
        for changed in ({"placement": "bottom"}, {"status": "ENDED"}, {"page_size": "2"}):
            with self.subTest(changed=changed):
                response = self.client.get(
                    "/api/admin/ads", {**query, **changed, "cursor": cursor}
                )
                self.assert_error(response, 422, "VALIDATION_ERROR", ["cursor"])

    def test_list_rejects_malformed_cursor_unknown_duplicate_filters_and_bad_page_sizes(self):
        invalid_queries = (
            ({"cursor": "forged-cursor"}, ["cursor"]),
            ({"target_tag_codes": "CAFE"}, ["target_tag_codes"]),
            ({"placement": ["top", "bottom"]}, ["placement"]),
            ({"page_size": "0"}, ["page_size"]),
            ({"page_size": "101"}, ["page_size"]),
            ({"page_size": "true"}, ["page_size"]),
        )
        for query, fields in invalid_queries:
            with self.subTest(query=query):
                response = self.client.get("/api/admin/ads", query)
                self.assert_error(response, 422, "VALIDATION_ERROR", fields)
        self.repository.list_ads.assert_not_called()

    def test_invalid_filter_enum_uses_option_invalid_error(self):
        for query, field in (({"placement": "all"}, "placement"), ({"status": "DRAFT"}, "status")):
            with self.subTest(query=query):
                response = self.client.get("/api/admin/ads", query)
                self.assert_error(response, 400, "OPTION_INVALID", [field])

    def test_database_failure_uses_common_503_without_exposing_connection_details(self):
        self.repository_provider.side_effect = DatabaseUnavailable()
        response = self.client.get("/api/admin/ads")
        self.assert_error(response, 503, "DATABASE_UNAVAILABLE")
        self.assertNotIn("mongodb://", response.content.decode())

    @override_settings(ADS_API_CONTRACT_VERSION="agreed-test-contract")
    def test_configured_contract_version_is_response_header_only(self):
        response = self.client.get("/api/admin/ads")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Contract-Version"], "agreed-test-contract")
        self.assertNotIn("data", response.json())
