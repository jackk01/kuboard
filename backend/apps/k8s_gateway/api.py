from datetime import timedelta

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event

from apps.clusters.models import Cluster, ClusterHealthState, ClusterStatus
from apps.streams.models import StreamSession

from .services import KubernetesAPIError, KubernetesClient


def _build_discovery_health_message(discovery: dict) -> str:
    group_count = len(discovery.get("groups", []))
    warning_count = len(discovery.get("warnings", []))
    if warning_count:
        return f"Discovery 成功，已同步 {group_count} 个资源组，跳过 {warning_count} 个异常接口。"
    return f"Discovery 成功，已同步 {group_count} 个资源组。"


class ResourceApplySerializer(serializers.Serializer):
    manifest = serializers.CharField()
    dry_run = serializers.BooleanField(default=False)
    force = serializers.BooleanField(default=False)


class ResourcePermissionQuerySerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)


class PodLogQuerySerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)
    container = serializers.CharField(required=False, allow_blank=True)
    tail_lines = serializers.IntegerField(required=False, min_value=10, max_value=2000, default=200)
    previous = serializers.BooleanField(required=False, default=False)
    timestamps = serializers.BooleanField(required=False, default=True)
    since_time = serializers.CharField(required=False, allow_blank=True)
    follow = serializers.BooleanField(required=False, default=False)
    session_id = serializers.IntegerField(required=False, min_value=1)


class PodExecSerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)
    container = serializers.CharField(required=False, allow_blank=True)
    shell_command = serializers.CharField()
    timeout_seconds = serializers.IntegerField(required=False, min_value=3, max_value=60, default=15)


class PodTerminalSerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)
    container = serializers.CharField(required=False, allow_blank=True)
    shell = serializers.CharField(required=False, allow_blank=True, default="/bin/sh")
    rows = serializers.IntegerField(required=False, min_value=12, max_value=120, default=32)
    cols = serializers.IntegerField(required=False, min_value=40, max_value=240, default=120)


class RulesReviewQuerySerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)


class ResourceWatchQuerySerializer(serializers.Serializer):
    namespace = serializers.CharField(required=False, allow_blank=True)
    resource_version = serializers.CharField(required=False, allow_blank=True)
    timeout_seconds = serializers.IntegerField(required=False, min_value=3, max_value=30, default=10)


class ClusterDiscoveryView(APIView):
    def get(self, request, pk):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)

        try:
            discovery = client.discover(best_effort=True)
            client.sync_capability_from_discovery(discovery)
        except KubernetesAPIError as exc:
            return Response(
                {
                    "message": str(exc),
                    "details": exc.details,
                },
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        cluster.status = ClusterStatus.READY
        cluster.health_state = ClusterHealthState.HEALTHY
        cluster.kube_version = discovery.get("version", {}).get("gitVersion", "")
        cluster.last_error = ""
        cluster.last_seen_at = timezone.now()
        cluster.save(
            update_fields=["status", "health_state", "kube_version", "last_error", "last_seen_at", "updated_at"]
        )
        cluster.health.status = ClusterHealthState.HEALTHY
        cluster.health.message = _build_discovery_health_message(discovery)
        cluster.health.save(update_fields=["status", "message", "last_checked_at"])

        record_audit_event(
            event_type="cluster.discovery",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id), "cluster_name": cluster.name},
        )
        return Response(discovery)


class ClusterPermissionRulesView(APIView):
    def get(self, request, pk):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = RulesReviewQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        try:
            payload = client.get_self_subject_rules(namespace=serializer.validated_data.get("namespace") or None)
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.auth.rules",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={"cluster_id": str(cluster.id), "namespace": serializer.validated_data.get("namespace", "")},
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.auth.rules",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={"cluster_id": str(cluster.id), "namespace": payload["namespace"]},
            metadata={"incomplete": payload["incomplete"]},
        )
        return Response(payload)


