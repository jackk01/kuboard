from __future__ import annotations

import base64
from bisect import bisect_right
import json
import os
import select
import ssl
import tempfile
import threading
import time
from dataclasses import dataclass, field

import yaml
from django.utils import timezone
from websocket import ABNF, WebSocket, WebSocketConnectionClosedException

from .models import StreamSession


class TerminalSessionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


ALLOWED_TERMINAL_SHELLS = {
    "auto": "auto",
    "sh": "/bin/sh",
    "/bin/sh": "/bin/sh",
    "bash": "/bin/bash",
    "/bin/bash": "/bin/bash",
}

AUTO_TERMINAL_SHELL_COMMAND = [
    "/bin/sh",
    "-lc",
    "if command -v bash >/dev/null 2>&1; then exec bash; else exec sh; fi",
]


def normalize_terminal_shell(shell: str) -> str:
    normalized = ALLOWED_TERMINAL_SHELLS.get((shell or "/bin/sh").strip())
    if not normalized:
        raise TerminalSessionError("当前终端仅允许 auto、/bin/sh 或 /bin/bash。", status_code=400)
    return normalized


def build_terminal_shell_command(shell: str) -> list[str]:
    normalized_shell = normalize_terminal_shell(shell)
    if normalized_shell == "auto":
        return list(AUTO_TERMINAL_SHELL_COMMAND)
    return [normalized_shell]


class KubernetesExecWebSocket:
    STDIN_CHANNEL = 0
    STDOUT_CHANNEL = 1
    STDERR_CHANNEL = 2
    ERROR_CHANNEL = 3
    RESIZE_CHANNEL = 4

    def __init__(
        self,
        *,
        url: str,
        headers: list[str],
        verify_ssl: bool = True,
        ca_cert_data: str | None = None,
        client_cert_data: str | None = None,
        client_key_data: str | None = None,
        tls_server_name: str | None = None,
    ):
        self.url = url
        self.headers = headers
        self.verify_ssl = verify_ssl
        self.ca_cert_data = ca_cert_data
        self.client_cert_data = client_cert_data
        self.client_key_data = client_key_data
        self.tls_server_name = tls_server_name
        self.sock: WebSocket | None = None
        self._connected = False
        self._returncode: int | None = None
        self._status_message = ""
        self._temp_files: list[str] = []
        self._send_lock = threading.Lock()
        self._close_lock = threading.Lock()

    def _write_temp_file(self, encoded: str, suffix: str) -> str:
        fd, path = tempfile.mkstemp(prefix="kuboard-terminal-", suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as file_obj:
                file_obj.write(base64.b64decode(encoded))
        except Exception:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            raise
        self._temp_files.append(path)
        return path

    def _build_ssl_options(self) -> dict[str, object]:
        ssl_options: dict[str, object] = {
            "cert_reqs": ssl.CERT_REQUIRED if self.verify_ssl else ssl.CERT_NONE,
        }
        if self.ca_cert_data:
            ssl_options["ca_certs"] = self._write_temp_file(self.ca_cert_data, ".crt")
        if self.client_cert_data:
            ssl_options["certfile"] = self._write_temp_file(self.client_cert_data, ".pem")
        if self.client_key_data:
            ssl_options["keyfile"] = self._write_temp_file(self.client_key_data, ".key")
        if self.tls_server_name:
            ssl_options["server_hostname"] = self.tls_server_name
        return ssl_options

    def connect(self):
        try:
            self.sock = WebSocket(
                sslopt=self._build_ssl_options(),
                skip_utf8_validation=False,
                enable_multithread=True,
            )
            self.sock.connect(
                self.url,
                header=[*self.headers, "sec-websocket-protocol: v4.channel.k8s.io"],
            )
            self._connected = True
        except Exception as exc:
            self.close()
            raise TerminalSessionError(f"无法连接 Kubernetes Exec Stream: {exc}", status_code=502) from exc

    def is_open(self) -> bool:
        return bool(self._connected and self.sock and self.sock.connected)

    def _poll_ready(self, timeout: float | None) -> bool:
        if not self.is_open() or not self.sock or not self.sock.sock:
            self._connected = False
            return False

        socket_obj = self.sock.sock
        if hasattr(select, "poll"):
            poller = select.poll()
            poller.register(socket_obj, select.POLLIN)
            try:
                wait_time = None if timeout is None else max(0, int(timeout * 1000))
                events = poller.poll(wait_time)
                return bool(events)
            finally:
                poller.unregister(socket_obj)

        readable, _, _ = select.select((socket_obj,), (), (), timeout)
        return bool(readable)

    def _record_status(self, payload: str):
        message = payload.strip()
        if not message:
            return

        try:
            data = yaml.safe_load(message)
        except yaml.YAMLError:
            self._status_message = message
            self._returncode = 1
            return

        if not isinstance(data, dict):
            self._status_message = message
            self._returncode = 1
            return

        self._status_message = str(data.get("message") or message)
        if data.get("status") == "Success":
            self._returncode = 0
            return

        details = data.get("details") or {}
        causes = details.get("causes") or []
        exit_code_text = ""
        if causes and isinstance(causes[0], dict):
            exit_code_text = str(causes[0].get("message") or "")
        try:
            self._returncode = int(exit_code_text)
        except (TypeError, ValueError):
            self._returncode = 1

    def read_frame(self, *, timeout: float | None = 0.0) -> tuple[int, str] | None:
        if not self.is_open():
            return None
        try:
            if not self._poll_ready(timeout):
                if not self.sock or not self.sock.connected:
                    self._connected = False
                return None
            if not self.sock:
                self._connected = False
                return None

            op_code, frame = self.sock.recv_data_frame(True)
        except WebSocketConnectionClosedException:
            self._connected = False
            return None
        except Exception as exc:
            raise TerminalSessionError(f"读取 Kubernetes Exec Stream 失败: {exc}", status_code=502) from exc

        if op_code == ABNF.OPCODE_CLOSE:
            self._connected = False
            return None
        if op_code not in (ABNF.OPCODE_BINARY, ABNF.OPCODE_TEXT):
            return None

        payload = frame.data
        if isinstance(payload, bytes):
            if not payload:
                return None
            channel = payload[0]
            text = payload[1:].decode("utf-8", errors="replace")
        else:
            if not payload:
                return None
            channel = ord(payload[0])
            text = payload[1:]

        if channel == self.ERROR_CHANNEL:
            self._record_status(text)
        return channel, text

    def _send_channel(self, channel: int, data: str):
        if not self.is_open() or not self.sock:
            raise TerminalSessionError("终端会话已关闭。", status_code=410)

        with self._send_lock:
            try:
                self.sock.send(f"{chr(channel)}{data}", opcode=ABNF.OPCODE_TEXT)
            except Exception as exc:
                raise TerminalSessionError(f"写入 Kubernetes Exec Stream 失败: {exc}", status_code=502) from exc

    def write_stdin(self, data: str):
        self._send_channel(self.STDIN_CHANNEL, data)

    def resize(self, *, rows: int, cols: int):
        self._send_channel(
            self.RESIZE_CHANNEL,
            json.dumps({"Width": cols, "Height": rows}, separators=(",", ":")),
        )

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def status_message(self) -> str:
        return self._status_message

    def close(self):
        with self._close_lock:
            self._connected = False
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

            for path in self._temp_files:
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
            self._temp_files = []


@dataclass
class TerminalChunk:
    start: int
    end: int
    text: str


@dataclass
class TerminalHandle:
    session_id: int
    connection: KubernetesExecWebSocket
    shell: str
    namespace: str
    container_name: str
    chunks: list[TerminalChunk] = field(default_factory=list)
    chunk_ends: list[int] = field(default_factory=list)
    cursor: int = 0
    status: str = "running"
    exit_code: int | None = None
    output_excerpt: str = ""
    closed: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)
    updated: threading.Condition = field(init=False)

    def __post_init__(self):
        self.updated = threading.Condition(self.lock)


