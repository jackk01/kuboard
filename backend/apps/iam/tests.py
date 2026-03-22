from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.iam.models import User


class UserModelTests(TestCase):
    def test_create_user_uses_email_as_login_identifier(self):
        user = User.objects.create_user(email="dev@example.com", password="secret123")

        self.assertEqual(user.email, "dev@example.com")
        self.assertTrue(user.username)


class AdminUserAPITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="secret123",
            is_staff=True,
        )
        self.regular = User.objects.create_user(email="user@example.com", password="secret123")

        self.admin_client = APIClient()
        self.admin_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.admin).key}")

        self.user_client = APIClient()
        self.user_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.regular).key}")

    def test_admin_can_list_and_create_users(self):
        list_response = self.admin_client.get("/api/v1/users")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 2)

        create_response = self.admin_client.post(
            "/api/v1/users",
            {
                "email": "viewer@example.com",
                "display_name": "Viewer",
                "password": "viewer123456",
                "is_staff": False,
                "is_superuser": False,
                "password_needs_reset": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["email"], "viewer@example.com")

    def test_regular_user_cannot_access_user_admin_api(self):
        response = self.user_client.get("/api/v1/users")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_group_with_members(self):
        response = self.admin_client.post(
            "/api/v1/user-groups",
            {
                "name": "platform-team",
                "description": "Platform Team",
                "member_emails": [self.regular.email],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "platform-team")
        self.assertEqual(response.json()["member_count"], 1)
