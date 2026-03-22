from django.db import models


class SystemSetting(models.Model):
    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class FeatureFlag(models.Model):
    key = models.CharField(max_length=64, unique=True)
    is_enabled = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

