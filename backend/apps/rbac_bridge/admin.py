from django.contrib import admin

from .models import SubjectMapping


@admin.register(SubjectMapping)
class SubjectMappingAdmin(admin.ModelAdmin):
    list_display = ("source_type", "source_identifier", "kubernetes_username", "cluster", "is_enabled")
    list_filter = ("source_type", "is_enabled")
    search_fields = ("source_identifier", "kubernetes_username")

