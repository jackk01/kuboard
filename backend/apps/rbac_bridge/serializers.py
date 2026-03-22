from rest_framework import serializers

from apps.clusters.models import Cluster

from .models import SubjectMapping


class SubjectMappingSerializer(serializers.ModelSerializer):
    cluster_name = serializers.CharField(source="cluster.name", read_only=True)
    kubernetes_groups = serializers.ListField(
        child=serializers.CharField(max_length=128),
        allow_empty=True,
        required=False,
    )

    class Meta:
        model = SubjectMapping
        fields = [
            "id",
            "source_type",
            "source_identifier",
            "kubernetes_username",
            "kubernetes_groups",
            "cluster",
            "cluster_name",
            "is_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "cluster_name", "created_at", "updated_at"]

    def validate_source_type(self, value):
        if value not in {"user", "group"}:
            raise serializers.ValidationError("source_type 仅支持 user 或 group。")
        return value


class ClusterImpersonationSerializer(serializers.Serializer):
    cluster_id = serializers.UUIDField()
    supports_impersonation = serializers.BooleanField()

    def validate_cluster_id(self, value):
        if not Cluster.objects.filter(pk=value).exists():
            raise serializers.ValidationError("目标集群不存在。")
        return value
