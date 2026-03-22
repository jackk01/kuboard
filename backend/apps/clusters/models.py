import hashlib
import uuid

from django.conf import settings
from django.db import models

from common.crypto import decrypt_text, encrypt_text


class ClusterStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    ERROR = "error", "Error"


class ClusterHealthState(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    DEGRADED = "degraded", "Degraded"
    UNKNOWN = "unknown", "Unknown"


class Cluster(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=72, unique=True)
    environment = models.CharField(max_length=32, default="development")
    description = models.CharField(max_length=255, blank=True)
    server = models.URLField(max_length=512)
    default_context = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=ClusterStatus.choices, default=ClusterStatus.PENDING)
    health_state = models.CharField(
        max_length=16,
        choices=ClusterHealthState.choices,
        default=ClusterHealthState.UNKNOWN,
    )
    kube_version = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imported_clusters",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClusterCredential(models.Model):
    cluster = models.OneToOneField(
        Cluster,
        on_delete=models.CASCADE,
        related_name="credential",
    )
    active_context = models.CharField(max_length=255)
    kubeconfig_encrypted = models.TextField()
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_kubeconfig(self, raw_kubeconfig: str):
        self.kubeconfig_encrypted = encrypt_text(raw_kubeconfig)
        self.fingerprint = hashlib.sha256(raw_kubeconfig.encode("utf-8")).hexdigest()

    def get_kubeconfig(self) -> str:
        return decrypt_text(self.kubeconfig_encrypted)

    def __str__(self):
        return f"Credential<{self.cluster.name}>"


class ClusterCapability(models.Model):
    cluster = models.OneToOneField(
        Cluster,
        on_delete=models.CASCADE,
        related_name="capability",
    )
    supports_impersonation = models.BooleanField(default=False)
    supports_server_side_apply = models.BooleanField(default=True)
    supports_watch_bookmarks = models.BooleanField(default=True)
    supports_exec = models.BooleanField(default=False)
    discovered_api_groups = models.JSONField(default=list, blank=True)
    openapi_index = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Capability<{self.cluster.name}>"


class ClusterHealthStatus(models.Model):
    cluster = models.OneToOneField(
        Cluster,
        on_delete=models.CASCADE,
        related_name="health",
    )
    status = models.CharField(
        max_length=16,
        choices=ClusterHealthState.choices,
        default=ClusterHealthState.UNKNOWN,
    )
    message = models.CharField(max_length=255, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Health<{self.cluster.name}:{self.status}>"

