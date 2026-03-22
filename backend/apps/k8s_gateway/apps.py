from django.apps import AppConfig


class K8SGatewayConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.k8s_gateway'
    verbose_name = 'Kuboard Kubernetes Gateway'
