from __future__ import annotations

import time
from datetime import timedelta

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.clusters.models import Cluster
from apps.iam.models import User

from .models import StreamSession
from .terminal import KubernetesExecWebSocket, terminal_hub


class FakeExecConnection:
    def __init__(
        self,
        *,
        events: list[tuple[int, str]] | None = None,
        linger: bool = False,
        final_returncode: int | None = 0,
        final_status_message: str = "",
    ):
        self.events = list(events or [])
        self.linger = linger
        self.final_returncode = final_returncode
        self.returncode = None
        self.status_message = ""
        self.final_status_message = final_status_message
        self.connected = False
        self.stdin_payloads: list[str] = []
        self.resize_events: list[tuple[int, int]] = []

    def connect(self):
        self.connected = True

    def is_open(self) -> bool:
        return self.connected

    def read_frame(self, *, timeout: float | None = 0.0):
        if self.events:
            return self.events.pop(0)
        if not self.linger and self.connected:
            self.connected = False
            self.returncode = self.final_returncode
            self.status_message = self.final_status_message
        return None

    def write_stdin(self, data: str):
        self.stdin_payloads.append(data)

    def resize(self, *, rows: int, cols: int):
        self.resize_events.append((rows, cols))

    def close(self):
        self.connected = False


class StreamSessionAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="tester@example.com", password="secret123")
        self.other_user = User.objects.create_user(email="other@example.com", password="secret123")
        self.staff_user = User.objects.create_user(email="admin@example.com", password="secret123", is_staff=True)

        self.cluster = Cluster.objects.create(
            name="demo",
            slug="demo",
            environment="development",
            server="https://127.0.0.1:6443",
            default_context="demo",
        )

        self.user_client = APIClient()
        self.user_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.user).key}")

        self.staff_client = APIClient()
        self.staff_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.staff_user).key}")

    def create_session(self, *, owner, resource_name, status="success", namespace="default"):
        return StreamSession.objects.create(
            stream_type="exec",
            status=status,
            cluster=self.cluster,
            owner=owner,
            namespace=namespace,
            resource_name=resource_name,
            container_name="demo",
            command=["id"],
            exit_code=0 if status == "success" else 1,
            output_excerpt=f"{resource_name}:{status}",
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_regular_user_only_sees_own_sessions(self):
        own_session = self.create_session(owner=self.user, resource_name="demo-pod")
        self.create_session(owner=self.other_user, resource_name="demo-pod")

        response = self.user_client.get(
            f"/api/v1/streams/sessions?cluster={self.cluster.id}&stream_type=exec&resource_name=demo-pod"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], own_session.id)

    def test_staff_user_can_filter_and_view_all_sessions(self):
        self.create_session(owner=self.user, resource_name="demo-pod", status="success")
        failed_session = self.create_session(owner=self.other_user, resource_name="demo-pod", status="error")
        self.create_session(owner=self.other_user, resource_name="other-pod", status="success")

        response = self.staff_client.get(
            f"/api/v1/streams/sessions?cluster={self.cluster.id}&stream_type=exec&namespace=default&resource_name=demo-pod&status=error"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], failed_session.id)

    def test_owner_can_close_session(self):
        session = self.create_session(owner=self.user, resource_name="demo-pod", status="running")

        response = self.user_client.post(
            f"/api/v1/streams/sessions/{session.id}/close",
            {"status": "stopped"},
            format="json",
        )

        session.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.status, "stopped")
        self.assertIsNotNone(session.closed_at)

    def test_regular_user_cannot_close_other_session(self):
        session = self.create_session(owner=self.other_user, resource_name="demo-pod", status="running")

        response = self.user_client.post(
            f"/api/v1/streams/sessions/{session.id}/close",
            {"status": "stopped"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    @patch("apps.streams.api.terminal_hub")
    def test_owner_can_read_terminal_output(self, terminal_hub):
        session = StreamSession.objects.create(
            stream_type="terminal",
            status="running",
            cluster=self.cluster,
            owner=self.user,
            namespace="default",
            resource_name="demo-pod",
            container_name="demo",
            command=["/bin/sh"],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        terminal_hub.read_output.return_value = {
            "text": "demo output",
            "cursor": 11,
            "status": "running",
            "closed": False,
            "exit_code": None,
            "closed_at": None,
        }

        response = self.user_client.get(f"/api/v1/streams/sessions/{session.id}/output?cursor=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "demo output")
        terminal_hub.read_output.assert_called_once_with(session_id=session.id, cursor=0)

    @patch("apps.streams.api.terminal_hub")
    def test_owner_can_send_terminal_input(self, terminal_hub):
        session = StreamSession.objects.create(
            stream_type="terminal",
            status="running",
            cluster=self.cluster,
            owner=self.user,
            namespace="default",
            resource_name="demo-pod",
            container_name="demo",
            command=["/bin/sh"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.user_client.post(
            f"/api/v1/streams/sessions/{session.id}/input",
            {"input": "echo hello\n"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        terminal_hub.write_input.assert_called_once_with(session_id=session.id, data="echo hello\n")

    @patch("apps.streams.api.terminal_hub")
    def test_owner_can_resize_terminal(self, terminal_hub):
        session = StreamSession.objects.create(
            stream_type="terminal",
            status="running",
            cluster=self.cluster,
            owner=self.user,
            namespace="default",
            resource_name="demo-pod",
            container_name="demo",
            command=["/bin/sh"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.user_client.post(
            f"/api/v1/streams/sessions/{session.id}/resize",
            {"rows": 40, "cols": 140},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        terminal_hub.resize.assert_called_once_with(session_id=session.id, rows=40, cols=140)


class TerminalHubTests(TransactionTestCase):
    def setUp(self):
        self.cluster = Cluster.objects.create(
            name="terminal-demo",
            slug="terminal-demo",
            environment="development",
            server="https://127.0.0.1:6443",
            default_context="demo",
        )

    def tearDown(self):
        for session_id in list(terminal_hub._sessions.keys()):
            terminal_hub.close_session(session_id=session_id, status="stopped")

    def create_terminal_session(self) -> StreamSession:
        return StreamSession.objects.create(
            stream_type="terminal",
            status="running",
            cluster=self.cluster,
            namespace="default",
            resource_name="demo-pod",
            container_name="demo",
            command=["/bin/sh"],
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def wait_for(self, predicate, *, timeout: float = 2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("等待终端状态更新超时。")

    def test_open_session_streams_remote_output(self):
        session = self.create_terminal_session()
        connection = FakeExecConnection(
            events=[(KubernetesExecWebSocket.STDOUT_CHANNEL, "hello from pod\n")],
            linger=True,
        )

        payload = terminal_hub.open_session(
            session=session,
            connection=connection,
            namespace="default",
            container="demo",
            shell="/bin/sh",
            rows=32,
            cols=120,
        )

        self.assertEqual(payload["shell"], "/bin/sh")
        self.assertEqual(connection.resize_events[0], (32, 120))

        self.wait_for(lambda: terminal_hub.read_output(session_id=session.id, cursor=0)["cursor"] > 0)
        output = terminal_hub.read_output(session_id=session.id, cursor=0)
        self.assertIn("hello from pod", output["text"])

    def test_write_input_and_resize_delegate_to_remote_stream(self):
        session = self.create_terminal_session()
        connection = FakeExecConnection(linger=True)

        terminal_hub.open_session(
            session=session,
            connection=connection,
            namespace="default",
            container="demo",
            shell="/bin/sh",
            rows=24,
            cols=80,
        )

        terminal_hub.write_input(session_id=session.id, data="echo hi\n")
        terminal_hub.resize(session_id=session.id, rows=40, cols=140)

        self.assertEqual(connection.stdin_payloads, ["echo hi\n"])
        self.assertEqual(connection.resize_events[-1], (40, 140))

    def test_remote_exec_failure_updates_session_status(self):
        session = self.create_terminal_session()
        connection = FakeExecConnection(
            final_returncode=127,
            final_status_message='exec: "/bin/bash": stat /bin/bash: no such file or directory',
        )

        terminal_hub.open_session(
            session=session,
            connection=connection,
            namespace="default",
            container="demo",
            shell="/bin/bash",
            rows=32,
            cols=120,
        )

        self.wait_for(lambda: StreamSession.objects.filter(pk=session.id, closed_at__isnull=False).exists())
        session.refresh_from_db()

        self.assertEqual(session.status, "error")
        self.assertEqual(session.exit_code, 127)
        self.assertIn("no such file or directory", session.output_excerpt)
