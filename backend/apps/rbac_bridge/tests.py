from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.clusters.models import Cluster, ClusterCapability, ClusterHealthStatus
from apps.iam.models import User, UserGroup, UserGroupMembership

from .models import SubjectMapping


class RbacBridgeAPITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.com", password="secret123")
        self.user = User.objects.create_user(email="viewer@example.com", password="secret123")
        self.group = UserGroup.objects.create(name="Platform Team")
        UserGroupMembership.objects.create(user=self.user, group=self.group)

        token = Token.objects.create(user=self.admin)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.cluster = Cluster.objects.create(
            name="demo",
            slug="demo",
            environment="development",
            server="https://127.0.0.1:6443",
            default_context="demo",
        )
        ClusterCapability.objects.create(cluster=self.cluster)
        ClusterHealthStatus.objects.create(cluster=self.cluster)

    def test_admin_can_create_and_update_subject_mapping(self):
        response = self.client.post(
            "/api/v1/rbac/mappings",
            {
                "source_type": "user",
                "source_identifier": self.user.email,
                "kubernetes_username": "viewer@corp.local",
                "kubernetes_groups": ["team:platform"],
                "cluster": str(self.cluster.id),
                "is_enabled": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        mapping_id = response.json()["id"]
        self.assertEqual(SubjectMapping.objects.count(), 1)

        update_response = self.client.patch(
            f"/api/v1/rbac/mappings/{mapping_id}",
            {
                "kubernetes_groups": ["team:platform", "env:dev"],
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["kubernetes_groups"], ["team:platform", "env:dev"])

    def test_current_user_preview_merges_user_and_group_mapping(self):
        SubjectMapping.objects.create(
            source_type="user",
            source_identifier=self.user.email,
            kubernetes_username="viewer@corp.local",
            kubernetes_groups=["team:platform"],
            cluster=self.cluster,
        )
        SubjectMapping.objects.create(
            source_type="group",
            source_identifier=self.group.slug,
            kubernetes_groups=["role:readonly"],
            cluster=self.cluster,
        )

        user_client = APIClient()
        user_token = Token.objects.create(user=self.user)
        user_client.credentials(HTTP_AUTHORIZATION=f"Token {user_token.key}")

        response = user_client.get(f"/api/v1/rbac/me?cluster_id={self.cluster.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["username"], "viewer@corp.local")
        self.assertIn("team:platform", payload["groups"])
        self.assertIn("role:readonly", payload["groups"])
        self.assertIn("kuboard:authenticated", payload["groups"])

    def test_admin_can_toggle_cluster_impersonation(self):
        response = self.client.patch(
            f"/api/v1/rbac/clusters/{self.cluster.id}/impersonation",
            {"supports_impersonation": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.cluster.refresh_from_db()
        self.cluster.capability.refresh_from_db()
        self.assertTrue(self.cluster.capability.supports_impersonation)
