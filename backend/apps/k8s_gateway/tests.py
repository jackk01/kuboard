from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.clusters.models import Cluster, ClusterCapability, ClusterCredential, ClusterHealthStatus
from apps.iam.models import User
from apps.streams.models import StreamSession
from .services import KubernetesAPIError, KubernetesClient, build_resource_path


class FakeExecStreamConnection:
    STDOUT_CHANNEL = 1
    STDERR_CHANNEL = 2

    def __init__(self, events=None, *, linger=False, final_returncode=0, final_status_message=""):
        self.events = list(events or [])
        self.linger = linger
        self.final_returncode = final_returncode
        self.final_status_message = final_status_message
        self.returncode = None
        self.status_message = ""
        self.connected = False

    def connect(self):
        self.connected = True

    def is_open(self):
        return self.connected

    def read_frame(self, *, timeout=0.0):
        if self.events:
            return self.events.pop(0)
        if not self.linger and self.connected:
            self.connected = False
            self.returncode = self.final_returncode
            self.status_message = self.final_status_message
        return None

    def close(self):
        self.connected = False


class KubernetesGatewayServiceTests(TestCase):
    def create_service_client(self, *, server="https://master:6443"):
        index = Cluster.objects.count() + 1
        cluster = Cluster.objects.create(
            name=f"demo-service-{index}",
            slug=f"demo-service-{index}",
            environment="dev",
            server=server,
            default_context="demo",
        )
        credential = ClusterCredential(cluster=cluster, active_context="demo", fingerprint=f"test-{index}")
        credential.set_kubeconfig(
            f"""
apiVersion: v1
kind: Config
clusters:
  - name: demo
    cluster:
      server: {server}
users:
  - name: demo
    user:
      token: demo-token
contexts:
  - name: demo
    context:
      cluster: demo
      user: demo
current-context: demo
"""
        )
        credential.save()
        ClusterCapability.objects.create(cluster=cluster, supports_exec=True)
        ClusterHealthStatus.objects.create(cluster=cluster)
        return KubernetesClient(cluster)

    def test_build_pod_exec_stream_uses_websocket_scheme_and_preserves_server_path(self):
        client = self.create_service_client(server="https://master:6443/prefix")

        connection = client._build_pod_exec_stream(
            name="demo-pod",
            namespace="default",
            container="demo",
            command=["/bin/sh"],
        )

        self.assertTrue(connection.url.startswith("wss://master:6443/prefix/api/v1/namespaces/default/pods/demo-pod/exec?"))
        self.assertIn("container=demo", connection.url)
        self.assertIn("command=%2Fbin%2Fsh", connection.url)

    def test_build_resource_path_for_namespaced_resource(self):
        path = build_resource_path(
            group="apps",
            version="v1",
            resource="deployments",
            namespaced=True,
            namespace="demo",
        )
        self.assertEqual(path, "/apis/apps/v1/namespaces/demo/deployments")

    def test_build_resource_path_for_cluster_scoped_resource(self):
        path = build_resource_path(
            group="rbac.authorization.k8s.io",
            version="v1",
            resource="clusterroles",
            namespaced=False,
        )
        self.assertEqual(path, "/apis/rbac.authorization.k8s.io/v1/clusterroles")

    def test_build_resource_path_for_core_resource(self):
        path = build_resource_path(
            group="core",
            version="v1",
            resource="pods",
            namespaced=True,
            namespace="default",
        )
        self.assertEqual(path, "/api/v1/namespaces/default/pods")

    def test_kubernetes_client_disables_env_proxy_for_direct_cluster_access(self):
        cluster = Cluster.objects.create(
            name="demo-service",
            slug="demo-service",
            environment="dev",
            server="https://master:6443",
            default_context="demo",
        )
        credential = ClusterCredential(cluster=cluster, active_context="demo", fingerprint="test")
        credential.set_kubeconfig(
            """
apiVersion: v1
kind: Config
clusters:
  - name: demo
    cluster:
      server: https://master:6443
users:
  - name: demo
    user:
      token: demo-token
contexts:
  - name: demo
    context:
      cluster: demo
      user: demo
current-context: demo
"""
        )
        credential.save()
        ClusterCapability.objects.create(cluster=cluster)
        ClusterHealthStatus.objects.create(cluster=cluster)

        client = KubernetesClient(cluster)
        opener = MagicMock()
        response = MagicMock()
        response.read.return_value = b'{"gitVersion": "v1.30.0"}'
        opener.open.return_value.__enter__.return_value = response

        with patch("apps.k8s_gateway.services.request.build_opener", return_value=opener) as build_opener_mock:
            payload = client.request_json("/version")

        self.assertEqual(payload["gitVersion"], "v1.30.0")
        handlers = build_opener_mock.call_args.args
        self.assertEqual(type(handlers[0]).__name__, "ProxyHandler")
        self.assertEqual(getattr(handlers[0], "proxies", None), {})

    def test_exec_pod_command_uses_stream_and_returns_output(self):
        client = self.create_service_client()
        connection = FakeExecStreamConnection(
            events=[
                (1, "uid=0(root)\n"),
                (2, "warning line\n"),
            ],
            final_returncode=0,
        )

        with patch.object(client, "_prepare_pod_exec", return_value="default"), patch.object(
            client,
            "_build_pod_exec_stream",
            return_value=connection,
        ) as build_stream_mock:
            payload = client.exec_pod_command(
                name="demo-pod",
                namespace="default",
                container="demo",
                shell_command="id",
                timeout_seconds=10,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["stdout"], "uid=0(root)\n")
        self.assertEqual(payload["stderr"], "warning line\n")
        build_stream_mock.assert_called_once_with(
            name="demo-pod",
            namespace="default",
            container="demo",
            command=["/bin/sh", "-lc", "id"],
            stdin=False,
            tty=False,
        )

    def test_exec_pod_command_includes_stream_status_message_on_failure(self):
        client = self.create_service_client()
        connection = FakeExecStreamConnection(
            final_returncode=127,
            final_status_message='exec: "/bin/bash": stat /bin/bash: no such file or directory',
        )

        with patch.object(client, "_prepare_pod_exec", return_value="default"), patch.object(
            client,
            "_build_pod_exec_stream",
            return_value=connection,
        ):
            payload = client.exec_pod_command(
                name="demo-pod",
                namespace="default",
                container="demo",
                shell_command="bash",
                timeout_seconds=10,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["exit_code"], 127)
        self.assertIn("no such file or directory", payload["stderr"])

    def test_exec_pod_command_times_out_when_stream_does_not_finish(self):
        client = self.create_service_client()
        connection = FakeExecStreamConnection(linger=True)

        with patch.object(client, "_prepare_pod_exec", return_value="default"), patch.object(
            client,
            "_build_pod_exec_stream",
            return_value=connection,
        ), patch("apps.k8s_gateway.services.time.monotonic", side_effect=[0.0, 3.1]):
            with self.assertRaises(KubernetesAPIError) as context:
                client.exec_pod_command(
                    name="demo-pod",
                    namespace="default",
                    container="demo",
                    shell_command="sleep 10",
                    timeout_seconds=3,
                )

        self.assertIn("Pod Exec 执行超时", str(context.exception))


class KubernetesGatewayAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tester@example.com", password="secret123")
        token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.cluster = Cluster.objects.create(
            name="demo",
            slug="demo",
            environment="development",
            server="https://127.0.0.1:6443",
            default_context="demo",
        )
        credential = ClusterCredential(cluster=self.cluster, active_context="demo", fingerprint="test")
        credential.set_kubeconfig(
            """
apiVersion: v1
kind: Config
clusters:
  - name: demo
    cluster:
      server: https://127.0.0.1:6443
users:
  - name: demo
    user:
      token: demo-token
contexts:
  - name: demo
    context:
      cluster: demo
      user: demo
current-context: demo
"""
        )
        credential.save()
        ClusterCapability.objects.create(cluster=self.cluster)
        ClusterHealthStatus.objects.create(cluster=self.cluster)

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_discovery_endpoint_returns_payload(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.discover.return_value = {
            "version": {"gitVersion": "v1.30.0"},
            "context": {"name": "demo", "server": "https://127.0.0.1:6443", "default_namespace": "default"},
            "groups": [
                {
                    "group": "core",
                    "version": "v1",
                    "preferred_version": "v1",
                    "resources": [{"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list"]}],
                }
            ],
            "namespaces": [{"name": "default", "phase": "Active"}],
            "resource_index": {"core::v1::pods": {"name": "pods", "kind": "Pod", "namespaced": True, "verbs": ["get", "list"]}},
        }

        response = self.client.get(f"/api/v1/clusters/{self.cluster.id}/discovery")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"]["gitVersion"], "v1.30.0")
        mocked_client.sync_capability_from_discovery.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_list_endpoint_returns_items(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.list_resources.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "pods",
                "kind": "Pod",
                "namespaced": True,
                "namespace": "default",
                "verbs": ["get", "list"],
            },
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {"name": "demo-pod", "namespace": "default"},
                }
            ],
            "metadata": {"count": 1, "continue": "", "resource_version": "1"},
        }

        response = self.client.get(f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods?namespace=default")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metadata"]["count"], 1)
        mocked_client.list_resources.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_schema_endpoint_returns_schema(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.get_resource_schema.return_value = {
            "resource": {
                "group": "apps",
                "version": "v1",
                "name": "deployments",
                "kind": "Deployment",
                "namespaced": True,
                "verbs": ["get", "list", "patch"],
                "short_names": ["deploy"],
            },
            "schema": {
                "type": "object",
                "properties": {
                    "spec": {
                        "type": "object",
                        "properties": {
                            "replicas": {"type": "integer"},
                        },
                    }
                },
            },
            "schema_name": "io.k8s.api.apps.v1.Deployment",
            "source": "openapi-v3",
            "metadata": {},
        }

        response = self.client.get(f"/api/v1/clusters/{self.cluster.id}/schemas/apps/v1/deployments")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "openapi-v3")
        self.assertEqual(response.json()["schema"]["properties"]["spec"]["type"], "object")
        mocked_client.get_resource_schema.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_permissions_endpoint_returns_access_matrix(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.check_resource_permissions.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "pods",
                "kind": "Pod",
                "namespaced": True,
            },
            "scope": {"namespace": "default", "name": "demo-pod"},
            "verbs": {
                "get": {"allowed": True, "denied": False, "reason": "", "evaluation_error": ""},
                "list": {"allowed": True, "denied": False, "reason": "", "evaluation_error": ""},
                "watch": {"allowed": True, "denied": False, "reason": "", "evaluation_error": ""},
                "create": {"allowed": False, "denied": True, "reason": "rbac", "evaluation_error": ""},
                "update": {"allowed": False, "denied": True, "reason": "rbac", "evaluation_error": ""},
                "patch": {"allowed": True, "denied": False, "reason": "", "evaluation_error": ""},
                "delete": {"allowed": False, "denied": True, "reason": "rbac", "evaluation_error": ""},
            },
            "subresources": {
                "log": {"allowed": True, "denied": False, "reason": "", "evaluation_error": ""}
            },
        }

        response = self.client.get(
            f"/api/v1/clusters/{self.cluster.id}/permissions/resources/core/v1/pods?namespace=default&name=demo-pod"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verbs"]["patch"]["allowed"])
        self.assertTrue(response.json()["subresources"]["log"]["allowed"])
        mocked_client.check_resource_permissions.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_watch_endpoint_returns_events(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.watch_resources.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "pods",
                "kind": "Pod",
                "namespaced": True,
                "namespace": "default",
                "verbs": ["get", "list", "watch"],
            },
            "events": [
                {
                    "type": "MODIFIED",
                    "object": {"metadata": {"name": "demo-pod", "namespace": "default", "resourceVersion": "12"}},
                    "metadata": {
                        "kind": "Pod",
                        "name": "demo-pod",
                        "namespace": "default",
                        "resource_version": "12",
                    },
                }
            ],
            "metadata": {
                "count": 1,
                "resource_version": "10",
                "next_resource_version": "12",
                "timeout_seconds": 8,
            },
        }

        response = self.client.get(
            f"/api/v1/clusters/{self.cluster.id}/watch/resources/core/v1/pods?namespace=default&resource_version=10&timeout_seconds=8"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metadata"]["next_resource_version"], "12")
        self.assertEqual(response.json()["events"][0]["type"], "MODIFIED")
        mocked_client.watch_resources.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_permission_rules_endpoint_returns_rules(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.get_self_subject_rules.return_value = {
            "namespace": "default",
            "incomplete": False,
            "evaluation_error": "",
            "resource_rules": [
                {"verbs": ["get", "list"], "apiGroups": [""], "resources": ["pods"]},
            ],
            "non_resource_rules": [],
        }

        response = self.client.get(
            f"/api/v1/clusters/{self.cluster.id}/permissions/rules?namespace=default"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["namespace"], "default")
        self.assertEqual(len(response.json()["resource_rules"]), 1)
        mocked_client.get_self_subject_rules.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_detail_endpoint_returns_yaml(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.get_resource.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "pods",
                "kind": "Pod",
                "namespaced": True,
                "namespace": "default",
                "verbs": ["get", "list"],
            },
            "object": {"metadata": {"name": "demo-pod", "namespace": "default"}},
            "yaml": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: demo-pod\n",
            "metadata": {"name": "demo-pod", "namespace": "default", "uid": "", "resource_version": "1", "generation": None},
        }

        response = self.client.get(f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods/demo-pod?namespace=default")

        self.assertEqual(response.status_code, 200)
        self.assertIn("yaml", response.json())
        mocked_client.get_resource.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_create_endpoint_returns_created_detail(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.create_resource.return_value = {
            "resource": {
                "group": "apps",
                "version": "v1",
                "name": "deployments",
                "kind": "Deployment",
                "namespaced": True,
                "namespace": "default",
                "verbs": ["get", "list", "create"],
            },
            "object": {"metadata": {"name": "demo-web", "namespace": "default"}},
            "yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: demo-web\n",
            "metadata": {"name": "demo-web", "namespace": "default", "uid": "", "resource_version": "1", "generation": 1},
        }

        response = self.client.post(
            f"/api/v1/clusters/{self.cluster.id}/resources/apps/v1/deployments?namespace=default",
            {
                "manifest": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: demo-web\nspec: {}\n",
                "dry_run": False,
                "force": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["metadata"]["name"], "demo-web")
        mocked_client.create_resource.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_apply_endpoint_returns_updated_yaml(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.apply_resource.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "configmaps",
                "kind": "ConfigMap",
                "namespaced": True,
                "namespace": "default",
                "verbs": ["get", "list", "patch"],
            },
            "object": {"metadata": {"name": "demo-config", "namespace": "default"}},
            "yaml": "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo-config\n",
            "metadata": {"name": "demo-config", "namespace": "default", "uid": "", "resource_version": "2", "generation": None},
        }

        response = self.client.post(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/configmaps/demo-config/apply?namespace=default",
            {"manifest": "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: demo-config\n", "dry_run": False, "force": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metadata"]["name"], "demo-config")
        mocked_client.apply_resource.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_pod_logs_endpoint_returns_text(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.get_pod_logs.return_value = {
            "pod": "demo-pod",
            "namespace": "default",
            "container": "demo",
            "tail_lines": 120,
            "previous": False,
            "timestamps": True,
            "text": "2026-03-21T10:00:00Z started\n2026-03-21T10:00:01Z ready\n",
            "cursor": {"since_time": "2026-03-21T10:00:01Z", "line_count": 2},
        }

        response = self.client.get(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods/demo-pod/logs?namespace=default&container=demo&tail_lines=120"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("ready", response.json()["text"])
        mocked_client.get_pod_logs.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_pod_logs_follow_creates_running_session(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.get_pod_logs.return_value = {
            "pod": "demo-pod",
            "namespace": "default",
            "container": "demo",
            "tail_lines": 200,
            "previous": False,
            "timestamps": True,
            "text": "2026-03-21T10:00:02Z probe ok\n",
            "cursor": {"since_time": "2026-03-21T10:00:02Z", "line_count": 1},
        }

        response = self.client.get(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods/demo-pod/logs?namespace=default&container=demo&follow=true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["follow"])
        self.assertEqual(response.json()["session"]["status"], "running")
        self.assertEqual(StreamSession.objects.filter(stream_type="logs").count(), 1)
        mocked_client.get_pod_logs.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_pod_exec_endpoint_returns_output_and_creates_session(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.exec_pod_command.return_value = {
            "pod": "demo-pod",
            "namespace": "default",
            "container": "demo",
            "command": ["/bin/sh", "-lc", "id"],
            "shell_command": "id",
            "exit_code": 0,
            "success": True,
            "stdout": "uid=0(root) gid=0(root)\n",
            "stderr": "",
            "duration_ms": 85,
            "output_excerpt": "uid=0(root) gid=0(root)",
        }

        response = self.client.post(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods/demo-pod/exec",
            {"namespace": "default", "container": "demo", "shell_command": "id", "timeout_seconds": 10},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["exit_code"], 0)
        self.assertEqual(StreamSession.objects.filter(stream_type="exec").count(), 1)
        mocked_client.exec_pod_command.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_pod_terminal_endpoint_opens_terminal_session(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.open_pod_terminal.return_value = {
            "pod": "demo-pod",
            "namespace": "default",
            "container": "demo",
            "shell": "/bin/sh",
            "terminal": {"rows": 32, "cols": 120},
            "text": "",
            "cursor": 0,
        }

        response = self.client.post(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/pods/demo-pod/terminal",
            {"namespace": "default", "container": "demo", "shell": "/bin/sh", "rows": 32, "cols": 120},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["shell"], "/bin/sh")
        self.assertEqual(StreamSession.objects.filter(stream_type="terminal").count(), 1)
        mocked_client.open_pod_terminal.assert_called_once()

    @patch("apps.k8s_gateway.api.KubernetesClient")
    def test_resource_delete_endpoint_returns_status(self, client_class):
        mocked_client = client_class.return_value
        mocked_client.delete_resource.return_value = {
            "resource": {
                "group": "core",
                "version": "v1",
                "name": "configmaps",
                "kind": "ConfigMap",
                "namespaced": True,
                "namespace": "default",
            },
            "result": {"status": "Success"},
        }

        response = self.client.delete(
            f"/api/v1/clusters/{self.cluster.id}/resources/core/v1/configmaps/demo-config?namespace=default"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["status"], "Success")
        mocked_client.delete_resource.assert_called_once()
