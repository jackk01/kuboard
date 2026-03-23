export interface UserProfile {
  id: number
  email: string
  username: string
  display_name: string
  is_staff: boolean
  is_superuser: boolean
  last_seen_at: string | null
  date_joined: string
}

export interface AdminUserRecord extends UserProfile {
  password_needs_reset: boolean
}

export interface AdminUserGroupRecord {
  id: number
  name: string
  slug: string
  description: string
  member_count: number
  member_emails: string[]
  created_at: string
  updated_at: string
}

export interface ClusterHealth {
  status: string
  message: string
  latency_ms: number
  last_checked_at: string
}

export interface ClusterCapability {
  supports_impersonation: boolean
  supports_server_side_apply: boolean
  supports_watch_bookmarks: boolean
  supports_exec: boolean
  discovered_api_groups: string[]
  last_synced_at: string | null
}

export interface Cluster {
  id: string
  name: string
  slug: string
  environment: string
  description: string
  server: string
  default_context: string
  status: string
  health_state: string
  kube_version: string
  last_error: string
  last_seen_at: string | null
  created_at: string
  updated_at: string
  health: ClusterHealth
  capability: ClusterCapability
}

export interface LocalKubeconfigPayload {
  source_path: string
  kubeconfig: string
  current_context: string
  server: string
  cluster_count: number
  user_count: number
  context_count: number
  fingerprint: string
}

export interface AuditEvent {
  id: number
  event_type: string
  severity: string
  status: string
  request_id: string
  target: Record<string, unknown>
  metadata: Record<string, unknown>
  actor_display?: string
  actor_email?: string
  cluster_name?: string
  created_at: string
}

export interface DashboardSummary {
  clusters: {
    total: number
    ready: number
    pending: number
    error: number
    healthy: number
    degraded: number
    unknown: number
  }
  recent_audit_count: number
  recent_events: Array<{
    event_type: string
    status: string
    cluster__name?: string
  }>
  features: {
    sqlite_mode: boolean
    rbac_bridge: boolean
    stream_hub: boolean
  }
}

export interface DiscoveryResource {
  group: string
  version: string
  name: string
  kind: string
  singular_name: string
  short_names: string[]
  namespaced: boolean
  verbs: string[]
}

export interface DiscoveryGroup {
  group: string
  version: string
  preferred_version: string
  resources: DiscoveryResource[]
}

export interface ClusterDiscoveryResponse {
  version: {
    major?: string
    minor?: string
    gitVersion?: string
  }
  context: {
    name: string
    server: string
    default_namespace: string
  }
  groups: DiscoveryGroup[]
  namespaces: Array<{
    name: string
    phase: string
  }>
  supports_exec?: boolean
}

export interface ResourceListResponse {
  resource: {
    group: string
    version: string
    name: string
    kind: string
    namespaced: boolean
    namespace: string | null
    verbs: string[]
  }
  items: Array<Record<string, any>>
  metadata: {
    count: number
    continue: string
    resource_version: string
  }
}

export interface ResourceDetailResponse {
  resource: {
    group: string
    version: string
    name: string
    kind: string
    namespaced: boolean
    namespace: string | null
    verbs: string[]
  }
  object: Record<string, any>
  yaml: string
  metadata: {
    name: string
    namespace: string
    uid: string
    resource_version: string
    generation: number | null
  }
}

export interface PermissionReview {
  allowed: boolean
  denied: boolean
  reason: string
  evaluation_error: string
}

export interface ResourcePermissionResponse {
  resource: {
    group: string
    version: string
    name: string
    kind: string
    namespaced: boolean
  }
  scope: {
    namespace: string | null
    name: string
  }
  verbs: Record<string, PermissionReview>
  subresources: Record<string, PermissionReview>
}

export interface ResourceSchemaResponse {
  resource: {
    group: string
    version: string
    name: string
    kind: string
    namespaced: boolean
    verbs: string[]
    short_names: string[]
  }
  schema: Record<string, any>
  schema_name: string
  source: 'crd' | 'openapi-v3' | 'inferred'
  metadata: Record<string, any>
}

export interface StreamSessionSummary {
  id: number
  status: string
  created_at: string
  closed_at: string | null
}

export type ExecSessionSummary = StreamSessionSummary

export interface PodLogsResponse {
  pod: string
  namespace: string
  container: string
  tail_lines: number
  previous: boolean
  timestamps: boolean
  text: string
  follow: boolean
  cursor: {
    since_time: string | null
    line_count: number
  }
  session: StreamSessionSummary | null
}

export interface ResourceWatchEvent {
  type: string
  object: Record<string, any>
  metadata: {
    kind: string
    name: string
    namespace: string
    resource_version: string
  }
}

export interface ResourceWatchResponse {
  resource: {
    group: string
    version: string
    name: string
    kind: string
    namespaced: boolean
    namespace: string | null
    verbs: string[]
  }
  events: ResourceWatchEvent[]
  metadata: {
    count: number
    resource_version: string
    next_resource_version: string
    timeout_seconds: number
  }
}

export interface SubjectMapping {
  id: number
  source_type: string
  source_identifier: string
  kubernetes_username: string
  kubernetes_groups: string[]
  cluster: string | null
  cluster_name?: string
  is_enabled: boolean
  created_at: string
  updated_at: string
}

export interface ImpersonationPreview {
  cluster_id: string
  cluster_name: string
  enabled: boolean
  username: string
  groups: string[]
  mapping_ids: number[]
}

export interface ClusterImpersonationConfig {
  cluster_id: string
  cluster_name: string
  supports_impersonation: boolean
}

export interface StreamSessionRecord {
  id: number
  stream_type: string
  status: string
  cluster: string
  cluster_name: string
  owner: number | null
  owner_email: string | null
  namespace: string
  resource_name: string
  container_name: string
  command: string[]
  exit_code: number | null
  output_excerpt: string
  expires_at: string
  closed_at: string | null
  created_at: string
}

export interface PodExecResponse {
  pod: string
  namespace: string
  container: string
  command: string[]
  shell_command: string
  exit_code: number
  success: boolean
  stdout: string
  stderr: string
  duration_ms: number
  output_excerpt: string
  session: ExecSessionSummary
}

export interface TerminalSessionResponse {
  pod: string
  namespace: string
  container: string
  shell: string
  terminal: {
    rows: number
    cols: number
  }
  text: string
  cursor: number
  session: StreamSessionSummary
}

export interface TerminalOutputResponse {
  text: string
  cursor: number
  status: string
  closed: boolean
  exit_code: number | null
  closed_at: string | null
}
