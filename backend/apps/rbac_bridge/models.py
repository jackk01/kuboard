from django.db import models


class SubjectMapping(models.Model):
    source_type = models.CharField(max_length=16, default="user")
    source_identifier = models.CharField(max_length=128)
    kubernetes_username = models.CharField(max_length=128, blank=True)
    kubernetes_groups = models.JSONField(default=list, blank=True)
    cluster = models.ForeignKey(
        "clusters.Cluster",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subject_mappings",
    )
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("source_type", "source_identifier", "cluster")

    def __str__(self):
        return f"{self.source_type}:{self.source_identifier}"

