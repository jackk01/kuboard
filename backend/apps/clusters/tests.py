from pathlib import Path
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
from apps.clusters.services import _is_ip_address, load_local_kubeconfig, validate_kubeconfig
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

class KubeconfigHostnameTests(TestCase):
    def test_hostname_server_kept_for_local_hosts_resolution(self):
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


class LoadLocalKubeconfigTests(TestCase):
    @patch("apps.clusters.services.Path.home", return_value=Path("/tmp/kuboard-home"))
    def test_load_local_kubeconfig_reads_default_path(self, _home_mock):
        kubeconfig = """\
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
        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.is_file", return_value=True), patch(
            "pathlib.Path.read_text", return_value=kubeconfig
        ) as read_text_mock:
            result = load_local_kubeconfig()

        read_text_mock.assert_called_once_with(encoding="utf-8")
        self.assertEqual(result.source_path, "/tmp/kuboard-home/.kube/config")
        self.assertEqual(result.kubeconfig, kubeconfig)
        self.assertEqual(result.inspection.current_context, "sample")

    @patch("apps.clusters.services.Path.home", return_value=Path("/tmp/kuboard-home"))
    def test_load_local_kubeconfig_raises_when_missing(self, _home_mock):
        with patch("pathlib.Path.exists", return_value=False):
            with self.assertRaises(ValidationError) as context:
                load_local_kubeconfig()

        self.assertIn("未找到本地 kubeconfig 文件", str(context.exception))


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
        credential = ClusterCredential.objects.create(
            cluster=self.cluster,
            active_context="prod",
            kubeconfig_encrypted="encrypted",
            fingerprint="fingerprint",
        )
        credential.set_kubeconfig(
            """\
apiVersion: v1
kind: Config
clusters:
  - name: prod
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: prod
    user:
      token: old-token
contexts:
  - name: prod
    context:
      cluster: prod
      user: prod
current-context: prod
"""
        )
        credential.save()
        ClusterCapability.objects.create(cluster=self.cluster)
        ClusterHealthStatus.objects.create(cluster=self.cluster, status="healthy", message="ok", latency_ms=5)

    def test_get_cluster_detail_includes_kubeconfig(self):
        response = self.client.get(f"/api/v1/clusters/{self.cluster.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("kubeconfig", payload)
        self.assertEqual(payload["active_context"], "prod")
        self.assertIn("current-context: prod", payload["kubeconfig"])

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

    @patch("apps.k8s_gateway.services.KubernetesClient.discover")
    @patch("apps.k8s_gateway.services.KubernetesClient.probe")
    def test_update_cluster_kubeconfig(self, probe_mock, discover_mock):
        probe_mock.return_value = {"version": {"gitVersion": "v1.30.1"}, "latency_ms": 8}
        discover_mock.return_value = {
            "groups": [{"group": "core", "version": "v1", "preferred_version": "v1", "resources": []}],
            "resource_index": {},
            "supports_exec": False,
        }

        response = self.client.patch(
            f"/api/v1/clusters/{self.cluster.id}",
            {
                "name": "prod-cluster",
                "environment": "prod",
                "description": "rotated token",
                "kubeconfig": """\
apiVersion: v1
kind: Config
clusters:
  - name: prod-new
    cluster:
      server: https://10.0.0.10:6443
users:
  - name: prod-new
    user:
      token: new-token
contexts:
  - name: prod-new
    context:
      cluster: prod-new
      user: prod-new
current-context: prod-new
""",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.cluster.refresh_from_db()
        self.cluster.credential.refresh_from_db()
        payload = response.json()
        self.assertEqual(payload["server"], "https://10.0.0.10:6443")
        self.assertEqual(payload["default_context"], "prod-new")
        self.assertEqual(self.cluster.credential.active_context, "prod-new")
        self.assertIn("new-token", self.cluster.credential.get_kubeconfig())

    def test_delete_cluster(self):
        response = self.client.delete(f"/api/v1/clusters/{self.cluster.id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Cluster.objects.filter(id=self.cluster.id).exists())

    @patch("apps.clusters.api.load_local_kubeconfig")
    def test_get_local_kubeconfig(self, load_local_kubeconfig_mock):
        load_local_kubeconfig_mock.return_value = type(
            "LocalResult",
            (),
            {
                "source_path": "/Users/test/.kube/config",
                "kubeconfig": "apiVersion: v1\nkind: Config\n",
                "inspection": type(
                    "Inspection",
                    (),
                    {
                        "current_context": "sample",
                        "server": "https://127.0.0.1:6443",
                        "cluster_count": 1,
                        "user_count": 1,
                        "context_count": 1,
                        "fingerprint": "fingerprint",
                    },
                )(),
            },
        )()

        response = self.client.get("/api/v1/clusters/local-kubeconfig")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_path"], "/Users/test/.kube/config")
        self.assertEqual(payload["current_context"], "sample")
        self.assertEqual(payload["server"], "https://127.0.0.1:6443")
        self.assertEqual(payload["cluster_count"], 1)
        self.assertEqual(payload["kubeconfig"], "apiVersion: v1\nkind: Config\n")

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
        discover_mock.assert_called_once_with(best_effort=True, version={"gitVersion": "v1.30.0"})

    @patch("apps.k8s_gateway.services.KubernetesClient.discover")
    @patch("apps.k8s_gateway.services.KubernetesClient.probe")
    def test_import_cluster_partial_discovery_keeps_health_check_success(self, probe_mock, discover_mock):
        probe_mock.return_value = {"version": {"gitVersion": "v1.30.0"}, "latency_ms": 12}
        discover_mock.return_value = {
            "groups": [{"group": "core", "version": "v1", "preferred_version": "v1", "resources": []}],
            "resource_index": {},
            "supports_exec": False,
            "warnings": [
                {
                    "group": "metrics.k8s.io",
                    "version": "v1beta1",
                    "path": "/apis/metrics.k8s.io/v1beta1",
                    "message": "连接集群超时: The read operation timed out",
                    "status_code": 504,
                }
            ],
            "partial": True,
        }

        response = self.client.post(
            "/api/v1/clusters",
            data={
                "name": "imported-cluster-partial-discovery",
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
        self.assertIn("Discovery 已同步", payload["health"]["message"])
        self.assertIn("跳过 1 个异常接口", payload["health"]["message"])
        discover_mock.assert_called_once_with(best_effort=True, version={"gitVersion": "v1.30.0"})

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

    @patch("apps.k8s_gateway.services.KubernetesClient.discover")
    @patch("apps.k8s_gateway.services.KubernetesClient.probe")
    def test_manual_health_check_partial_discovery_returns_success(self, probe_mock, discover_mock):
        probe_mock.return_value = {"version": {"gitVersion": "v1.30.1"}, "latency_ms": 9}
        discover_mock.return_value = {
            "groups": [{"group": "core", "version": "v1", "preferred_version": "v1", "resources": []}],
            "resource_index": {},
            "supports_exec": False,
            "warnings": [
                {
                    "group": "metrics.k8s.io",
                    "version": "v1beta1",
                    "path": "/apis/metrics.k8s.io/v1beta1",
                    "message": "连接集群超时: The read operation timed out",
                    "status_code": 504,
                }
            ],
            "partial": True,
        }

        response = self.client.post(f"/api/v1/clusters/{self.cluster.id}/health-check", format="json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], ClusterStatus.READY)
        self.assertEqual(payload["health_state"], ClusterHealthState.HEALTHY)
        self.assertIn("跳过 1 个异常接口", payload["health"]["message"])
        discover_mock.assert_called_once_with(best_effort=True, version={"gitVersion": "v1.30.1"})
