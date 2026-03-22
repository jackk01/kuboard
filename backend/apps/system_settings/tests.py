from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.iam.models import User


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "kuboard-tests",
        }
    }
)
class SystemSettingsAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tester@example.com", password="secret123")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

    def test_health_endpoint_is_public(self):
        public_client = APIClient()

        response = public_client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_endpoint_checks_database_and_cache(self):
        public_client = APIClient()

        response = public_client.get("/api/v1/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["checks"]["database"]["ok"])
        self.assertTrue(response.json()["checks"]["cache"]["ok"])

    def test_dashboard_summary_reports_stream_hub_enabled(self):
        response = self.client.get("/api/v1/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["features"]["stream_hub"])
