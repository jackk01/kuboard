from unittest.mock import patch

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.clusters.models import (
    Cluster,
    ClusterCapability,
    ClusterCredential,
    ClusterHealthState,
    ClusterHealthStatus,
    ClusterStatus,
)
from apps.k8s_gateway.services import KubernetesAPIError
from apps.clusters.services import _is_ip_address, _replace_server_host, validate_kubeconfig
from apps.iam.models import User


class IsIpAddressTests(TestCase):
    def test_ipv4(self):
        self.assertTrue(_is_ip_address("127.0.0.1"))
        self.assertTrue(_is_ip_address("192.168.1.100"))

    def test_ipv6(self):
        self.assertTrue(_is_ip_address("::1"))
        self.assertTrue(_is_ip_address("[::1]"))
        self.assertTrue(_is_ip_address("fe80::1"))

    def test_hostname(self):
        self.assertFalse(_is_ip_address("master"))
        self.assertFalse(_is_ip_address("example.com"))
        self.assertFalse(_is_ip_address("k8s-master.local"))


class ReplaceServerHostTests(TestCase):
    def test_replace_hostname_with_ip(self):
        result = _replace_server_host("https://master:6443", "192.168.1.100")
        self.assertEqual(result, "https://192.168.1.100:6443")

    def test_replace_hostname_without_port(self):
        result = _replace_server_host("https://master", "10.0.0.1")
        self.assertEqual(result, "https://10.0.0.1")

    def test_replace_with_ipv6(self):
        result = _replace_server_host("https://master:6443", "::1")
        self.assertEqual(result, "https://[::1]:6443")

    def test_empty_url(self):
        result = _replace_server_host("", "10.0.0.1")
        self.assertEqual(result, "")

    def test_empty_ip(self):
        result = _replace_server_host("https://master:6443", "")
        self.assertEqual(result, "https://master:6443")

    def test_preserve_path(self):
        result = _replace_server_host("https://master:6443/api/v1", "10.0.0.1")
        self.assertEqual(result, "https://10.0.0.1:6443/api/v1")


class KubeconfigValidationTests(TestCase):
    def test_validate_rejects_exec_plugin(self):
        kubeconfig = """
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: sample
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1
        command: aws
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        with self.assertRaises(ValidationError):
            validate_kubeconfig(kubeconfig)

    def test_validate_accepts_safe_kubeconfig(self):
        kubeconfig = """
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        inspection = validate_kubeconfig(kubeconfig)
        self.assertEqual(inspection.current_context, "sample")
        self.assertEqual(inspection.server, "https://127.0.0.1:6443")

    def test_validate_rejects_local_certificate_paths(self):
        kubeconfig = """
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
      certificate-authority: /tmp/ca.crt
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        with self.assertRaises(ValidationError):
            validate_kubeconfig(kubeconfig)


class ValidateKubeconfigServerOverrideTests(TestCase):
    def test_server_override_replaces_hostname(self):
        kubeconfig = """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://master:6443
      certificate-authority-data: dGVzdA==
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        inspection = validate_kubeconfig(kubeconfig, server_override="192.168.1.100")
        self.assertEqual(inspection.server, "https://192.168.1.100:6443")
        self.assertIn("192.168.1.100", inspection.normalized)

    def test_server_override_ignored_for_ip_server(self):
        kubeconfig = """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://10.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        # server_override 应该不影响已经是 IP 地址的 server
        inspection = validate_kubeconfig(kubeconfig, server_override="192.168.1.100")
        self.assertEqual(inspection.server, "https://10.0.0.1:6443")

    def test_no_server_override_keeps_hostname(self):
        kubeconfig = """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://master:6443
      certificate-authority-data: dGVzdA==
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        inspection = validate_kubeconfig(kubeconfig)
        self.assertEqual(inspection.server, "https://master:6443")

    def test_server_override_with_ip_unchanged(self):
        kubeconfig = """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://10.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
"""
        inspection = validate_kubeconfig(kubeconfig)
        self.assertEqual(inspection.server, "https://10.0.0.1:6443")


class ClusterManagementAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cluster-admin@example.com", password="secret123")
        token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.cluster = Cluster.objects.create(
            name="prod-cluster",
            slug="prod-cluster",
            environment="prod",
            description="initial description",
            server="https://127.0.0.1:6443",
            default_context="prod",
            status=ClusterStatus.READY,
            imported_by=self.user,
        )
        ClusterCredential.objects.create(
            cluster=self.cluster,
            active_context="prod",
            kubeconfig_encrypted="encrypted",
            fingerprint="fingerprint",
        )
        ClusterCapability.objects.create(cluster=self.cluster)
        ClusterHealthStatus.objects.create(cluster=self.cluster, status="healthy", message="ok", latency_ms=5)

    def test_update_cluster_metadata(self):
        response = self.client.patch(
            f"/api/v1/clusters/{self.cluster.id}",
            {
                "name": "prod-cluster-updated",
                "environment": "uat",
                "description": "updated description",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "prod-cluster-updated")
        self.assertEqual(payload["environment"], "uat")
        self.assertEqual(payload["description"], "updated description")

    def test_delete_cluster(self):
        response = self.client.delete(f"/api/v1/clusters/{self.cluster.id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Cluster.objects.filter(id=self.cluster.id).exists())

    @patch("apps.k8s_gateway.services.KubernetesClient.discover")
    @patch("apps.k8s_gateway.services.KubernetesClient.probe")
    def test_import_cluster_triggers_initial_health_check(self, probe_mock, discover_mock):
        probe_mock.return_value = {"version": {"gitVersion": "v1.30.0"}, "latency_ms": 12}
        discover_mock.return_value = {
            "groups": [{"group": "core", "version": "v1", "preferred_version": "v1", "resources": []}],
            "resource_index": {},
            "supports_exec": False,
        }
        response = self.client.post(
            "/api/v1/clusters",
            data={
                "name": "imported-cluster",
                "environment": "dev",
                "description": "import test",
                "kubeconfig": """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
""",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], ClusterStatus.READY)
        self.assertEqual(payload["health_state"], ClusterHealthState.HEALTHY)
        self.assertEqual(payload["health"]["status"], ClusterHealthState.HEALTHY)
        self.assertIn("Kubernetes 版本", payload["health"]["message"])
        self.assertIn("Discovery 已同步", payload["health"]["message"])

    @patch("apps.k8s_gateway.services.KubernetesClient.probe", side_effect=KubernetesAPIError("探测失败", status_code=502))
    def test_import_cluster_health_probe_failure_does_not_block_import(self, _probe_mock):
        response = self.client.post(
            "/api/v1/clusters",
            data={
                "name": "imported-cluster-failed-probe",
                "environment": "dev",
                "description": "import test",
                "kubeconfig": """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
""",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], ClusterStatus.ERROR)
        self.assertEqual(payload["health_state"], ClusterHealthState.DEGRADED)
        self.assertEqual(payload["health"]["status"], ClusterHealthState.DEGRADED)
        self.assertIn("探测失败", payload["health"]["message"])

    @patch("apps.k8s_gateway.services.KubernetesClient.discover", side_effect=KubernetesAPIError("discovery 失败", status_code=502))
    @patch("apps.k8s_gateway.services.KubernetesClient.probe")
    def test_import_cluster_discovery_failure_does_not_block_import(self, probe_mock, _discover_mock):
        probe_mock.return_value = {"version": {"gitVersion": "v1.30.0"}, "latency_ms": 10}
        response = self.client.post(
            "/api/v1/clusters",
            data={
                "name": "imported-cluster-discovery-failed",
                "environment": "dev",
                "description": "import test",
                "kubeconfig": """\
apiVersion: v1
kind: Config
clusters:
  - name: sample
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: sample
    user:
      token: test-token
contexts:
  - name: sample
    context:
      cluster: sample
      user: sample
current-context: sample
""",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], ClusterStatus.READY)
        self.assertEqual(payload["health_state"], ClusterHealthState.HEALTHY)
        self.assertIn("Discovery 同步失败", payload["health"]["message"])
