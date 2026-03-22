from __future__ import annotations

import errno
import fcntl
import os
import pty
import shutil
import struct
import subprocess
import tempfile
import termios
import threading
from dataclasses import dataclass, field

from django.utils import timezone

from .models import StreamSession


class TerminalSessionError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class TerminalChunk:
    start: int
    end: int
    text: str


@dataclass
class TerminalHandle:
    session_id: int
    process: subprocess.Popen[bytes]
    master_fd: int
    slave_fd: int
    kubeconfig_path: str
    shell: str
    namespace: str
    container_name: str
    chunks: list[TerminalChunk] = field(default_factory=list)
    cursor: int = 0
    status: str = "running"
    exit_code: int | None = None
    output_excerpt: str = ""
    closed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class TerminalHub:
    ALLOWED_SHELLS = {
        "sh": "/bin/sh",
        "/bin/sh": "/bin/sh",
        "bash": "/bin/bash",
        "/bin/bash": "/bin/bash",
    }

    def __init__(self):
        self._sessions: dict[int, TerminalHandle] = {}
        self._lock = threading.Lock()

    def _normalize_shell(self, shell: str) -> str:
        normalized = self.ALLOWED_SHELLS.get((shell or "/bin/sh").strip())
        if not normalized:
            raise TerminalSessionError("当前终端仅允许 /bin/sh 或 /bin/bash。", status_code=400)
        return normalized

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int):
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)

    @staticmethod
    def _append_excerpt(previous: str, incoming: str) -> str:
        text = f"{previous}{incoming}".strip()
        return text[-4000:]

    def _store_chunk(self, handle: TerminalHandle, text: str):
        if not text:
            return
        with handle.lock:
            start = handle.cursor
            handle.cursor += len(text)
            handle.chunks.append(TerminalChunk(start=start, end=handle.cursor, text=text))
            handle.output_excerpt = self._append_excerpt(handle.output_excerpt, text)

    def _finalize_session(self, handle: TerminalHandle, *, status: str, exit_code: int | None):
        with handle.lock:
            if handle.closed:
                return
            handle.closed = True
            handle.status = status
            handle.exit_code = exit_code

        StreamSession.objects.filter(pk=handle.session_id).update(
            status=status,
            exit_code=exit_code,
            output_excerpt=handle.output_excerpt[-4000:],
            closed_at=timezone.now(),
        )

        with self._lock:
            self._sessions.pop(handle.session_id, None)

        try:
            os.close(handle.master_fd)
        except OSError:
            pass
        try:
            os.close(handle.slave_fd)
        except OSError:
            pass
        try:
            os.remove(handle.kubeconfig_path)
        except FileNotFoundError:
            pass

    def _reader_loop(self, handle: TerminalHandle):
        while True:
            try:
                chunk = os.read(handle.master_fd, 4096)
                if not chunk:
                    break
                self._store_chunk(handle, chunk.decode("utf-8", errors="replace"))
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                self._store_chunk(handle, f"\n[terminal read error] {exc}\n")
                break

        return_code = handle.process.poll()
        if return_code is None:
            try:
                return_code = handle.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                return_code = None

        final_status = "success" if return_code == 0 else "error"
        self._finalize_session(handle, status=final_status, exit_code=return_code)

    def open_session(
        self,
        *,
        session: StreamSession,
        kubeconfig_text: str,
        kubectl_path: str,
        impersonation_username: str | None,
        impersonation_groups: list[str],
        pod_name: str,
        namespace: str,
        container: str | None,
        shell: str,
        rows: int,
        cols: int,
    ) -> dict[str, object]:
        if not shutil.which(kubectl_path):
            raise TerminalSessionError("系统中未找到 kubectl，暂时无法建立终端。", status_code=500)

        normalized_shell = self._normalize_shell(shell)
        rows = max(12, min(rows, 120))
        cols = max(40, min(cols, 240))

        kubeconfig_file = tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8")
        kubeconfig_file.write(kubeconfig_text)
        kubeconfig_file.flush()
        kubeconfig_file.close()

        master_fd, slave_fd = pty.openpty()
        self._set_winsize(slave_fd, rows, cols)

        args = [
            kubectl_path,
            "--kubeconfig",
            kubeconfig_file.name,
        ]
        if impersonation_username:
            args.extend(["--as", impersonation_username])
        for group in impersonation_groups:
            args.extend(["--as-group", group])
        args.extend(["exec", "-i", "-t", "-n", namespace, pod_name])
        if container:
            args.extend(["-c", container])
        args.extend(["--", normalized_shell])

        try:
            process = subprocess.Popen(
                args,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            try:
                os.close(master_fd)
            except OSError:
                pass
            try:
                os.close(slave_fd)
            except OSError:
                pass
            try:
                os.remove(kubeconfig_file.name)
            except FileNotFoundError:
                pass
            raise TerminalSessionError(f"无法启动终端进程: {exc}", status_code=500) from exc

        try:
            os.close(slave_fd)
        except OSError:
            pass

        handle = TerminalHandle(
            session_id=session.id,
            process=process,
            master_fd=master_fd,
            slave_fd=-1,
            kubeconfig_path=kubeconfig_file.name,
            shell=normalized_shell,
            namespace=namespace,
            container_name=container or "",
        )

        with self._lock:
            self._sessions[session.id] = handle

        thread = threading.Thread(target=self._reader_loop, args=(handle,), daemon=True)
        thread.start()

        StreamSession.objects.filter(pk=session.id).update(
            command=[normalized_shell],
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

    def read_output(self, *, session_id: int, cursor: int = 0) -> dict[str, object]:
        handle = self._get_handle(session_id)
        with handle.lock:
            next_cursor = handle.cursor
            chunks: list[str] = []
            for chunk in handle.chunks:
                if chunk.end <= cursor:
                    continue
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

        try:
            os.write(handle.master_fd, data.encode("utf-8"))
        except OSError as exc:
            raise TerminalSessionError(f"终端输入写入失败: {exc}", status_code=500) from exc

        return self.read_output(session_id=session_id, cursor=0 if handle.cursor == 0 else handle.cursor)

    def resize(self, *, session_id: int, rows: int, cols: int):
        handle = self._get_handle(session_id)
        if handle.closed:
            raise TerminalSessionError("终端会话已关闭。", status_code=410)
        rows = max(12, min(rows, 120))
        cols = max(40, min(cols, 240))
        try:
            self._set_winsize(handle.master_fd, rows, cols)
        except OSError as exc:
            raise TerminalSessionError(f"终端尺寸调整失败: {exc}", status_code=500) from exc

    def close_session(self, *, session_id: int, status: str = "stopped"):
        handle = None
        with self._lock:
            handle = self._sessions.get(session_id)
        if not handle:
            return

        if handle.process.poll() is None:
            try:
                handle.process.terminate()
                handle.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                handle.process.kill()
            except OSError:
                pass

        self._finalize_session(handle, status=status, exit_code=handle.process.poll())


terminal_hub = TerminalHub()
