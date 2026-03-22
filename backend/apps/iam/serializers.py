from rest_framework import serializers

from apps.iam.models import User, UserGroup, UserGroupMembership


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "display_name",
            "is_staff",
            "is_superuser",
            "last_seen_at",
            "date_joined",
        ]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "display_name",
            "is_staff",
            "is_superuser",
            "password_needs_reset",
            "last_seen_at",
            "date_joined",
        ]


class AdminUserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = [
            "email",
            "display_name",
            "is_staff",
            "is_superuser",
            "password_needs_reset",
            "password",
        ]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "创建用户时必须提供初始密码。"})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AdminUserGroupSerializer(serializers.ModelSerializer):
    member_emails = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = UserGroup
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "member_count",
            "member_emails",
            "created_at",
            "updated_at",
        ]

    def get_member_emails(self, obj):
        return [membership.user.email for membership in obj.memberships.select_related("user").all()]

    def get_member_count(self, obj):
        return obj.memberships.count()


class AdminUserGroupWriteSerializer(serializers.ModelSerializer):
    member_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = UserGroup
        fields = [
            "name",
            "description",
            "member_emails",
        ]

    def _sync_memberships(self, group: UserGroup, emails: list[str]):
        normalized_emails = {email.strip().lower() for email in emails if email.strip()}
        users = list(User.objects.filter(email__in=normalized_emails))
        found_emails = {user.email.lower() for user in users}
        missing = sorted(normalized_emails - found_emails)
        if missing:
            raise serializers.ValidationError({"member_emails": f"以下邮箱未找到：{', '.join(missing)}"})

        UserGroupMembership.objects.filter(group=group).exclude(user__in=users).delete()
        existing_user_ids = set(
            UserGroupMembership.objects.filter(group=group, user__in=users).values_list("user_id", flat=True)
        )
        for user in users:
            if user.id not in existing_user_ids:
                UserGroupMembership.objects.create(group=group, user=user, role="member")

    def create(self, validated_data):
        emails = validated_data.pop("member_emails", [])
        group = UserGroup.objects.create(**validated_data)
        self._sync_memberships(group, emails)
        return group

    def update(self, instance, validated_data):
        emails = validated_data.pop("member_emails", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if emails is not None:
            self._sync_memberships(instance, emails)
        return instance
