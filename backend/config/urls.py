from django.contrib import admin
from django.urls import path

from apps.audit.api import AuditEventListView
from apps.clusters.api import ClusterDetailView, ClusterHealthCheckView, ClusterListCreateView, LocalKubeconfigView
from apps.iam.api import (
    AdminUserDetailView,
    AdminUserGroupDetailView,
    AdminUserGroupListCreateView,
    AdminUserListCreateView,
    CurrentUserView,
    LoginView,
    LogoutView,
)
from apps.k8s_gateway.api import (
    ClusterDiscoveryView,
    ClusterPermissionRulesView,
    EventListView,
    PodExecView,
    PodLogView,
    PodTerminalView,
    ResourceApplyView,
    ResourceDetailView,
    ResourceListView,
    ResourcePermissionView,
    ResourceSchemaView,
    ResourceWatchView,
)
from apps.rbac_bridge.api import (
    ClusterImpersonationConfigView,
    CurrentImpersonationPreviewView,
    SubjectMappingDetailView,
    SubjectMappingListCreateView,
)
from apps.streams.api import (
    StreamSessionCloseView,
    StreamSessionInputView,
    StreamSessionListView,
    StreamSessionOutputView,
    StreamSessionResizeView,
)
from apps.system_settings.api import DashboardSummaryView, HealthView, ReadinessView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health", HealthView.as_view(), name="health"),
    path("api/v1/health/ready", ReadinessView.as_view(), name="health-ready"),
    path("api/v1/auth/login", LoginView.as_view(), name="login"),
    path("api/v1/auth/logout", LogoutView.as_view(), name="logout"),
    path("api/v1/me", CurrentUserView.as_view(), name="me"),
    path("api/v1/users", AdminUserListCreateView.as_view(), name="user-list"),
    path("api/v1/users/<int:pk>", AdminUserDetailView.as_view(), name="user-detail"),
    path("api/v1/user-groups", AdminUserGroupListCreateView.as_view(), name="user-group-list"),
    path("api/v1/user-groups/<int:pk>", AdminUserGroupDetailView.as_view(), name="user-group-detail"),
    path("api/v1/dashboard/summary", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("api/v1/rbac/mappings", SubjectMappingListCreateView.as_view(), name="rbac-mapping-list"),
    path("api/v1/rbac/mappings/<int:pk>", SubjectMappingDetailView.as_view(), name="rbac-mapping-detail"),
    path("api/v1/rbac/me", CurrentImpersonationPreviewView.as_view(), name="rbac-preview"),
    path(
        "api/v1/rbac/clusters/<uuid:cluster_id>/impersonation",
        ClusterImpersonationConfigView.as_view(),
        name="rbac-cluster-impersonation",
    ),
    path("api/v1/clusters/local-kubeconfig", LocalKubeconfigView.as_view(), name="cluster-local-kubeconfig"),
    path("api/v1/clusters", ClusterListCreateView.as_view(), name="cluster-list"),
    path("api/v1/clusters/<uuid:pk>", ClusterDetailView.as_view(), name="cluster-detail"),
    path("api/v1/clusters/<uuid:pk>/discovery", ClusterDiscoveryView.as_view(), name="cluster-discovery"),
    path("api/v1/clusters/<uuid:pk>/events", EventListView.as_view(), name="cluster-events"),
    path(
        "api/v1/clusters/<uuid:pk>/permissions/rules",
        ClusterPermissionRulesView.as_view(),
        name="cluster-permission-rules",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/permissions/resources/<str:group>/<str:version>/<str:resource>",
        ResourcePermissionView.as_view(),
        name="resource-permissions",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/watch/resources/<str:group>/<str:version>/<str:resource>",
        ResourceWatchView.as_view(),
        name="resource-watch",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/health-check",
        ClusterHealthCheckView.as_view(),
        name="cluster-health-check",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/<str:group>/<str:version>/<str:resource>",
        ResourceListView.as_view(),
        name="resource-list",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/schemas/<str:group>/<str:version>/<str:resource>",
        ResourceSchemaView.as_view(),
        name="resource-schema",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/<str:group>/<str:version>/<str:resource>/<str:name>",
        ResourceDetailView.as_view(),
        name="resource-detail",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/core/v1/pods/<str:name>/logs",
        PodLogView.as_view(),
        name="pod-logs",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/core/v1/pods/<str:name>/exec",
        PodExecView.as_view(),
        name="pod-exec",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/core/v1/pods/<str:name>/terminal",
        PodTerminalView.as_view(),
        name="pod-terminal",
    ),
    path(
        "api/v1/clusters/<uuid:pk>/resources/<str:group>/<str:version>/<str:resource>/<str:name>/apply",
        ResourceApplyView.as_view(),
        name="resource-apply",
    ),
    path("api/v1/audit/events", AuditEventListView.as_view(), name="audit-events"),
    path("api/v1/streams/sessions", StreamSessionListView.as_view(), name="stream-session-list"),
    path("api/v1/streams/sessions/<int:pk>/output", StreamSessionOutputView.as_view(), name="stream-session-output"),
    path("api/v1/streams/sessions/<int:pk>/input", StreamSessionInputView.as_view(), name="stream-session-input"),
    path("api/v1/streams/sessions/<int:pk>/resize", StreamSessionResizeView.as_view(), name="stream-session-resize"),
    path("api/v1/streams/sessions/<int:pk>/close", StreamSessionCloseView.as_view(), name="stream-session-close"),
]