class ResourcePermissionView(APIView):
    def get(self, request, pk, group, version, resource):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = ResourcePermissionQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        query_group = "" if group == "core" else group
        namespace = serializer.validated_data.get("namespace") or None
        name = serializer.validated_data.get("name") or None

        try:
            payload = client.check_resource_permissions(
                group=query_group,
                version=version,
                resource=resource,
                namespace=namespace,
                name=name,
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.permissions",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "namespace": namespace,
                    "name": name,
                },
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.permissions",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "namespace": payload["scope"]["namespace"],
                "name": payload["scope"]["name"],
            },
            metadata={"subresources": list(payload["subresources"].keys())},
        )
        return Response(payload)


class ResourceListView(APIView):
    def get(self, request, pk, group, version, resource):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)

        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace")
        limit = int(request.query_params.get("limit", "100"))
        continue_token = request.query_params.get("continue")

        try:
            payload = client.list_resources(
                group=query_group,
                version=version,
                resource=resource,
                namespace=namespace,
                limit=limit,
                continue_token=continue_token,
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.list",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "namespace": namespace,
                },
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
            event_type="k8s.resource.list",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "namespace": payload["resource"]["namespace"],
            },
            metadata={"count": payload["metadata"]["count"]},
        )
        return Response(payload)

    def post(self, request, pk, group, version, resource):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = ResourceApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace")

        try:
            payload = client.create_resource(
                group=query_group,
                version=version,
                resource=resource,
                namespace=namespace,
                manifest_text=serializer.validated_data["manifest"],
                dry_run=serializer.validated_data["dry_run"],
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.create",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "namespace": namespace,
                },
                metadata={"message": str(exc), "dry_run": serializer.validated_data["dry_run"]},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.create",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "name": payload["metadata"]["name"],
                "namespace": payload["metadata"]["namespace"] or namespace,
            },
            metadata={"dry_run": serializer.validated_data["dry_run"]},
        )
        return Response(payload, status=status.HTTP_201_CREATED if not serializer.validated_data["dry_run"] else 200)


class ResourceSchemaView(APIView):
    def get(self, request, pk, group, version, resource):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace") or None

        try:
            payload = client.get_resource_schema(
                group=query_group,
                version=version,
                resource=resource,
                namespace=namespace,
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.schema",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                },
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.schema",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
            },
            metadata={"source": payload["source"], "schema_name": payload["schema_name"]},
        )
        return Response(payload)


class PodLogView(APIView):
    def get(self, request, pk, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = PodLogQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        namespace = serializer.validated_data.get("namespace") or None
        container = serializer.validated_data.get("container") or None
        follow = serializer.validated_data["follow"]
        session = None

        if follow:
            session_id = serializer.validated_data.get("session_id")
            session_queryset = StreamSession.objects.select_related("cluster", "owner").filter(
                cluster=cluster,
                stream_type="logs",
            )
            if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
                session_queryset = session_queryset.filter(owner=request.user)

            if session_id:
                session = get_object_or_404(session_queryset, pk=session_id)
            else:
                session = StreamSession.objects.create(
                    stream_type="logs",
                    status="running",
                    cluster=cluster,
                    owner=request.user if getattr(request.user, "is_authenticated", False) else None,
                    namespace=namespace or "",
                    resource_name=name,
                    container_name=container or "",
                    command=["follow"],
                    expires_at=timezone.now() + timedelta(hours=1),
                )

        try:
            payload = client.get_pod_logs(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=serializer.validated_data["tail_lines"],
                previous=serializer.validated_data["previous"],
                timestamps=serializer.validated_data["timestamps"],
                since_time=serializer.validated_data.get("since_time") or None,
            )
        except KubernetesAPIError as exc:
            if session:
                session.status = "error"
                session.output_excerpt = str(exc)[:4000]
                session.closed_at = timezone.now()
                session.save(update_fields=["status", "output_excerpt", "closed_at"])
            record_audit_event(
                event_type="k8s.pod.logs",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "name": name,
                    "namespace": namespace,
                    "container": container,
                    "session_id": session.id if session else None,
                },
                metadata={"message": str(exc), "follow": follow},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        if session:
            lines = [line for line in payload["text"].splitlines() if line.strip()]
            session.status = "running"
            session.namespace = payload["namespace"]
            session.container_name = payload["container"]
            session.output_excerpt = (lines[-1] if lines else session.output_excerpt)[:4000]
            session.closed_at = None
            session.save(update_fields=["status", "namespace", "container_name", "output_excerpt", "closed_at"])

        record_audit_event(
            event_type="k8s.pod.logs",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "name": name,
                "namespace": payload["namespace"],
                "container": payload["container"],
                "session_id": session.id if session else None,
            },
            metadata={
                "tail_lines": payload["tail_lines"],
                "previous": payload["previous"],
                "follow": follow,
                "line_count": payload["cursor"]["line_count"],
            },
        )
        return Response(
            {
                **payload,
                "follow": follow,
                "session": (
                    {
                        "id": session.id,
                        "status": session.status,
                        "created_at": session.created_at,
                        "closed_at": session.closed_at,
                    }
                    if session
                    else None
                ),
            }
        )


