from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any


_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_reserved_record_fields = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


def bind_request_id(request_id: str) -> Token[str]:
    return _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get("")


def reset_request_id(token: Token[str]) -> None:
    _request_id_var.reset(token)


def _format_timestamp(created_at: float) -> str:
    return datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00",
        "Z",
    )


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", "") or get_request_id()
        if request_id:
            payload["request_id"] = request_id

        if record.name == "uvicorn.access":
            payload.update(self._extract_uvicorn_access_fields(record))

        extras = self._extract_extra_fields(record)
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)

    def _extract_extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        extra_fields: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _reserved_record_fields or key == "request_id":
                continue
            extra_fields[key] = _normalize_value(value)
        return extra_fields

    def _extract_uvicorn_access_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        if not isinstance(record.args, tuple) or len(record.args) < 5:
            return {}

        client_addr, method, full_path, http_version, status_code = record.args[:5]
        return {
            "client_addr": _normalize_value(client_addr),
            "method": _normalize_value(method),
            "path": _normalize_value(full_path),
            "http_version": _normalize_value(http_version),
            "status_code": _normalize_value(status_code),
        }