class TerminalHub:
    def __init__(self):
        self._sessions: dict[int, TerminalHandle] = {}
        self._lock = threading.Lock()

    def _normalize_shell(self, shell: str) -> str:
        return normalize_terminal_shell(shell)

    @staticmethod
    def _append_excerpt(previous: str, incoming: str) -> str:
        text = f"{previous}{incoming}".strip()
        return text[-4000:]

    def _store_chunk(self, handle: TerminalHandle, text: str):
        if not text:
            return
        with handle.updated:
            start = handle.cursor
            handle.cursor += len(text)
            handle.chunks.append(TerminalChunk(start=start, end=handle.cursor, text=text))
            handle.chunk_ends.append(handle.cursor)
            handle.output_excerpt = self._append_excerpt(handle.output_excerpt, text)
            handle.updated.notify_all()

    def _finalize_session(self, handle: TerminalHandle, *, status: str, exit_code: int | None):
        with handle.updated:
            if handle.closed:
                return
            handle.closed = True
            handle.status = status
            handle.exit_code = exit_code
            handle.updated.notify_all()

        StreamSession.objects.filter(pk=handle.session_id).update(
            status=status,
            exit_code=exit_code,
            output_excerpt=handle.output_excerpt[-4000:],
            closed_at=timezone.now(),
        )

        with self._lock:
            self._sessions.pop(handle.session_id, None)

        handle.connection.close()

    def _reader_loop(self, handle: TerminalHandle):
        final_status = "success"
        exit_code: int | None = None

        while True:
            try:
                event = handle.connection.read_frame(timeout=1.0)
            except TerminalSessionError as exc:
                self._store_chunk(handle, f"\n[terminal read error] {exc}\n")
                final_status = "error"
                exit_code = handle.connection.returncode
                break

            if event is None:
                if handle.connection.is_open():
                    continue
                exit_code = handle.connection.returncode
                final_status = "success" if exit_code == 0 else "error"
                status_message = handle.connection.status_message
                if final_status == "error" and status_message:
                    self._store_chunk(handle, f"\n[terminal status] {status_message}\n")
                break

            channel, text = event
            if channel in (KubernetesExecWebSocket.STDOUT_CHANNEL, KubernetesExecWebSocket.STDERR_CHANNEL):
                self._store_chunk(handle, text)

        self._finalize_session(handle, status=final_status, exit_code=exit_code)

    def open_session(
        self,
        *,
        session: StreamSession,
        connection: KubernetesExecWebSocket,
        namespace: str,
        container: str | None,
        shell: str,
        rows: int,
        cols: int,
    ) -> dict[str, object]:
        normalized_shell = self._normalize_shell(shell)
        rows = max(12, min(rows, 120))
        cols = max(40, min(cols, 240))

        try:
            connection.connect()
            connection.resize(rows=rows, cols=cols)
        except TerminalSessionError:
            connection.close()
            raise

        handle = TerminalHandle(
            session_id=session.id,
            connection=connection,
            shell=normalized_shell,
            namespace=namespace,
            container_name=container or "",
        )

        with self._lock:
            self._sessions[session.id] = handle

        thread = threading.Thread(target=self._reader_loop, args=(handle,), daemon=True)
        thread.start()

        StreamSession.objects.filter(pk=session.id).update(
            command=build_terminal_shell_command(normalized_shell),
            namespace=namespace,
            container_name=container or "",
        )

        return {
            "text": "",
            "cursor": 0,
            "shell": normalized_shell,
            "rows": rows,
            "cols": cols,
        }

    def _get_handle(self, session_id: int) -> TerminalHandle:
        with self._lock:
            handle = self._sessions.get(session_id)
        if not handle:
            raise TerminalSessionError("终端会话不存在或已结束。", status_code=404)
        return handle

    def read_output(self, *, session_id: int, cursor: int = 0, wait_timeout: float = 0.0) -> dict[str, object]:
        handle = self._get_handle(session_id)
        deadline = time.monotonic() + max(wait_timeout, 0.0)
        with handle.updated:
            while wait_timeout > 0 and cursor >= handle.cursor and not handle.closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                handle.updated.wait(timeout=remaining)

            next_cursor = handle.cursor
            start_index = bisect_right(handle.chunk_ends, cursor)
            chunks: list[str] = []
            for chunk in handle.chunks[start_index:]:
                if cursor > chunk.start:
                    chunks.append(chunk.text[cursor - chunk.start :])
                else:
                    chunks.append(chunk.text)
            text = "".join(chunks)
            status = handle.status
            closed = handle.closed
            exit_code = handle.exit_code

        if closed:
            persisted = StreamSession.objects.filter(pk=session_id).values("status", "exit_code", "closed_at").first() or {}
            status = persisted.get("status", status)
            exit_code = persisted.get("exit_code", exit_code)
            closed_at = persisted.get("closed_at")
        else:
            closed_at = None

        return {
            "text": text,
            "cursor": next_cursor,
            "status": status,
            "closed": closed,
            "exit_code": exit_code,
            "closed_at": closed_at,
        }

    def write_input(self, *, session_id: int, data: str) -> dict[str, object]:
        handle = self._get_handle(session_id)
        if handle.closed:
            raise TerminalSessionError("终端会话已关闭。", status_code=410)
        if not data:
            raise TerminalSessionError("终端输入不能为空。", status_code=400)

        handle.connection.write_stdin(data)
        return self.read_output(session_id=session_id, cursor=0 if handle.cursor == 0 else handle.cursor)

    def resize(self, *, session_id: int, rows: int, cols: int):
        handle = self._get_handle(session_id)
        if handle.closed:
            raise TerminalSessionError("终端会话已关闭。", status_code=410)
        rows = max(12, min(rows, 120))
        cols = max(40, min(cols, 240))
        handle.connection.resize(rows=rows, cols=cols)

    def close_session(self, *, session_id: int, status: str = "stopped"):
        with self._lock:
            handle = self._sessions.get(session_id)
        if not handle:
            return

        handle.connection.close()
        self._finalize_session(handle, status=status, exit_code=handle.connection.returncode)


terminal_hub = TerminalHub()
