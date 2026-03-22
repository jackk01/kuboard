from django.db import models


class ResourceBookmark(models.Model):
    cluster = models.ForeignKey(
        "clusters.Cluster",
        on_delete=models.CASCADE,
        related_name="resource_bookmarks",
    )
    owner = models.ForeignKey(
        "iam.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resource_bookmarks",
    )
    resource_path = models.CharField(max_length=255)
    resource_version = models.CharField(max_length=128, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

