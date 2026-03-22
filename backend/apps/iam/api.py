from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from common.audit import record_audit_event

from .models import User, UserGroup
from .serializers import (
    AdminUserGroupSerializer,
    AdminUserGroupWriteSerializer,
    AdminUserSerializer,
    AdminUserWriteSerializer,
    LoginSerializer,
    UserSerializer,
)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            record_audit_event(
                event_type="auth.login",
                request=request,
                severity="warning",
                status="denied",
                metadata={"email": serializer.validated_data["email"]},
            )
            return Response(
                {"message": "邮箱或密码错误。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user.last_seen_at = timezone.now()
        user.save(update_fields=["last_seen_at"])

        token, _ = Token.objects.get_or_create(user=user)
        record_audit_event(
            event_type="auth.login",
            actor=user,
            request=request,
            status="success",
        )
        return Response(
            {
                "token": token.key,
                "user": UserSerializer(user).data,
            }
        )


class LogoutView(APIView):
    def post(self, request):
        if request.auth:
            request.auth.delete()

        record_audit_event(
            event_type="auth.logout",
            actor=request.user,
            request=request,
            status="success",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminUserListCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        users = User.objects.order_by("email")
        return Response(AdminUserSerializer(users, many=True).data)

    def post(self, request):
        serializer = AdminUserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        record_audit_event(
            event_type="iam.user.create",
            actor=request.user,
            request=request,
            status="success",
            target={"user_id": user.id, "email": user.email},
        )
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        serializer = AdminUserWriteSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        record_audit_event(
            event_type="iam.user.update",
            actor=request.user,
            request=request,
            status="success",
            target={"user_id": user.id, "email": user.email},
        )
        return Response(AdminUserSerializer(user).data)

    def delete(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if request.user.pk == user.pk:
            return Response({"message": "不能删除当前登录账号。"}, status=status.HTTP_400_BAD_REQUEST)

        payload = {"user_id": user.id, "email": user.email}
        user.delete()
        record_audit_event(
            event_type="iam.user.delete",
            actor=request.user,
            request=request,
            status="success",
            target=payload,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserGroupListCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        groups = UserGroup.objects.order_by("name")
        return Response(AdminUserGroupSerializer(groups, many=True).data)

    def post(self, request):
        serializer = AdminUserGroupWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        record_audit_event(
            event_type="iam.group.create",
            actor=request.user,
            request=request,
            status="success",
            target={"group_id": group.id, "name": group.name},
        )
        return Response(AdminUserGroupSerializer(group).data, status=status.HTTP_201_CREATED)


class AdminUserGroupDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, pk):
        group = get_object_or_404(UserGroup, pk=pk)
        serializer = AdminUserGroupWriteSerializer(group, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        group = serializer.save()
        record_audit_event(
            event_type="iam.group.update",
            actor=request.user,
            request=request,
            status="success",
            target={"group_id": group.id, "name": group.name},
        )
        return Response(AdminUserGroupSerializer(group).data)

    def delete(self, request, pk):
        group = get_object_or_404(UserGroup, pk=pk)
        payload = {"group_id": group.id, "name": group.name}
        group.delete()
        record_audit_event(
            event_type="iam.group.delete",
            actor=request.user,
            request=request,
            status="success",
            target=payload,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