class PodExecView(APIView):
    def post(self, request, pk, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = PodExecSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        namespace = serializer.validated_data.get("namespace") or None
        container = serializer.validated_data.get("container") or None
        session = StreamSession.objects.create(
            stream_type="exec",
            status="running",
            cluster=cluster,
            owner=request.user if getattr(request.user, "is_authenticated", False) else None,
            namespace=namespace or "",
            resource_name=name,
            container_name=container or "",
            command=[serializer.validated_data["shell_command"]],
            expires_at=timezone.now() + timedelta(hours=1),
        )

        try:
            payload = client.exec_pod_command(
                name=name,
                namespace=namespace,
                container=container,
                shell_command=serializer.validated_data["shell_command"],
                timeout_seconds=serializer.validated_data["timeout_seconds"],
            )
        except KubernetesAPIError as exc:
            session.status = "error"
            session.output_excerpt = str(exc)[:4000]
            session.closed_at = timezone.now()
            session.save(update_fields=["status", "output_excerpt", "closed_at"])
            record_audit_event(
                event_type="k8s.pod.exec",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "name": name,
                    "namespace": namespace,
                    "container": container,
                    "session_id": session.id,
                },
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        session.status = "success" if payload["success"] else "error"
        session.exit_code = payload["exit_code"]
        session.output_excerpt = payload["output_excerpt"]
        session.closed_at = timezone.now()
        session.save(update_fields=["status", "exit_code", "output_excerpt", "closed_at"])

        record_audit_event(
            event_type="k8s.pod.exec",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success" if payload["success"] else "error",
            target={
                "cluster_id": str(cluster.id),
                "name": name,
                "namespace": payload["namespace"],
                "container": payload["container"],
                "session_id": session.id,
            },
            metadata={"exit_code": payload["exit_code"], "duration_ms": payload["duration_ms"]},
        )
        return Response(
            {
                **payload,
                "session": {
                    "id": session.id,
                    "status": session.status,
                    "created_at": session.created_at,
                    "closed_at": session.closed_at,
                },
            }
        )


class PodTerminalView(APIView):
    def post(self, request, pk, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = PodTerminalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        namespace = serializer.validated_data.get("namespace") or None
        container = serializer.validated_data.get("container") or None
        session = StreamSession.objects.create(
            stream_type="terminal",
            status="running",
            cluster=cluster,
            owner=request.user if getattr(request.user, "is_authenticated", False) else None,
            namespace=namespace or "",
            resource_name=name,
            container_name=container or "",
            command=[serializer.validated_data["shell"]],
            expires_at=timezone.now() + timedelta(hours=2),
        )

        try:
            payload = client.open_pod_terminal(
                session=session,
                name=name,
                namespace=namespace,
                container=container,
                shell=serializer.validated_data["shell"],
                rows=serializer.validated_data["rows"],
                cols=serializer.validated_data["cols"],
            )
        except KubernetesAPIError as exc:
            session.status = "error"
            session.output_excerpt = str(exc)[:4000]
            session.closed_at = timezone.now()
            session.save(update_fields=["status", "output_excerpt", "closed_at"])
            record_audit_event(
                event_type="k8s.pod.terminal",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "name": name,
                    "namespace": namespace,
                    "container": container,
                    "session_id": session.id,
                },
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        session.namespace = payload["namespace"]
        session.container_name = payload["container"]
        session.save(update_fields=["namespace", "container_name"])

        record_audit_event(
            event_type="k8s.pod.terminal",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "name": name,
                "namespace": payload["namespace"],
                "container": payload["container"],
                "session_id": session.id,
            },
            metadata={"shell": payload["shell"], "rows": payload["terminal"]["rows"], "cols": payload["terminal"]["cols"]},
        )
        return Response(
            {
                **payload,
                "session": {
                    "id": session.id,
                    "status": session.status,
                    "created_at": session.created_at,
                    "closed_at": session.closed_at,
                },
            }
        )


class ResourceWatchView(APIView):
    def get(self, request, pk, group, version, resource):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = ResourceWatchQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        query_group = "" if group == "core" else group
        namespace = serializer.validated_data.get("namespace") or None
        resource_version = serializer.validated_data.get("resource_version") or None

        try:
            payload = client.watch_resources(
                group=query_group,
                version=version,
                resource=resource,
                namespace=namespace,
                resource_version=resource_version,
                timeout_seconds=serializer.validated_data["timeout_seconds"],
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.watch",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "namespace": namespace,
                },
                metadata={"message": str(exc), "resource_version": resource_version or ""},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        return Response(payload)


class ResourceDetailView(APIView):
    def get(self, request, pk, group, version, resource, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)

        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace")

        try:
            payload = client.get_resource(
                group=query_group,
                version=version,
                resource=resource,
                name=name,
                namespace=namespace,
            )
        except KubernetesAPIError as exc:
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.get",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "name": name,
                "namespace": payload["metadata"]["namespace"] or namespace,
            },
        )
        return Response(payload)

    def delete(self, request, pk, group, version, resource, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)

        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace")

        try:
            payload = client.delete_resource(
                group=query_group,
                version=version,
                resource=resource,
                name=name,
                namespace=namespace,
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.delete",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "name": name,
                    "namespace": namespace,
                },
                metadata={"message": str(exc)},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.delete",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "name": name,
                "namespace": namespace,
            },
        )
        return Response(payload)


