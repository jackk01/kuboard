from django.db import models


class StreamSession(models.Model):
    stream_type = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default="running")
    cluster = models.ForeignKey(
        "clusters.Cluster",
        on_delete=models.CASCADE,
        related_name="stream_sessions",
    )
    owner = models.ForeignKey(
        "iam.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stream_sessions",
    )
    namespace = models.CharField(max_length=128, blank=True)
    resource_name = models.CharField(max_length=255, blank=True)
    container_name = models.CharField(max_length=255, blank=True)
    command = models.JSONField(default=list, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    output_excerpt = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
