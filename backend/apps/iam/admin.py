from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, UserGroup, UserGroupMembership


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "display_name", "is_staff", "is_superuser", "is_active")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "display_name", "last_seen_at")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Flags", {"fields": ("password_needs_reset",)}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "updated_at")
    search_fields = ("name", "slug")


@admin.register(UserGroupMembership)
class UserGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__email", "group__name")

