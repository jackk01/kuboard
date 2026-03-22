from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event

from apps.clusters.models import Cluster

from .models import SubjectMapping
from .serializers import ClusterImpersonationSerializer, SubjectMappingSerializer
from .services import resolve_impersonation_context


class AdminOnlyPermission(permissions.IsAdminUser):
    message = "只有管理员可以管理 RBAC 映射。"


class SubjectMappingListCreateView(generics.ListCreateAPIView):
    permission_classes = [AdminOnlyPermission]
    serializer_class = SubjectMappingSerializer
    queryset = SubjectMapping.objects.select_related("cluster").all().order_by("-updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        cluster_id = self.request.query_params.get("cluster_id")
        if cluster_id:
            queryset = queryset.filter(cluster_id=cluster_id)
        return queryset

    def perform_create(self, serializer):
        mapping = serializer.save()
        record_audit_event(
            event_type="rbac.mapping.create",
            actor=self.request.user,
            request=self.request,
            status="success",
            target={"mapping_id": mapping.id, "cluster_id": str(mapping.cluster_id or "")},
        )


class SubjectMappingDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [AdminOnlyPermission]
    serializer_class = SubjectMappingSerializer
    queryset = SubjectMapping.objects.select_related("cluster").all()

    def perform_update(self, serializer):
        mapping = serializer.save()
        record_audit_event(
            event_type="rbac.mapping.update",
            actor=self.request.user,
            request=self.request,
            status="success",
            target={"mapping_id": mapping.id, "cluster_id": str(mapping.cluster_id or "")},
        )

    def perform_destroy(self, instance):
        record_audit_event(
            event_type="rbac.mapping.delete",
            actor=self.request.user,
            request=self.request,
            status="success",
            target={"mapping_id": instance.id, "cluster_id": str(instance.cluster_id or "")},
        )
        instance.delete()


class ClusterImpersonationConfigView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, cluster_id):
        cluster = get_object_or_404(Cluster.objects.select_related("capability"), pk=cluster_id)
        return Response(
            {
                "cluster_id": str(cluster.id),
                "cluster_name": cluster.name,
                "supports_impersonation": cluster.capability.supports_impersonation,
            }
        )

    def patch(self, request, cluster_id):
        payload = {"cluster_id": cluster_id, **request.data}
        serializer = ClusterImpersonationSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        cluster = get_object_or_404(Cluster.objects.select_related("capability"), pk=cluster_id)
        cluster.capability.supports_impersonation = serializer.validated_data["supports_impersonation"]
        cluster.capability.save(update_fields=["supports_impersonation"])

        record_audit_event(
            event_type="rbac.cluster.impersonation",
            actor=request.user,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id), "cluster_name": cluster.name},
            metadata={"enabled": cluster.capability.supports_impersonation},
        )
        return Response(
            {
                "cluster_id": str(cluster.id),
                "cluster_name": cluster.name,
                "supports_impersonation": cluster.capability.supports_impersonation,
            }
        )


class PreviewQuerySerializer(serializers.Serializer):
    cluster_id = serializers.UUIDField()


class CurrentImpersonationPreviewView(APIView):
    def get(self, request):
        serializer = PreviewQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        cluster = get_object_or_404(Cluster.objects.select_related("capability"), pk=serializer.validated_data["cluster_id"])
        context = resolve_impersonation_context(request.user, cluster)
        return Response(
            {
                "cluster_id": str(cluster.id),
                "cluster_name": cluster.name,
                "enabled": cluster.capability.supports_impersonation,
                "username": context.username,
                "groups": context.groups,
                "mapping_ids": context.mapping_ids,
            }
        )
