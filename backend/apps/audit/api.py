from rest_framework import generics, serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_display = serializers.CharField(source="actor.display_name", read_only=True)
    actor_email = serializers.CharField(source="actor.email", read_only=True)
    cluster_name = serializers.CharField(source="cluster.name", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "event_type",
            "severity",
            "status",
            "request_id",
            "target",
            "metadata",
            "actor_display",
            "actor_email",
            "cluster_name",
            "created_at",
        ]


class AuditEventListView(generics.ListAPIView):
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        queryset = AuditEvent.objects.select_related("actor", "cluster")
        limit = min(int(self.request.query_params.get("limit", 20)), 100)
        return queryset[:limit]

