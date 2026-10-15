"""로컬 임시 관리 화면의 인증·출처·기존 API 경계를 검증합니다.

실제 공유 사용자 DB나 운영 인증을 대체하는 테스트는 아닙니다.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, SimpleTestCase, override_settings
from pymongo.errors import ConnectionFailure, OperationFailure
from rest_framework.test import APIClient

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DomainError
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService
from domains.ads.validation import utc_string
from tests.policy_fixtures import MemoryPolicyRepository
from tests.test_ads_domain import image_bytes

SANDBOX_SETTINGS = {
    "IS_ADS_SANDBOX": True,
    "DEBUG": False,
    "ADS_IS_TEST": True,
    "ROOT_URLCONF": "config.sandbox_urls",
    "ALLOWED_HOSTS": ["127.0.0.1", "localhost", "untrusted.example"],
    "MIDDLEWARE": [
        "django.middleware.security.SecurityMiddleware",
        "api.ads_sandbox.SandboxMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
    ],
    "TEMPLATES": [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [settings.BASE_DIR / "templates"],
            "APP_DIRS": True,
            "OPTIONS": {"context_processors": ["django.template.context_processors.csrf"]},
        }
    ],
    "ADS_SANDBOX_ACCESS_TOKEN": "fixture-access-token-that-is-not-an-operating-password",
    "ADS_SANDBOX_INSTANCE_ID": "fixture-sandbox-instance",
    "ADS_MONGODB_DATABASE": "ads_sandbox_dev",
    "ADS_MONGODB_URI": "mongodb://127.0.0.1:27019/?replicaSet=ads-rs&directConnection=true",
    "CSRF_COOKIE_NAME": "ads_sandbox_csrf",
    "CSRF_COOKIE_SECURE": False,
    "CSRF_COOKIE_SAMESITE": "Strict",
    "CSRF_TRUSTED_ORIGINS": [],
    "CSRF_FAILURE_VIEW": "api.ads_sandbox.csrf_failure",
    "ADS_ADMIN_AUTHORIZER": "api.ads_sandbox.sandbox_admin",
    "ADS_GUEST_CONTEXT_PROVIDER": "api.ads_sandbox.sandbox_guest",
    "ADS_PUBLIC_POLICY_PROVIDER": "domains.ads.runtime_policy.get_public_policy",
    "ADS_DELIVERY_SIGNING_KEY": "fixture-sandbox-signing-key",
    "ADS_PUBLIC_BASE_URL": "https://127.0.0.1:8001",
}


@override_settings(**SANDBOX_SETTINGS)
class AdsSandboxTests(SimpleTestCase):
    """HTTP CSRF를 켜고 로컬 서명 세션을 실제 요청에 적용합니다."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.transport = {"HTTP_HOST": "127.0.0.1:8001", "REMOTE_ADDR": "127.0.0.1"}
        self.origin = "http://127.0.0.1:8001"

    def csrf_headers(self):
        self.client.get("/dev/ads/login", **self.transport)
        return {
            "HTTP_X_CSRFTOKEN": self.client.cookies[settings.CSRF_COOKIE_NAME].value,
            "HTTP_ORIGIN": self.origin,
        }

    def login(self):
        headers = self.csrf_headers()
        response = self.client.post(
            "/dev/ads/login",
            {"access_code": settings.ADS_SANDBOX_ACCESS_TOKEN},
            **headers,
            **self.transport,
        )
        self.assertEqual(response.status_code, 302)
        return response

    def signed_admin(self, *, instance=None, kind="ads-sandbox-admin"):
        return signing.dumps(
            {
                "kind": kind,
                "instance": settings.ADS_SANDBOX_INSTANCE_ID if instance is None else instance,
            },
            salt="ads-sandbox-admin-v1",
        )

    def test_general_urlconf_does_not_expose_temporary_admin(self):
        with self.settings(ROOT_URLCONF="config.urls", MIDDLEWARE=[]):
            for route in ("/dev/ads/", "/dev/ads/login", "/dev/ads/status", "/dev/ads/refresh"):
                with self.subTest(route=route):
                    self.assertEqual(self.client.get(route, **self.transport).status_code, 404)

    def test_login_requires_csrf_and_correct_access_code(self):
        denied = self.client.post(
            "/dev/ads/login",
            {"access_code": settings.ADS_SANDBOX_ACCESS_TOKEN},
            **self.transport,
        )
        self.assertEqual(denied.status_code, 403)
        response = self.client.post(
            "/dev/ads/login",
            {"access_code": "wrong-code"},
            **self.csrf_headers(),
            **self.transport,
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("ads_sandbox_admin", response.cookies)
        self.assertNotContains(
            response, settings.ADS_SANDBOX_ACCESS_TOKEN, status_code=response.status_code
        )

    def test_login_issues_instance_bound_http_only_cookie(self):
        response = self.login()
        cookie = response.cookies["ads_sandbox_admin"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertFalse(cookie["secure"])
        self.assertEqual(int(cookie["max-age"]), 28800)
        payload = signing.loads(cookie.value, salt="ads-sandbox-admin-v1", max_age=28800)
        self.assertEqual(
            payload,
            {"kind": "ads-sandbox-admin", "instance": settings.ADS_SANDBOX_INSTANCE_ID},
        )
        self.assertNotIn(settings.ADS_SANDBOX_ACCESS_TOKEN, cookie.value)

    def test_missing_admin_redirects_page_and_denies_api_without_database_access(self):
        with patch("api.ads.get_ads_repository") as repository:
            page = self.client.get("/dev/ads/", **self.transport)
            self.assertEqual(page.status_code, 302)
            self.assertEqual(urlsplit(page["Location"]).path, "/dev/ads/login")
            api = self.client.get("/api/admin/ads", **self.transport)
            self.assertEqual(api.status_code, 401)
            repository.assert_not_called()

    def test_public_ad_routes_also_require_local_admin_before_guest_or_database_access(self):
        with (
            patch("api.ads_public.get_ads_policy_repository") as repository,
            patch("api.ads_public.resolve_guest") as guest,
        ):
            response = self.client.get("/api/ads", {"placement": "top"}, **self.transport)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("ads_sandbox_guest", response.cookies)
        repository.assert_not_called()
        guest.assert_not_called()

    def test_tampered_wrong_instance_and_wrong_kind_cookies_are_not_admin(self):
        cookies = (
            self.signed_admin() + "tampered",
            self.signed_admin(instance="different-process"),
            self.signed_admin(kind="ads-sandbox-guest"),
        )
        with patch("api.ads.get_ads_repository") as repository:
            for cookie in cookies:
                with self.subTest(cookie=cookie):
                    self.client.cookies["ads_sandbox_admin"] = cookie
                    response = self.client.get("/api/admin/ads", **self.transport)
                    self.assertEqual(response.status_code, 401)
            repository.assert_not_called()

    def test_expired_admin_cookie_is_rejected(self):
        with patch("django.core.signing.time.time", return_value=1_700_000_000):
            self.client.cookies["ads_sandbox_admin"] = self.signed_admin()
        with patch("django.core.signing.time.time", return_value=1_700_028_801):
            self.assertEqual(self.client.get("/api/admin/ads", **self.transport).status_code, 401)

    def test_local_guard_blocks_remote_ip_and_host_and_ignores_forwarded_headers(self):
        self.client.cookies["ads_sandbox_admin"] = self.signed_admin()
        cases = (
            {"REMOTE_ADDR": "192.0.2.12", "HTTP_X_FORWARDED_FOR": "127.0.0.1"},
            {"HTTP_HOST": "untrusted.example", "HTTP_X_FORWARDED_HOST": "127.0.0.1"},
        )
        with patch("api.ads.get_ads_repository") as repository:
            for transport in cases:
                with self.subTest(transport=transport):
                    response = self.client.get("/api/admin/ads", **{**self.transport, **transport})
                    self.assertEqual(response.status_code, 403)
            repository.assert_not_called()

    def test_sandbox_flag_is_required_even_with_valid_cookie(self):
        self.client.cookies["ads_sandbox_admin"] = self.signed_admin()
        with self.settings(IS_ADS_SANDBOX=False):
            self.assertEqual(self.client.get("/dev/ads/login", **self.transport).status_code, 403)

    def test_guard_rejects_non_test_or_different_database_before_authentication(self):
        for changed in (
            {"ADS_IS_TEST": False},
            {"ADS_MONGODB_DATABASE": "advertising_dev"},
        ):
            with self.subTest(settings=changed), self.settings(**changed):
                self.assertEqual(
                    self.client.get("/dev/ads/login", **self.transport).status_code, 403
                )

    def test_login_has_no_store_and_per_response_nonce_content_security_policy(self):
        first = self.client.get("/dev/ads/login", **self.transport)
        second = self.client.get("/dev/ads/login", **self.transport)
        self.assertEqual(first.status_code, 200)
        self.assertIn("no-store", first["Cache-Control"])
        self.assertEqual(first["Referrer-Policy"], "no-referrer")
        self.assertEqual(first["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", first["Content-Security-Policy"])
        self.assertNotIn("'unsafe-inline'", first["Content-Security-Policy"])
        self.assertNotEqual(first["Content-Security-Policy"], second["Content-Security-Policy"])

    def test_status_requires_admin_and_reports_only_sandbox_health(self):
        denied = self.client.get("/dev/ads/status", **self.transport)
        self.assertEqual(denied.status_code, 401)
        self.login()
        worker = {"running": True, "last_success_at": None}
        with patch("api.ads_sandbox.sandbox_runtime.worker_status", return_value=worker):
            response = self.client.get("/dev/ads/status", **self.transport)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "ads_sandbox_dev")
        self.assertIs(response.json()["is_test"], True)
        self.assertEqual(response.json()["log_sink"], "NOT_CONNECTED")
        self.assertNotContains(response, settings.ADS_SANDBOX_ACCESS_TOKEN)

    def test_runtime_guard_rejects_remote_and_malformed_uris_without_database_connection(self):
        from domains.ads.sandbox_runtime import require_sandbox

        for uri in (
            "mongodb://192.0.2.1:27017/",
            "mongodb://127.0.0.1:27019,192.0.2.1:27017/",
            "mongodb+srv://cluster.example.test/",
            "mongodb://",
            "mongodb://127.0.0.1:27019/?replicaSet=ads-rs",
            "mongodb://127.0.0.1:27019/?replicaSet=ads-rs&directConnection=false",
        ):
            with self.subTest(uri=uri), self.settings(ADS_MONGODB_URI=uri):
                with self.assertRaises(DomainError) as caught:
                    require_sandbox()
                self.assertEqual(caught.exception.code, "SANDBOX_LOCAL_ONLY")
                self.assertNotIn(uri, caught.exception.message)

    def test_launcher_rejects_regular_settings_before_starting_mongo_or_worker(self):
        with (
            self.settings(SETTINGS_MODULE="config.settings"),
            patch("domains.ads.management.commands.run_ads_sandbox.local_client") as database,
            patch(
                "domains.ads.management.commands.run_ads_sandbox.sandbox_runtime.start_worker"
            ) as worker,
        ):
            with self.assertRaises(CommandError):
                call_command("run_ads_sandbox", start_mongo=True)
        database.assert_not_called()
        worker.assert_not_called()

    def test_cross_origin_login_is_rejected_with_valid_csrf_token(self):
        headers = self.csrf_headers()
        headers["HTTP_ORIGIN"] = "https://untrusted.example"
        response = self.client.post(
            "/dev/ads/login",
            {"access_code": settings.ADS_SANDBOX_ACCESS_TOKEN},
            **headers,
            **self.transport,
        )
        self.assertEqual(response.status_code, 403)

    def test_logout_requires_post_csrf_and_revokes_browser_cookie(self):
        self.login()
        response = self.client.get("/dev/ads/logout", **self.transport)
        self.assertEqual(response.status_code, 405)
        denied = self.client.post("/dev/ads/logout", **self.transport)
        self.assertEqual(denied.status_code, 403)
        response = self.client.post("/dev/ads/logout", **self.csrf_headers(), **self.transport)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(response.cookies["ads_sandbox_admin"]["max-age"]), 0)
        self.assertEqual(self.client.get("/api/admin/ads", **self.transport).status_code, 401)

    def test_manual_policy_refresh_requires_csrf_and_runs_once(self):
        self.login()
        result = {"ads_checked": 1, "blocked": 0, "metrics_rows": 1}
        with patch("api.ads_sandbox.sandbox_runtime.refresh_policy", return_value=result) as job:
            self.assertEqual(self.client.get("/dev/ads/refresh", **self.transport).status_code, 405)
            self.assertEqual(
                self.client.post("/dev/ads/refresh", **self.transport).status_code, 403
            )
            job.assert_not_called()
            response = self.client.post("/dev/ads/refresh", **self.csrf_headers(), **self.transport)
        self.assertEqual(response.status_code, 200)
        job.assert_called_once_with()

    def test_manual_refresh_reports_busy_without_exposing_database_error_details(self):
        self.login()
        errors = (
            (DomainError("SANDBOX_BUSY", "검증 중입니다.", 409), 409, "SANDBOX_BUSY"),
            (
                RuntimeError("mongodb://private-password@database.example/"),
                503,
                "SANDBOX_REFRESH_FAILED",
            ),
        )
        for error, status_code, code in errors:
            with (
                self.subTest(code=code),
                patch("api.ads_sandbox.sandbox_runtime.refresh_policy", side_effect=error),
            ):
                response = self.client.post(
                    "/dev/ads/refresh", **self.csrf_headers(), **self.transport
                )
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json()["code"], code)
                self.assertNotContains(response, "private-password", status_code=status_code)

    def test_sandbox_authorizer_does_not_accept_client_account_or_role(self):
        from api.ads_sandbox import sandbox_admin

        request = RequestFactory().get(
            "/api/admin/ads",
            HTTP_X_ROLE="ADMIN",
            HTTP_X_ACCOUNT_ID="forged-account",
            **self.transport,
        )
        self.assertIsNone(sandbox_admin(request, "CREATE"))
        request.COOKIES["ads_sandbox_admin"] = self.signed_admin()
        identity = sandbox_admin(request, "CREATE")
        self.assertEqual(identity.role, "ADMIN")
        self.assertTrue(identity.active)
        self.assertTrue(identity.ads_allowed)
        self.assertNotEqual(identity.account_id, "forged-account")

    def test_local_guest_requires_admin_and_cookie_reuse_is_stable(self):
        from api.ads_sandbox import sandbox_guest

        request = RequestFactory().get("/api/ads", **self.transport)
        denied = sandbox_guest(request, bootstrap=True)
        self.assertFalse(denied.measurement_available)
        self.assertIsNone(denied.owner_guest_id)
        request.COOKIES["ads_sandbox_admin"] = self.signed_admin()
        uninitialized = sandbox_guest(request, bootstrap=False)
        self.assertIsNone(uninitialized.owner_guest_id)
        self.assertFalse(uninitialized.measurement_available)
        created = sandbox_guest(request, bootstrap=True)
        self.assertTrue(created.measurement_available)
        self.assertTrue(created.owner_guest_id)
        self.assertTrue(callable(created.response_finalizer))
        from django.http import HttpResponse

        response = HttpResponse()
        created.response_finalizer(response)
        cookie = response.cookies["ads_sandbox_guest"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        request.COOKIES["ads_sandbox_guest"] = cookie.value
        resolved = sandbox_guest(request, bootstrap=False)
        self.assertEqual(resolved.owner_guest_id, created.owner_guest_id)

    def test_authenticated_management_and_public_requests_share_test_ads_only(self):
        self.login()
        now = datetime(2026, 10, 15, 5, tzinfo=UTC)
        repository = MemoryPolicyRepository(is_test=True)
        service = AdsService(repository, clock=lambda: now, is_test=True)
        actor = {"account_id": "fixture-sandbox", "identity_source": "sandbox"}
        asset = service.upload_asset(
            image_bytes(), actor=actor, idempotency_key="asset", request_id="asset"
        ).body
        data = {
            "title": "샌드박스 광고",
            "asset_id": asset["asset_id"],
            "link_url": "https://example.test/ad",
            "placement": "top",
            "starts_at": now,
            "ends_at": now + timedelta(hours=1),
            "priority": 1,
            "daily_budget_tokens": 1000,
            "total_budget_tokens": 1000,
        }
        created = service.create_ad(
            data, actor=actor, idempotency_key="create", request_id="create"
        ).body
        AdsBudgetService(repository, clock=lambda: now).run_once()
        with (
            patch("api.ads.get_ads_repository", return_value=repository),
            patch("api.ads_public.get_ads_policy_repository", return_value=repository),
            patch(
                "api.ads_public.AdsPublicService",
                side_effect=lambda repo, **kwargs: AdsPublicService(
                    repo, clock=lambda: now, **kwargs
                ),
            ),
        ):
            public = self.client.get("/api/ads", {"placement": "top"}, **self.transport)
            self.assertEqual(public.status_code, 200)
            self.assertEqual(public.json()["ad"]["ad_id"], created["ad_id"])
            delivery = public.json()["ad"]
            event = self.client.post(
                "/api/ad-events",
                {
                    "event_id": str(uuid4()),
                    "delivery_id": delivery["delivery_id"],
                    "event_type": "VIEWABLE_IMPRESSION",
                    "occurred_at": utc_string(now),
                },
                format="json",
                HTTP_X_AD_DELIVERY_TOKEN=delivery["delivery_token"],
                **self.csrf_headers(),
                **self.transport,
            )
            self.assertEqual(event.status_code, 200)
            self.assertEqual(event.json()["result"], "MEASUREMENT_UNAVAILABLE")
            self.assertFalse(event.json()["counted"])
            self.assertFalse(repository.usage)
            uploaded = self.client.post(
                "/api/admin/ad-assets",
                {"image": SimpleUploadedFile("test.png", image_bytes(), "image/png")},
                format="multipart",
                HTTP_IDEMPOTENCY_KEY="sandbox-upload",
                **self.csrf_headers(),
                **self.transport,
            )
            self.assertEqual(uploaded.status_code, 201)
        self.assertTrue(all(item["is_test"] is True for item in repository.assets.values()))
        self.assertTrue(all(item["is_test"] is True for item in repository.deliveries.values()))

    def test_existing_mongo_is_not_started_or_owned_by_launcher(self):
        from domains.ads.management.commands.run_ads_sandbox import start_mongo

        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.admin.command.return_value = {"ok": 1}
        with (
            patch(
                "domains.ads.management.commands.run_ads_sandbox.MongoClient", return_value=client
            ),
            patch("domains.ads.management.commands.run_ads_sandbox.subprocess.Popen") as process,
        ):
            owned = start_mongo("missing-executable", Path("unused-state-directory"))
        self.assertIsNone(owned)
        process.assert_not_called()

    def test_failed_owned_mongo_start_terminates_only_owned_process(self):
        from domains.ads.management.commands.run_ads_sandbox import start_mongo

        probe = Mock()
        probe.__enter__ = Mock(return_value=probe)
        probe.__exit__ = Mock(return_value=False)
        probe.admin.command.side_effect = ConnectionFailure("fixture-port-unused")
        initializing = Mock()
        initializing.__enter__ = Mock(return_value=initializing)
        initializing.__exit__ = Mock(return_value=False)
        initializing.admin.command.side_effect = OperationFailure(
            "fixture-invalid-config", code=103
        )
        process = Mock()
        process.poll.return_value = None
        with (
            TemporaryDirectory(
                prefix="ads-sandbox-process-test-", dir=Path(__file__).resolve().parent
            ) as temporary,
            patch(
                "domains.ads.management.commands.run_ads_sandbox.MongoClient",
                side_effect=[probe, initializing],
            ),
            patch(
                "domains.ads.management.commands.run_ads_sandbox.subprocess.Popen",
                return_value=process,
            ),
        ):
            with self.assertRaises(CommandError):
                start_mongo(__file__, Path(temporary))
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=10)

    def test_failed_batch_releases_lock_and_status_has_only_error_class(self):
        from domains.ads import sandbox_runtime

        result = {"ads_checked": 0, "blocked": 0, "metrics_rows": 0}
        service = Mock()
        service.run_once.side_effect = [RuntimeError("mongodb://private-password@local/"), result]
        with (
            patch.object(sandbox_runtime, "_batch_lock", Lock()),
            patch.object(
                sandbox_runtime,
                "_state",
                {"last_started_at": None, "last_succeeded_at": None, "last_error": None},
            ),
            patch.object(sandbox_runtime, "get_ads_policy_repository", return_value=object()),
            patch.object(sandbox_runtime, "AdsBudgetService", return_value=service),
        ):
            with self.assertRaises(RuntimeError):
                sandbox_runtime.refresh_policy()
            status = sandbox_runtime.worker_status()
            self.assertEqual(status["last_error"], "RuntimeError")
            self.assertNotIn("private-password", str(status))
            self.assertEqual(sandbox_runtime.refresh_policy(), result)
            self.assertIsNone(sandbox_runtime.worker_status()["last_error"])

    def test_worker_starts_once_and_stop_releases_waiting_thread(self):
        from domains.ads import sandbox_runtime

        with (
            patch.object(sandbox_runtime, "_stop", Event()),
            patch.object(sandbox_runtime, "_thread", None),
            patch.object(sandbox_runtime, "refresh_policy") as refresh,
        ):
            try:
                sandbox_runtime.start_worker()
                first = sandbox_runtime._thread
                self.assertTrue(sandbox_runtime.worker_status()["running"])
                sandbox_runtime.start_worker()
                self.assertIs(sandbox_runtime._thread, first)
                refresh.assert_called_once_with()
            finally:
                sandbox_runtime.stop_worker()
            self.assertFalse(first.is_alive())
            self.assertFalse(sandbox_runtime.worker_status()["running"])
