from rest_framework import serializers

from .models import StreamSession


class StreamSessionSerializer(serializers.ModelSerializer):
    cluster_name = serializers.CharField(source="cluster.name", read_only=True)
    owner_email = serializers.CharField(source="owner.email", read_only=True, allow_null=True)

    class Meta:
        model = StreamSession
        fields = [
            "id",
            "stream_type",
            "status",
            "cluster",
            "cluster_name",
            "owner",
            "owner_email",
            "namespace",
            "resource_name",
            "container_name",
            "command",
            "exit_code",
            "output_excerpt",
            "expires_at",
            "closed_at",
            "created_at",
        ]
