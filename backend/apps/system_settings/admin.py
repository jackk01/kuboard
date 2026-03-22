from django.contrib import admin

from .models import FeatureFlag, SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key",)


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("key", "is_enabled", "updated_at")
    list_filter = ("is_enabled",)

