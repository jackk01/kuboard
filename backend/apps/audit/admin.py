from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "status", "severity", "actor", "cluster", "created_at")
    list_filter = ("status", "severity", "event_type")
    search_fields = ("event_type", "request_id", "actor__email", "cluster__name")
    readonly_fields = ("created_at",)

