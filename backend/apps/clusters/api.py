from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event
from apps.k8s_gateway.services import KubernetesAPIError, KubernetesClient

from .models import Cluster
from .serializers import ClusterImportSerializer, ClusterSerializer, ClusterUpdateSerializer


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
        response_serializer = ClusterSerializer(cluster)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ClusterDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Cluster.objects.select_related("health", "capability").all()

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return ClusterUpdateSerializer
        return ClusterSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        cluster = self.get_object()
        serializer = self.get_serializer(cluster, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

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
            return Response(
                {
                    "message": str(exc),
                    "details": exc.details,
                },
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
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
