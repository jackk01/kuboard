from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event

from .models import StreamSession
from .serializers import StreamSessionSerializer
from .terminal import TerminalSessionError, terminal_hub


class StreamSessionCloseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["success", "error", "stopped"], required=False, default="success")


class StreamSessionOutputQuerySerializer(serializers.Serializer):
    cursor = serializers.IntegerField(required=False, min_value=0, default=0)


class StreamSessionInputSerializer(serializers.Serializer):
    input = serializers.CharField(trim_whitespace=False)


class StreamSessionResizeSerializer(serializers.Serializer):
    rows = serializers.IntegerField(required=False, min_value=12, max_value=120, default=32)
    cols = serializers.IntegerField(required=False, min_value=40, max_value=240, default=120)


class StreamSessionListView(generics.ListAPIView):
    serializer_class = StreamSessionSerializer

    def get_queryset(self):
        queryset = StreamSession.objects.select_related("cluster", "owner").order_by("-created_at", "-id")
        user = self.request.user

        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            queryset = queryset.filter(owner=user)

        cluster_id = self.request.query_params.get("cluster")
        if cluster_id:
            queryset = queryset.filter(cluster_id=cluster_id)

        stream_type = self.request.query_params.get("stream_type")
        if stream_type:
            queryset = queryset.filter(stream_type=stream_type)

        namespace = self.request.query_params.get("namespace")
        if namespace:
            queryset = queryset.filter(namespace=namespace)

        resource_name = self.request.query_params.get("resource_name")
        if resource_name:
            queryset = queryset.filter(resource_name=resource_name)

        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        try:
            limit = int(self.request.query_params.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))
        return queryset[:limit]


class StreamSessionCloseView(APIView):
    def post(self, request, pk):
        serializer = StreamSessionCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        queryset = StreamSession.objects.select_related("cluster", "owner")
        if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
            queryset = queryset.filter(owner=request.user)

        session = get_object_or_404(queryset, pk=pk)
        if session.stream_type == "terminal":
            terminal_hub.close_session(session_id=session.id, status=serializer.validated_data["status"])
            session.refresh_from_db()
        session.status = serializer.validated_data["status"]
        session.closed_at = timezone.now()
        session.save(update_fields=["status", "closed_at"])

        record_audit_event(
            event_type="stream.session.close",
            actor=request.user,
            cluster=session.cluster,
            request=request,
            status="success",
            target={
                "session_id": session.id,
                "stream_type": session.stream_type,
                "resource_name": session.resource_name,
                "namespace": session.namespace,
            },
            metadata={"status": session.status},
        )
        return Response(StreamSessionSerializer(session).data, status=status.HTTP_200_OK)


class StreamSessionOutputView(APIView):
    def get(self, request, pk):
        serializer = StreamSessionOutputQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        queryset = StreamSession.objects.select_related("cluster", "owner")
        if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
            queryset = queryset.filter(owner=request.user)
        session = get_object_or_404(queryset, pk=pk, stream_type="terminal")

        try:
            payload = terminal_hub.read_output(session_id=session.id, cursor=serializer.validated_data["cursor"])
        except TerminalSessionError as exc:
            if exc.status_code == 404 and session.closed_at:
                return Response(
                    {
                        "text": "",
                        "cursor": serializer.validated_data["cursor"],
                        "status": session.status,
                        "closed": True,
                        "exit_code": session.exit_code,
                        "closed_at": session.closed_at,
                    }
                )
            return Response({"message": str(exc)}, status=exc.status_code)

        return Response(payload)


class StreamSessionInputView(APIView):
    def post(self, request, pk):
        serializer = StreamSessionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        queryset = StreamSession.objects.select_related("cluster", "owner")
        if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
            queryset = queryset.filter(owner=request.user)
        session = get_object_or_404(queryset, pk=pk, stream_type="terminal")

        try:
            terminal_hub.write_input(session_id=session.id, data=serializer.validated_data["input"])
        except TerminalSessionError as exc:
            return Response({"message": str(exc)}, status=exc.status_code)

        record_audit_event(
            event_type="stream.session.input",
            actor=request.user,
            cluster=session.cluster,
            request=request,
            status="success",
            target={"session_id": session.id, "stream_type": session.stream_type},
            metadata={"size": len(serializer.validated_data["input"])},
        )
        return Response({"accepted": True}, status=status.HTTP_200_OK)


class StreamSessionResizeView(APIView):
    def post(self, request, pk):
        serializer = StreamSessionResizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        queryset = StreamSession.objects.select_related("cluster", "owner")
        if not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
            queryset = queryset.filter(owner=request.user)
        session = get_object_or_404(queryset, pk=pk, stream_type="terminal")

        try:
            terminal_hub.resize(
                session_id=session.id,
                rows=serializer.validated_data["rows"],
                cols=serializer.validated_data["cols"],
            )
        except TerminalSessionError as exc:
            return Response({"message": str(exc)}, status=exc.status_code)

        return Response({"accepted": True}, status=status.HTTP_200_OK)
