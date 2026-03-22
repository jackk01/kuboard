from __future__ import annotations

from typing import Any


def _extract_client_ip(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def record_audit_event(
    *,
    event_type: str,
    actor=None,
    cluster=None,
    request=None,
    severity: str = "info",
    status: str = "success",
    target: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
):
    from apps.audit.models import AuditEvent

    request_id = getattr(request, "request_id", "")
    user_agent = ""
    remote_addr = ""
    if request is not None:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        remote_addr = _extract_client_ip(request)

    return AuditEvent.objects.create(
        event_type=event_type,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        cluster=cluster,
        severity=severity,
        status=status,
        request_id=request_id,
        target=target or {},
        metadata=metadata or {},
        remote_addr=remote_addr or None,
        user_agent=user_agent[:512],
    )

