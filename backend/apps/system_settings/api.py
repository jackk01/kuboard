from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.clusters.models import Cluster


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "kuboard-api",
                "timestamp": timezone.now(),
            }
        )


class ReadinessView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        checks = {
            "database": {"ok": True, "message": "ok"},
            "cache": {"ok": True, "message": "ok"},
        }
        status_code = 200

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:  # pragma: no cover - defensive runtime path
            checks["database"] = {"ok": False, "message": str(exc)}
            status_code = 503

        try:
            cache.set("kuboard:health:ready", "ok", timeout=5)
            if cache.get("kuboard:health:ready") != "ok":
                raise RuntimeError("redis round-trip mismatch")
        except Exception as exc:  # pragma: no cover - defensive runtime path
            checks["cache"] = {"ok": False, "message": str(exc)}
            status_code = 503

        return Response(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "service": "kuboard-api",
                "timestamp": timezone.now(),
                "checks": checks,
            },
            status=status_code,
        )


class DashboardSummaryView(APIView):
    def get(self, request):
        cluster_summary = Cluster.objects.aggregate(
            total=Count("id"),
            ready=Count("id", filter=Q(status="ready")),
        )
        recent_audit_count = AuditEvent.objects.count()
        recent_events = (
            AuditEvent.objects.select_related("cluster")
            .values("event_type", "status", "cluster__name")
            .order_by("-created_at")[:5]
        )
        return Response(
            {
                "clusters": cluster_summary,
                "recent_audit_count": recent_audit_count,
                "recent_events": list(recent_events),
                "features": {
                    "sqlite_mode": True,
                    "rbac_bridge": True,
                    "stream_hub": True,
                },
            }
        )
