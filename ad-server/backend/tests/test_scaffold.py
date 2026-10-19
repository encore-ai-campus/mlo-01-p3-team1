from django.test import SimpleTestCase, override_settings
from django.urls import resolve


@override_settings(ALLOWED_HOSTS=["testserver"])
class ScaffoldTests(SimpleTestCase):
    def test_health_does_not_require_database(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database_checked"], False)

    @override_settings(ADS_ADMIN_AUTHORIZER="")
    def test_ad_mutations_fail_closed_before_auth_integration(self):
        for path in ("/api/admin/ads", "/api/admin/ad-assets"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 503)
        self.assertEqual(self.client.get("/admin/ads").status_code, 404)

    def test_health_route_is_registered(self):
        self.assertEqual(resolve("/api/health").url_name, "health")
