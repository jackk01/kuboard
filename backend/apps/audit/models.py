from django.conf import settings
from django.db import models


class AuditSeverity(models.TextChoices):
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    CRITICAL = "critical", "Critical"


class AuditStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    DENIED = "denied", "Denied"
    ERROR = "error", "Error"


class AuditEvent(models.Model):
    event_type = models.CharField(max_length=64)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    cluster = models.ForeignKey(
        "clusters.Cluster",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    severity = models.CharField(max_length=16, choices=AuditSeverity.choices, default=AuditSeverity.INFO)
    status = models.CharField(max_length=16, choices=AuditStatus.choices, default=AuditStatus.SUCCESS)
    request_id = models.CharField(max_length=64, blank=True)
    target = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    remote_addr = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type}<{self.status}>"

