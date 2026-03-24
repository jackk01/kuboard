from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers

from common.audit import record_audit_event

from .models import Cluster, ClusterCapability, ClusterCredential, ClusterHealthState, ClusterHealthStatus, ClusterStatus
from .services import validate_kubeconfig

ENVIRONMENT_CHOICES = ("test", "dev", "uat", "prod")


class ClusterHealthSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterHealthStatus
        fields = ["status", "message", "latency_ms", "last_checked_at"]


class ClusterCapabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ClusterCapability
        fields = [
            "supports_impersonation",
            "supports_server_side_apply",
            "supports_watch_bookmarks",
            "supports_exec",
            "discovered_api_groups",
            "last_synced_at",
        ]


class ClusterSerializer(serializers.ModelSerializer):
    health = ClusterHealthSerializer(read_only=True)
    capability = ClusterCapabilitySerializer(read_only=True)

    class Meta:
        model = Cluster
        fields = [
            "id",
            "name",
            "slug",
            "environment",
            "description",
            "server",
            "default_context",
            "status",
            "health_state",
            "kube_version",
            "last_error",
            "last_seen_at",
            "created_at",
            "updated_at",
            "health",
            "capability",
        ]


class ClusterDetailSerializer(ClusterSerializer):
    kubeconfig = serializers.SerializerMethodField()
    fingerprint = serializers.CharField(source="credential.fingerprint", read_only=True)
    active_context = serializers.CharField(source="credential.active_context", read_only=True)

    class Meta(ClusterSerializer.Meta):
        fields = ClusterSerializer.Meta.fields + ["kubeconfig", "fingerprint", "active_context"]

    def get_kubeconfig(self, obj: Cluster) -> str:
        return obj.credential.get_kubeconfig()


class ClusterUpdateSerializer(serializers.ModelSerializer):
    environment = serializers.ChoiceField(choices=ENVIRONMENT_CHOICES)
    kubeconfig = serializers.CharField(required=False)

    class Meta:
        model = Cluster
        fields = ["name", "environment", "description", "kubeconfig"]

    def validate(self, attrs):
        kubeconfig = attrs.get("kubeconfig")
        if kubeconfig is not None:
            self.context["inspection"] = validate_kubeconfig(kubeconfig)
        return attrs

    def validate_name(self, value):
        if not slugify(value):
            raise serializers.ValidationError("集群名称需要包含可生成 slug 的字符。")
        return value

    @transaction.atomic
    def update(self, instance: Cluster, validated_data):
        inspection = self.context.get("inspection")
        kubeconfig = validated_data.pop("kubeconfig", None)

        for field in ["name", "environment", "description"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        if inspection and kubeconfig is not None:
            instance.server = inspection.server
            instance.default_context = inspection.current_context

            credential = instance.credential
            credential.active_context = inspection.current_context
            credential.set_kubeconfig(inspection.normalized)
            credential.save(update_fields=["active_context", "kubeconfig_encrypted", "fingerprint", "updated_at"])

        instance.save()
        return instance


class ClusterImportSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64)
    environment = serializers.ChoiceField(choices=ENVIRONMENT_CHOICES, default="dev")
    description = serializers.CharField(max_length=255, allow_blank=True, required=False)
    kubeconfig = serializers.CharField()

    def validate(self, attrs):
        inspection = validate_kubeconfig(attrs["kubeconfig"])
        self.context["inspection"] = inspection
        return attrs

    def validate_name(self, value):
        if not slugify(value):
            raise serializers.ValidationError("集群名称需要包含可生成 slug 的字符。")
        return value

    def _make_unique_slug(self, base_name: str) -> str:
        base_slug = slugify(base_name)[:64]
        candidate = base_slug
        index = 1
        while Cluster.objects.filter(slug=candidate).exists():
            suffix = f"-{index}"
            candidate = f"{base_slug[: 64 - len(suffix)]}{suffix}"
            index += 1
        return candidate

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        inspection = self.context["inspection"]
        cluster = Cluster.objects.create(
            name=validated_data["name"],
            slug=self._make_unique_slug(validated_data["name"]),
            environment=validated_data["environment"],
            description=validated_data.get("description", ""),
            server=inspection.server,
            default_context=inspection.current_context,
            status=ClusterStatus.PENDING,
            health_state=ClusterHealthState.UNKNOWN,
            imported_by=request.user,
        )

        credential = ClusterCredential(
            cluster=cluster,
            active_context=inspection.current_context,
            fingerprint=inspection.fingerprint,
        )
        credential.set_kubeconfig(inspection.normalized)
        credential.save()

        ClusterCapability.objects.create(
            cluster=cluster,
            supports_impersonation=False,
            supports_server_side_apply=True,
            supports_watch_bookmarks=True,
            supports_exec=False,
            discovered_api_groups=[],
        )
        ClusterHealthStatus.objects.create(
            cluster=cluster,
            status=ClusterHealthState.UNKNOWN,
            message="kubeconfig 结构校验通过，等待真实联通性探测。",
            latency_ms=0,
        )

        record_audit_event(
            event_type="cluster.import",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id), "cluster_name": cluster.name},
            metadata={
                "context": inspection.current_context,
                "cluster_count": inspection.cluster_count,
                "user_count": inspection.user_count,
                "context_count": inspection.context_count,
            },
        )
        return cluster