class ResourceApplyView(APIView):
    def post(self, request, pk, group, version, resource, name):
        cluster = get_object_or_404(Cluster.objects.select_related("credential", "capability", "health"), pk=pk)
        client = KubernetesClient(cluster, actor=request.user)
        serializer = ResourceApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query_group = "" if group == "core" else group
        namespace = request.query_params.get("namespace")

        try:
            payload = client.apply_resource(
                group=query_group,
                version=version,
                resource=resource,
                name=name,
                namespace=namespace,
                manifest_text=serializer.validated_data["manifest"],
                dry_run=serializer.validated_data["dry_run"],
                force=serializer.validated_data["force"],
            )
        except KubernetesAPIError as exc:
            record_audit_event(
                event_type="k8s.resource.apply",
                actor=request.user,
                cluster=cluster,
                request=request,
                severity="warning",
                status="error",
                target={
                    "cluster_id": str(cluster.id),
                    "group": group,
                    "version": version,
                    "resource": resource,
                    "name": name,
                    "namespace": namespace,
                },
                metadata={"message": str(exc), "dry_run": serializer.validated_data["dry_run"]},
            )
            return Response(
                {"message": str(exc), "details": exc.details},
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        record_audit_event(
            event_type="k8s.resource.apply",
            actor=request.user,
            cluster=cluster,
            request=request,
            status="success",
            target={
                "cluster_id": str(cluster.id),
                "group": group,
                "version": version,
                "resource": resource,
                "name": name,
                "namespace": payload["metadata"]["namespace"] or namespace,
            },
            metadata={"dry_run": serializer.validated_data["dry_run"]},
        )
        return Response(payload)
