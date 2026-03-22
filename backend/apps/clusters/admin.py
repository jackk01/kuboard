from django.contrib import admin

from .models import Cluster, ClusterCapability, ClusterCredential, ClusterHealthStatus


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ("name", "environment", "server", "status", "health_state", "updated_at")
    list_filter = ("environment", "status", "health_state")
    search_fields = ("name", "slug", "server", "default_context")


@admin.register(ClusterCredential)
class ClusterCredentialAdmin(admin.ModelAdmin):
    list_display = ("cluster", "active_context", "fingerprint", "updated_at")
    readonly_fields = ("fingerprint", "created_at", "updated_at")


@admin.register(ClusterCapability)
class ClusterCapabilityAdmin(admin.ModelAdmin):
    list_display = ("cluster", "supports_impersonation", "supports_server_side_apply", "supports_exec")


@admin.register(ClusterHealthStatus)
class ClusterHealthStatusAdmin(admin.ModelAdmin):
    list_display = ("cluster", "status", "latency_ms", "last_checked_at")

