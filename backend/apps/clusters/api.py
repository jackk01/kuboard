from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event
from apps.k8s_gateway.services import KubernetesAPIError, KubernetesClient

from .models import Cluster
from .serializers import ClusterDetailSerializer, ClusterImportSerializer, ClusterSerializer, ClusterUpdateSerializer
from .services import load_local_kubeconfig


def _sync_discovery_after_health_check(client: KubernetesClient, cluster: Cluster) -> dict:
    discovery = client.discover()
    client.sync_capability_from_discovery(discovery)
    group_count = len(discovery.get("groups", []))
    cluster.health.message = f"{cluster.health.message} Discovery 已同步 {group_count} 个资源组。"
    cluster.health.save(update_fields=["message", "last_checked_at"])
    return discovery


class ClusterListCreateView(generics.ListCreateAPIView):
    queryset = Cluster.objects.select_related("health", "capability").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClusterImportSerializer
        return ClusterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        cluster = serializer.save()
        client = KubernetesClient(cluster)
        # 导入后立即触发一次真实联通性探测，避免状态长期停留在 pending。
        try:
            client.sync_health()
        except KubernetesAPIError:
            # 导入流程本身已完成，探测失败只更新健康状态，不影响 201 响应。
            pass
        else:
            try:
                _sync_discovery_after_health_check(client, cluster)
            except KubernetesAPIError as exc:
                cluster.health.message = f"{cluster.health.message} Discovery 同步失败：{exc}"
                cluster.health.save(update_fields=["message", "last_checked_at"])
        response_serializer = ClusterSerializer(cluster)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class LocalKubeconfigView(APIView):
    def get(self, request):
        result = load_local_kubeconfig()
        return Response(
            {
                "source_path": result.source_path,
                "kubeconfig": result.kubeconfig,
                "current_context": result.inspection.current_context,
                "server": result.inspection.server,
                "cluster_count": result.inspection.cluster_count,
                "user_count": result.inspection.user_count,
                "context_count": result.inspection.context_count,
                "fingerprint": result.inspection.fingerprint,
            }
        )


class ClusterDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Cluster.objects.select_related("credential", "health", "capability").all()

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return ClusterUpdateSerializer
        return ClusterDetailSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        cluster = self.get_object()
        serializer = self.get_serializer(cluster, data=request.data, partial=partial, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if "kubeconfig" in serializer.validated_data:
            client = KubernetesClient(cluster)
            try:
                client.sync_health()
            except KubernetesAPIError:
                pass
            else:
                try:
                    _sync_discovery_after_health_check(client, cluster)
                except KubernetesAPIError as exc:
                    cluster.health.message = f"{cluster.health.message} Discovery 同步失败：{exc}"
                    cluster.health.save(update_fields=["message", "last_checked_at"])

        record_audit_event(
            event_type="cluster.update",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id), "cluster_name": cluster.name},
            metadata={
                "fields": sorted(serializer.validated_data.keys()),
                "environment": cluster.environment,
                "kubeconfig_updated": "kubeconfig" in serializer.validated_data,
            },
        )
        return Response(ClusterSerializer(cluster).data)

    def destroy(self, request, *args, **kwargs):
        cluster = self.get_object()
        cluster_name = cluster.name
        cluster_id = str(cluster.id)
        cluster.delete()

        record_audit_event(
            event_type="cluster.delete",
            actor=request.user,
            request=request,
            status="success",
            severity="warning",
            target={"cluster_id": cluster_id, "cluster_name": cluster_name},
            metadata={},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClusterHealthCheckView(APIView):
    def post(self, request, pk):
        cluster = Cluster.objects.select_related("credential", "capability", "health").get(pk=pk)
        client = KubernetesClient(cluster)

        try:
            probe = client.sync_health()
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="cluster.health_check",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={"cluster_id": str(cluster.id)},
                metadata={"message": str(exc)},
            )
            message = str(exc)
            if exc.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
                message = f"上游 Kubernetes API 鉴权失败（{exc.status_code}）：{exc}"
            return Response(
                {
                    "message": message,
                    "details": exc.details,
                },
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )
        discovery = None
        try:
            discovery = _sync_discovery_after_health_check(client, cluster)
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="cluster.discovery",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={"cluster_id": str(cluster.id)},
                metadata={"message": str(exc)},
            )
            cluster.health.message = f"{cluster.health.message} Discovery 同步失败：{exc}"
            cluster.health.save(update_fields=["message", "last_checked_at"])
        else:
            record_audit_event(
                event_type="cluster.discovery",
                actor=request.user,
                cluster=cluster,
                request=request,
                status="success",
                target={"cluster_id": str(cluster.id)},
                metadata={"group_count": len(discovery.get("groups", []))},
            )

        record_audit_event(
            event_type="cluster.health_check",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id)},
            metadata={"version": probe["version"].get("gitVersion", "")},
        )
        return Response(ClusterSerializer(cluster).data)
