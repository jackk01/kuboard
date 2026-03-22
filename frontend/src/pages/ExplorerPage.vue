<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type {
  ClusterDiscoveryResponse,
  DiscoveryResource,
  PodExecResponse,
  PodLogsResponse,
  ResourceDetailResponse,
  ResourceListResponse,
  ResourcePermissionResponse,
  ResourceSchemaResponse,
  ResourceWatchResponse,
  StreamSessionRecord,
  StreamSessionSummary,
  TerminalOutputResponse,
  TerminalSessionResponse,
} from '../types'

const clusterStore = useClusterStore()
type WatchEventItem = ResourceWatchResponse['events'][number] & { received_at: string }

const selectedClusterId = ref('')
const selectedGroupKey = ref('')
const selectedResourceName = ref('')
const selectedNamespace = ref('')

const discovery = ref<ClusterDiscoveryResponse | null>(null)
const resourceList = ref<ResourceListResponse | null>(null)
const selectedItem = ref<Record<string, any> | null>(null)
const selectedDetail = ref<ResourceDetailResponse | null>(null)
const resourcePermissions = ref<ResourcePermissionResponse | null>(null)
const resourceSchema = ref<ResourceSchemaResponse | null>(null)
const formDraftObject = ref<Record<string, any> | null>(null)
const createOriginItem = ref<Record<string, any> | null>(null)
const editorText = ref('')
const isEditing = ref(false)
const isCreating = ref(false)
const editorMode = ref<'yaml' | 'form'>('yaml')
const detailError = ref('')
const permissionError = ref('')
const schemaError = ref('')
const applyError = ref('')
const applyMessage = ref('')
const loadingDetail = ref(false)
const loadingPermissions = ref(false)
const loadingSchema = ref(false)
const applying = ref(false)
const deleting = ref(false)
const watchActive = ref(false)
const watchLoading = ref(false)
const watchEvents = ref<WatchEventItem[]>([])
const watchError = ref('')
const watchCursor = ref('')
const watchSyncMessage = ref('')
const execResponse = ref<PodExecResponse | null>(null)
const execError = ref('')
const executing = ref(false)
const selectedExecContainer = ref('')
const execCommand = ref('id')
const execTimeoutSeconds = ref(15)
const execHistory = ref<StreamSessionRecord[]>([])
const execHistoryError = ref('')
const loadingExecHistory = ref(false)
const terminalSession = ref<TerminalSessionResponse | null>(null)
const terminalOutput = ref('')
const terminalError = ref('')
const terminalConnecting = ref(false)
const terminalSending = ref(false)
const terminalCursor = ref(0)
const terminalShell = ref('/bin/sh')
const terminalInput = ref('')
const terminalRows = ref(32)
const terminalCols = ref(120)
const logsResponse = ref<PodLogsResponse | null>(null)
const logsError = ref('')
const loadingLogs = ref(false)
const logsFollowing = ref(false)
const logFollowCursor = ref('')
const logFollowSession = ref<StreamSessionSummary | null>(null)
const selectedLogContainer = ref('')
const logTailLines = ref(200)
let watchLoopToken = 0
let watchTimer: number | null = null
let detailRefreshTimer: number | null = null
let logFollowLoopToken = 0
let logFollowTimer: number | null = null
let terminalLoopToken = 0
let terminalPollTimer: number | null = null

const loadingDiscovery = ref(false)
const loadingResources = ref(false)
const discoveryError = ref('')
const resourceError = ref('')

const selectedGroup = computed(() =>
  discovery.value?.groups.find(
    (group) => `${group.group}::${group.version}` === selectedGroupKey.value,
  ) ?? null,
)

const resources = computed<DiscoveryResource[]>(() => selectedGroup.value?.resources ?? [])

const selectedResource = computed(() =>
  resources.value.find((resource) => resource.name === selectedResourceName.value) ?? null,
)

const namespaceOptions = computed(() => discovery.value?.namespaces ?? [])
const permissionLabels: Record<string, string> = {
  get: '读取',
  list: '列表',
  watch: '监听',
  create: '创建',
  update: '更新',
  patch: 'Patch',
  delete: '删除',
}

const previewJson = computed(() =>
  selectedDetail.value
    ? JSON.stringify(selectedDetail.value.object, null, 2)
    : '// 选择一条资源后在这里查看原始对象',
)

const selectedNamespaceOrDefault = computed(
  () => selectedItem.value?.metadata?.namespace || selectedNamespace.value || discovery.value?.context.default_namespace || 'default',
)

const permissionEntries = computed(() =>
  Object.entries(resourcePermissions.value?.verbs ?? {}).map(([key, review]) => ({
    key,
    label: permissionLabels[key] ?? key,
    ...review,
  })),
)

const subresourceEntries = computed(() =>
  Object.entries(resourcePermissions.value?.subresources ?? {}).map(([key, review]) => ({
    key,
    label: key === 'log' ? '日志' : key === 'exec' ? 'Exec' : key,
    ...review,
  })),
)

const containerOptions = computed(() => extractContainerNames(selectedDetail.value?.object ?? null))
const schemaPreviewItems = computed(() => {
  const results: Array<{ path: string; type: string; required: boolean; description: string; depth: number }> = []

  function normalizeType(node: Record<string, any>) {
    if (typeof node.type === 'string') return node.type
    if (Array.isArray(node.type) && node.type.length) return node.type.join(' | ')
    if (node.$ref) return '$ref'
    if (node.properties) return 'object'
    if (node.items) return 'array'
    if (node.oneOf || node.anyOf || node.allOf) return 'union'
    return '--'
  }

  function walk(node: Record<string, any> | null | undefined, prefix = '', depth = 0, requiredKeys: string[] = []) {
    if (!node || depth > 2) {
      return
    }
    const properties = node.properties
    if (!properties || typeof properties !== 'object') {
      return
    }

    Object.entries(properties).forEach(([key, value]) => {
      if (!value || typeof value !== 'object') {
        return
      }
      const nextPath = prefix ? `${prefix}.${key}` : key
      results.push({
        path: nextPath,
        type: normalizeType(value as Record<string, any>),
        required: requiredKeys.includes(key),
        description: String((value as Record<string, any>).description || ''),
        depth,
      })
      walk(
        value as Record<string, any>,
        nextPath,
        depth + 1,
        Array.isArray((value as Record<string, any>).required) ? (value as Record<string, any>).required : [],
      )
      if ((value as Record<string, any>).items && typeof (value as Record<string, any>).items === 'object') {
        walk(
          (value as Record<string, any>).items as Record<string, any>,
          `${nextPath}[]`,
          depth + 1,
          Array.isArray(((value as Record<string, any>).items as Record<string, any>).required)
            ? (((value as Record<string, any>).items as Record<string, any>).required as string[])
            : [],
        )
      }
    })
  }

  walk(resourceSchema.value?.schema ?? null, '', 0, Array.isArray(resourceSchema.value?.schema?.required) ? resourceSchema.value?.schema?.required : [])
  return results.slice(0, 24)
})
const schemaJsonPreview = computed(() =>
  resourceSchema.value ? JSON.stringify(resourceSchema.value.schema, null, 2) : '// 选择资源后在这里查看结构化 schema',
)
const formEditableFields = computed(() => {
  const results: Array<{ path: string; type: string; required: boolean; description: string }> = []

  function walk(node: Record<string, any> | null | undefined, prefix = '', requiredKeys: string[] = [], depth = 0) {
    if (!node || depth > 3) {
      return
    }
    const properties = node.properties
    if (!properties || typeof properties !== 'object') {
      return
    }

    Object.entries(properties).forEach(([key, value]) => {
      if (!value || typeof value !== 'object') {
        return
      }
      const nextPath = prefix ? `${prefix}.${key}` : key
      const typeValue = Array.isArray((value as Record<string, any>).type)
        ? ((value as Record<string, any>).type as string[])[0]
        : String((value as Record<string, any>).type || '')

      if (
        nextPath.startsWith('spec.') &&
        ['string', 'integer', 'number', 'boolean'].includes(typeValue)
      ) {
        results.push({
          path: nextPath,
          type: typeValue,
          required: requiredKeys.includes(key),
          description: String((value as Record<string, any>).description || ''),
        })
      }

      if ((value as Record<string, any>).properties && !nextPath.includes('[]')) {
        walk(
          value as Record<string, any>,
          nextPath,
          Array.isArray((value as Record<string, any>).required) ? ((value as Record<string, any>).required as string[]) : [],
          depth + 1,
        )
      }
    })
  }

  walk(
    resourceSchema.value?.schema ?? null,
    '',
    Array.isArray(resourceSchema.value?.schema?.required) ? (resourceSchema.value?.schema?.required as string[]) : [],
    0,
  )

  return results.slice(0, 20)
})
const supportsFormEditing = computed(() => formEditableFields.value.length > 0)
const canCreateResource = computed(() => Boolean(resourcePermissions.value?.verbs.create?.allowed))
const canEditYaml = computed(
  () => Boolean(resourcePermissions.value?.verbs.patch?.allowed || resourcePermissions.value?.verbs.update?.allowed),
)
const canDeleteResource = computed(() => Boolean(resourcePermissions.value?.verbs.delete?.allowed))
const canWatchResources = computed(() => Boolean(resourcePermissions.value?.verbs.watch?.allowed))
const canExecPod = computed(
  () =>
    Boolean(
      isPodResource.value &&
        resourcePermissions.value?.subresources.exec?.allowed,
    ),
)
const canOpenTerminal = computed(() => canExecPod.value)
const canViewPodLogs = computed(
  () =>
    Boolean(
      selectedDetail.value?.resource.group === 'core' &&
        selectedDetail.value?.resource.name === 'pods' &&
        resourcePermissions.value?.subresources.log?.allowed,
    ),
)
const isPodResource = computed(
  () => selectedDetail.value?.resource.group === 'core' && selectedDetail.value?.resource.name === 'pods',
)

function extractContainerNames(object: Record<string, any> | null) {
  if (!object) {
    return [] as string[]
  }
  const spec = object.spec ?? {}
  const groups = [spec.initContainers, spec.containers, spec.ephemeralContainers]
  return groups
    .flatMap((items) => (Array.isArray(items) ? items : []))
    .map((item) => item?.name)
    .filter((name): name is string => Boolean(name))
}

function resetLogState() {
  const sessionId = logFollowSession.value?.id ?? null
  logsFollowing.value = false
  logFollowLoopToken += 1
  clearLogFollowTimer()
  logsResponse.value = null
  logsError.value = ''
  loadingLogs.value = false
  logFollowCursor.value = ''
  logFollowSession.value = null
  selectedLogContainer.value = ''
  logTailLines.value = 200
  if (sessionId) {
    void closeStreamSession(sessionId)
  }
}

function resetExecState() {
  execResponse.value = null
  execError.value = ''
  executing.value = false
  selectedExecContainer.value = ''
  execCommand.value = 'id'
  execTimeoutSeconds.value = 15
}

function resetExecHistory() {
  execHistory.value = []
  execHistoryError.value = ''
  loadingExecHistory.value = false
}

function clearTerminalPollTimer() {
  if (terminalPollTimer !== null) {
    window.clearTimeout(terminalPollTimer)
    terminalPollTimer = null
  }
}

function resetTerminalState(options: { closeRemote?: boolean } = {}) {
  const sessionId = terminalSession.value?.session.id ?? null
  terminalLoopToken += 1
  clearTerminalPollTimer()
  terminalSession.value = null
  terminalOutput.value = ''
  terminalError.value = ''
  terminalConnecting.value = false
  terminalSending.value = false
  terminalCursor.value = 0
  terminalInput.value = ''
  if (options.closeRemote !== false && sessionId) {
    void closeStreamSession(sessionId)
  }
}

function resetSchemaState() {
  resourceSchema.value = null
  schemaError.value = ''
  loadingSchema.value = false
}

function resetFormEditorState() {
  formDraftObject.value = null
  editorMode.value = 'yaml'
}

function resetCreateState() {
  isCreating.value = false
  createOriginItem.value = null
}

function clearWatchTimer() {
  if (watchTimer !== null) {
    window.clearTimeout(watchTimer)
    watchTimer = null
  }
}

function clearLogFollowTimer() {
  if (logFollowTimer !== null) {
    window.clearTimeout(logFollowTimer)
    logFollowTimer = null
  }
}

function clearDetailRefreshTimer() {
  if (detailRefreshTimer !== null) {
    window.clearTimeout(detailRefreshTimer)
    detailRefreshTimer = null
  }
}

function stopWatching(options: { keepEvents?: boolean } = {}) {
  watchLoopToken += 1
  watchActive.value = false
  watchLoading.value = false
  clearWatchTimer()
  clearDetailRefreshTimer()
  if (!options.keepEvents) {
    watchEvents.value = []
    watchError.value = ''
    watchCursor.value = ''
    watchSyncMessage.value = ''
  }
}

function formatWatchTime(timestamp: string) {
  const value = new Date(timestamp)
  if (Number.isNaN(value.getTime())) {
    return '--'
  }
  return value.toLocaleTimeString('zh-CN', { hour12: false })
}

function formatDateTime(timestamp?: string | null) {
  if (!timestamp) {
    return '--'
  }
  const value = new Date(timestamp)
  if (Number.isNaN(value.getTime())) {
    return '--'
  }
  return value.toLocaleString('zh-CN', { hour12: false })
}

function cloneObject<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

function getValueAtPath(target: Record<string, any> | null, path: string) {
  if (!target) {
    return undefined
  }
  return path.split('.').reduce<any>((cursor, segment) => {
    if (cursor && typeof cursor === 'object') {
      return cursor[segment]
    }
    return undefined
  }, target)
}

function setValueAtPath(target: Record<string, any>, path: string, value: unknown) {
  const segments = path.split('.')
  let cursor: Record<string, any> = target

  segments.forEach((segment, index) => {
    if (index === segments.length - 1) {
      cursor[segment] = value
      return
    }
    if (!cursor[segment] || typeof cursor[segment] !== 'object' || Array.isArray(cursor[segment])) {
      cursor[segment] = {}
    }
    cursor = cursor[segment]
  })
}

function mergeLogText(existingText: string, incomingText: string) {
  if (!incomingText.trim()) {
    return existingText
  }
  if (!existingText.trim()) {
    return incomingText
  }

  const existingLines = existingText.split('\n')
  const incomingLines = incomingText.split('\n')
  if (existingLines[existingLines.length - 1] === incomingLines[0]) {
    incomingLines.shift()
  }
  const suffix = incomingLines.join('\n')
  if (!suffix.trim()) {
    return existingText
  }
  return `${existingText.replace(/\n+$/, '')}\n${suffix}`
}

function watchEventBadgeClass(type: string) {
  if (type === 'ADDED') return 'status-success'
  if (type === 'DELETED') return 'status-denied'
  if (type === 'BOOKMARK') return 'status-warning'
  return 'status-info'
}

function sessionStatusClass(status: string) {
  if (status === 'success') return 'status-success'
  if (status === 'error') return 'status-denied'
  return 'status-warning'
}

function schemaSourceLabel(source?: string) {
  if (source === 'crd') return 'CRD Schema'
  if (source === 'openapi-v3') return 'OpenAPI v3'
  if (source === 'inferred') return '样本推断'
  return '--'
}

function buildResourceApiVersion() {
  if (!selectedGroup.value) {
    return ''
  }
  return selectedGroup.value.group === 'core' ? selectedGroup.value.version : `${selectedGroup.value.group}/${selectedGroup.value.version}`
}

function serializeDraftManifest(object: Record<string, any>) {
  return JSON.stringify(object, null, 2)
}

function buildDraftManifestObject() {
  if (!selectedResource.value) {
    return {} as Record<string, any>
  }

  const topLevelProperties = resourceSchema.value?.schema?.properties ?? {}
  const metadata: Record<string, any> = {}
  if (selectedResource.value.namespaced) {
    metadata.namespace = selectedNamespace.value || discovery.value?.context.default_namespace || 'default'
  }

  const draft: Record<string, any> = {
    apiVersion: buildResourceApiVersion(),
    kind: selectedResource.value.kind,
    metadata,
  }

  if (topLevelProperties.spec && typeof topLevelProperties.spec === 'object') {
    draft.spec = {}
  }
  if (topLevelProperties.data && typeof topLevelProperties.data === 'object') {
    draft.data = {}
  }
  if (topLevelProperties.stringData && typeof topLevelProperties.stringData === 'object') {
    draft.stringData = {}
  }
  if ((topLevelProperties.subjects as Record<string, any> | undefined)?.type === 'array') {
    draft.subjects = []
  }
  if ((topLevelProperties.rules as Record<string, any> | undefined)?.type === 'array') {
    draft.rules = []
  }

  return draft
}

function buildDraftDetail(): ResourceDetailResponse | null {
  if (!selectedResource.value || !selectedGroup.value) {
    return null
  }

  const object = buildDraftManifestObject()
  return {
    resource: {
      group: selectedGroup.value.group,
      version: selectedGroup.value.version,
      name: selectedResource.value.name,
      kind: selectedResource.value.kind,
      namespaced: selectedResource.value.namespaced,
      namespace: selectedResource.value.namespaced ? String((object.metadata ?? {}).namespace || '') : null,
      verbs: selectedResource.value.verbs,
    },
    object,
    yaml: serializeDraftManifest(object),
    metadata: {
      name: String((object.metadata ?? {}).name || ''),
      namespace: String((object.metadata ?? {}).namespace || ''),
      uid: '',
      resource_version: '',
      generation: null,
    },
  }
}

function hydrateFormDraft(object: Record<string, any> | null) {
  formDraftObject.value = object ? cloneObject(object) : null
}

function updateFormField(path: string, type: string, rawValue: string | boolean) {
  if (!formDraftObject.value) {
    return
  }

  let normalizedValue: unknown = rawValue
  if (type === 'integer') {
    normalizedValue = rawValue === '' ? null : Number.parseInt(String(rawValue), 10)
  } else if (type === 'number') {
    normalizedValue = rawValue === '' ? null : Number.parseFloat(String(rawValue))
  } else if (type === 'boolean') {
    normalizedValue = Boolean(rawValue)
  }

  setValueAtPath(formDraftObject.value, path, normalizedValue)
}

async function closeStreamSession(sessionId: number, statusValue = 'stopped') {
  try {
    await apiRequest(`/api/v1/streams/sessions/${sessionId}/close`, {
      method: 'POST',
      body: JSON.stringify({ status: statusValue }),
    })
  } catch {
    // Ignore close failures to avoid blocking the main UX.
  }
}

function appendWatchEvents(events: ResourceWatchResponse['events']) {
  if (!events.length) {
    return
  }
  const stampedEvents = events.map((event) => ({
    ...event,
    received_at: new Date().toISOString(),
  }))
  watchEvents.value = [...stampedEvents.reverse(), ...watchEvents.value].slice(0, 24)
}

function resourceItemKey(item: Record<string, any> | null) {
  const metadata = item?.metadata ?? {}
  return `${metadata.namespace || 'cluster'}:${metadata.name || ''}`
}

function updateContainerSelection(nextContainers: string[]) {
  if (!nextContainers.length) {
    selectedLogContainer.value = ''
    selectedExecContainer.value = ''
    return
  }
  if (!selectedLogContainer.value || !nextContainers.includes(selectedLogContainer.value)) {
    selectedLogContainer.value = nextContainers[0] ?? ''
  }
  if (!selectedExecContainer.value || !nextContainers.includes(selectedExecContainer.value)) {
    selectedExecContainer.value = nextContainers[0] ?? ''
  }
}

function clearSelectedResourceState(message = '') {
  selectedItem.value = null
  selectedDetail.value = null
  resourcePermissions.value = null
  resourceSchema.value = null
  formDraftObject.value = null
  createOriginItem.value = null
  editorText.value = ''
  isEditing.value = false
  isCreating.value = false
  editorMode.value = 'yaml'
  detailError.value = ''
  permissionError.value = ''
  applyError.value = ''
  applyMessage.value = ''
  resetLogState()
  resetExecState()
  resetExecHistory()
  resetTerminalState()
  watchSyncMessage.value = message
}

function syncResourceListFromWatch(events: ResourceWatchResponse['events']) {
  if (!resourceList.value || !events.length) {
    return
  }

  const nextItems = [...resourceList.value.items]
  let changed = false

  for (const event of events) {
    const item = event.object
    const itemKey = item?.metadata?.name
      ? resourceItemKey(item)
      : `${event.metadata.namespace || 'cluster'}:${event.metadata.name || ''}`
    const currentIndex = nextItems.findIndex((candidate) => resourceItemKey(candidate) === itemKey)

    if (event.type === 'DELETED') {
      if (currentIndex >= 0) {
        nextItems.splice(currentIndex, 1)
        changed = true
      }
      if (selectedItem.value && resourceItemKey(selectedItem.value) === itemKey) {
        clearSelectedResourceState(`当前选中的资源 ${event.metadata.name} 已被删除，详情视图已同步清空。`)
      }
      continue
    }

    if (!item?.metadata?.name) {
      continue
    }

    if (currentIndex >= 0) {
      nextItems.splice(currentIndex, 1, item)
    } else {
      nextItems.unshift(item)
    }
    changed = true

    if (selectedItem.value && resourceItemKey(selectedItem.value) === itemKey) {
      selectedItem.value = item
      scheduleSelectedDetailRefresh(item, event.type)
    }
  }

  if (!changed) {
    return
  }

  const latestResourceVersion =
    [...events]
      .reverse()
      .find((event) => event.metadata.resource_version)
      ?.metadata.resource_version || resourceList.value.metadata.resource_version

  resourceList.value = {
    ...resourceList.value,
    items: nextItems,
    metadata: {
      ...resourceList.value.metadata,
      count: nextItems.length,
      resource_version: latestResourceVersion,
    },
  }
}

function scheduleSelectedDetailRefresh(item: Record<string, any>, eventType: string) {
  clearDetailRefreshTimer()

  if (isEditing.value) {
    watchSyncMessage.value = `当前资源收到 ${eventType} 事件，编辑器内容已保留，避免自动覆盖你正在修改的 YAML。`
    return
  }

  watchSyncMessage.value = `收到 ${eventType} 事件，正在同步当前资源详情。`
  detailRefreshTimer = window.setTimeout(() => {
    void loadResourceDetail(item, {
      preserveFeedback: true,
      preserveStreams: true,
      fromWatch: true,
    })
  }, 320)
}

function summarizeStatus(item: Record<string, any>) {
  const status = item.status ?? {}
  if (typeof status.phase === 'string' && status.phase) {
    return status.phase
  }
  const conditions = Array.isArray(status.conditions)
    ? (status.conditions as Array<{ type?: string; status?: string }>)
    : []
  const ready = conditions.find((condition) => condition.type === 'Ready')
  return ready?.status ?? '--'
}

function formatAge(timestamp?: string) {
  if (!timestamp) {
    return '--'
  }
  const createdAt = new Date(timestamp).getTime()
  const diffMinutes = Math.max(Math.floor((Date.now() - createdAt) / 60000), 0)
  if (diffMinutes < 1) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h`
  return `${Math.floor(diffHours / 24)}d`
}

async function loadDiscovery() {
  if (!selectedClusterId.value) {
    return
  }

  stopWatching()
  clearDetailRefreshTimer()
  loadingDiscovery.value = true
  discoveryError.value = ''
  resourceList.value = null
  selectedItem.value = null
  selectedDetail.value = null
  resourcePermissions.value = null
  resourceSchema.value = null
  formDraftObject.value = null
  editorText.value = ''
  isEditing.value = false
  permissionError.value = ''
  schemaError.value = ''
  applyError.value = ''
  applyMessage.value = ''
  watchSyncMessage.value = ''
  resetLogState()
  resetExecState()
  resetExecHistory()
  resetTerminalState()
  resetSchemaState()
  resetFormEditorState()
  resetCreateState()

  try {
    const payload = await apiRequest<ClusterDiscoveryResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/discovery`,
    )
    discovery.value = payload
    await clusterStore.fetchClusters()
    const preferredGroup =
      payload.groups.find((group) => group.group === 'core' && group.version === 'v1') ?? payload.groups[0]
    selectedGroupKey.value = preferredGroup ? `${preferredGroup.group}::${preferredGroup.version}` : ''
    selectedResourceName.value =
      preferredGroup?.resources.find((resource) => resource.name === 'pods')?.name ??
      preferredGroup?.resources[0]?.name ??
      ''
    selectedNamespace.value = payload.context.default_namespace || payload.namespaces[0]?.name || 'default'
  } catch (error) {
    if (error instanceof ApiError) {
      discoveryError.value = error.message
    } else {
      discoveryError.value = '拉取 Discovery 失败，请检查后端日志。'
    }
  } finally {
    loadingDiscovery.value = false
  }
}

async function loadResourcePermissions(item: Record<string, any> | null = null) {
  if (!selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return
  }

  loadingPermissions.value = true
  permissionError.value = ''

  const namespace = selectedResource.value?.namespaced
    ? item?.metadata?.namespace || selectedNamespace.value || discovery.value?.context.default_namespace || 'default'
    : ''
  const name = item?.metadata?.name || ''
  const query = new URLSearchParams()

  if (namespace) {
    query.set('namespace', namespace)
  }
  if (name) {
    query.set('name', name)
  }
  const queryString = query.toString()

  try {
    resourcePermissions.value = await apiRequest<ResourcePermissionResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/permissions/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}${queryString ? `?${queryString}` : ''}`,
    )
  } catch (error) {
    resourcePermissions.value = null
    if (error instanceof ApiError) {
      permissionError.value = error.message
    } else {
      permissionError.value = '权限探测失败，请稍后再试。'
    }
  } finally {
    loadingPermissions.value = false
  }
}

async function loadResourceSchema() {
  if (!selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return
  }

  loadingSchema.value = true
  schemaError.value = ''

  try {
    resourceSchema.value = await apiRequest<ResourceSchemaResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/schemas/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}`,
    )
  } catch (error) {
    resourceSchema.value = null
    if (error instanceof ApiError) {
      schemaError.value = error.message
    } else {
      schemaError.value = '资源 Schema 读取失败。'
    }
  } finally {
    loadingSchema.value = false
  }
}

async function loadExecHistory() {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value) {
    resetExecHistory()
    return
  }

  loadingExecHistory.value = true
  execHistoryError.value = ''

  const query = new URLSearchParams({
    cluster: selectedClusterId.value,
    stream_type: 'exec',
    namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
    resource_name: selectedDetail.value.metadata.name,
    limit: '8',
  })

  try {
    execHistory.value = await apiRequest<StreamSessionRecord[]>(
      `/api/v1/streams/sessions?${query.toString()}`,
    )
  } catch (error) {
    execHistory.value = []
    if (error instanceof ApiError) {
      execHistoryError.value = error.message
    } else {
      execHistoryError.value = 'Exec 历史读取失败。'
    }
  } finally {
    loadingExecHistory.value = false
  }
}

async function loadResourceDetail(
  item: Record<string, any>,
  options: { preserveFeedback?: boolean; preserveStreams?: boolean; fromWatch?: boolean } = {},
) {
  if (!selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return
  }

  selectedItem.value = item
  loadingDetail.value = true
  detailError.value = ''
  permissionError.value = ''
  if (!options.preserveFeedback) {
    applyError.value = ''
    applyMessage.value = ''
  }
  if (!options.fromWatch) {
    watchSyncMessage.value = ''
  }
  isEditing.value = false
  editorMode.value = 'yaml'
  resetCreateState()
  if (!options.preserveStreams) {
    resetLogState()
    resetExecState()
    resetExecHistory()
    resetTerminalState()
  }

  const itemNamespace = item.metadata?.namespace
  const namespaceQuery =
    selectedResource.value?.namespaced && itemNamespace
      ? `?namespace=${encodeURIComponent(itemNamespace)}`
      : ''

  try {
    const payload = await apiRequest<ResourceDetailResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}/${encodeURIComponent(item.metadata?.name || '')}${namespaceQuery}`,
    )
    selectedDetail.value = payload
    editorText.value = payload.yaml
    hydrateFormDraft(payload.object)
    updateContainerSelection(extractContainerNames(payload.object))
    await loadResourcePermissions(item)
    if (payload.resource.group === 'core' && payload.resource.name === 'pods') {
      if (!options.preserveStreams || !execHistory.value.length) {
        await loadExecHistory()
      }
    } else if (!options.preserveStreams) {
      resetExecHistory()
      resetTerminalState()
    }
    if (options.fromWatch) {
      watchSyncMessage.value = `当前资源已根据 Watch 事件自动刷新，最新 RV 为 ${payload.metadata.resource_version || '--'}。`
    }
  } catch (error) {
    selectedDetail.value = null
    resourcePermissions.value = null
    resetFormEditorState()
    resetCreateState()
    resetExecHistory()
    resetTerminalState()
    if (error instanceof ApiError) {
      detailError.value = error.message
    } else {
      detailError.value = '资源详情读取失败。'
    }
  } finally {
    loadingDetail.value = false
  }
}

async function loadResources(options: { preserveFeedback?: boolean; targetKey?: string } = {}) {
  if (!selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return
  }

  const preferredItemKey =
    options.targetKey ||
    (selectedItem.value?.metadata?.name ? resourceItemKey(selectedItem.value) : '')

  stopWatching()
  clearDetailRefreshTimer()
  loadingResources.value = true
  resourceError.value = ''
  selectedItem.value = null
  selectedDetail.value = null
  resourcePermissions.value = null
  resourceSchema.value = null
  formDraftObject.value = null
  editorText.value = ''
  isEditing.value = false
  detailError.value = ''
  permissionError.value = ''
  schemaError.value = ''
  if (!options.preserveFeedback) {
    applyError.value = ''
    applyMessage.value = ''
  }
  watchSyncMessage.value = ''
  resetLogState()
  resetExecState()
  resetExecHistory()
  resetTerminalState()
  resetSchemaState()
  resetFormEditorState()
  resetCreateState()

  const namespaceQuery =
    selectedResource.value?.namespaced && selectedNamespace.value
      ? `?namespace=${encodeURIComponent(selectedNamespace.value)}`
      : ''

  try {
    resourceList.value = await apiRequest<ResourceListResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}${namespaceQuery}`,
    )
    await loadResourceSchema()
    await loadResourcePermissions()
    const preferredItem =
      (preferredItemKey
        ? resourceList.value.items.find((item) => resourceItemKey(item) === preferredItemKey) ?? null
        : null) || resourceList.value.items[0]
    if (preferredItem) {
      await loadResourceDetail(preferredItem, { preserveFeedback: options.preserveFeedback })
    }
  } catch (error) {
    resourceList.value = null
    if (error instanceof ApiError) {
      resourceError.value = error.message
    } else {
      resourceError.value = '资源读取失败。'
    }
  } finally {
    loadingResources.value = false
  }
}

function startEditing(mode: 'yaml' | 'form' = 'yaml') {
  if (!selectedDetail.value || (isCreating.value ? !canCreateResource.value : !canEditYaml.value)) {
    return
  }
  if (mode === 'form' && !supportsFormEditing.value) {
    applyError.value = '当前资源暂时没有可安全表单编辑的 schema 字段，请继续使用 YAML 模式。'
    return
  }
  applyError.value = ''
  isEditing.value = true
  editorMode.value = mode
  editorText.value = selectedDetail.value.yaml
  hydrateFormDraft(selectedDetail.value.object)
}

function startCreating(mode: 'yaml' | 'form' = 'yaml') {
  if (!selectedResource.value || !selectedGroup.value || !canCreateResource.value) {
    return
  }
  if (mode === 'form' && !supportsFormEditing.value) {
    applyError.value = '当前资源暂时没有可安全表单编辑的 schema 字段，请继续使用 YAML 模式。'
    return
  }

  const draftDetail = buildDraftDetail()
  if (!draftDetail) {
    return
  }

  createOriginItem.value = selectedItem.value ? cloneObject(selectedItem.value) : null
  selectedItem.value = null
  selectedDetail.value = draftDetail
  isCreating.value = true
  isEditing.value = true
  editorMode.value = mode
  editorText.value = draftDetail.yaml
  hydrateFormDraft(draftDetail.object)
  detailError.value = ''
  applyError.value = ''
  applyMessage.value = ''
  watchSyncMessage.value = ''
  resetLogState()
  resetExecState()
  resetExecHistory()
  resetTerminalState()
}

async function cancelEditing() {
  if (isCreating.value) {
    const originItem = createOriginItem.value ? cloneObject(createOriginItem.value) : null
    resetCreateState()
    isEditing.value = false
    editorMode.value = 'yaml'
    editorText.value = ''
    hydrateFormDraft(null)
    applyError.value = ''
    applyMessage.value = ''
    if (originItem) {
      await loadResourceDetail(originItem, { preserveFeedback: true })
    } else if (resourceList.value?.items[0]) {
      await loadResourceDetail(resourceList.value.items[0], { preserveFeedback: true })
    } else {
      selectedDetail.value = null
    }
    return
  }

  isEditing.value = false
  editorMode.value = 'yaml'
  editorText.value = selectedDetail.value?.yaml || ''
  hydrateFormDraft(selectedDetail.value?.object ?? null)
  applyError.value = ''
  applyMessage.value = ''
}

async function submitCreate(dryRun = false) {
  if (
    !selectedClusterId.value ||
    !selectedGroup.value ||
    !selectedResourceName.value ||
    !selectedDetail.value ||
    !canCreateResource.value
  ) {
    return
  }

  applying.value = true
  applyError.value = ''
  applyMessage.value = ''

  const namespaceQuery =
    selectedResource.value?.namespaced && selectedNamespaceOrDefault.value
      ? `?namespace=${encodeURIComponent(selectedNamespaceOrDefault.value)}`
      : ''

  try {
    const manifestText =
      isEditing.value && editorMode.value === 'form'
        ? JSON.stringify(formDraftObject.value ?? selectedDetail.value.object ?? {}, null, 2)
        : editorText.value
    const payload = await apiRequest<ResourceDetailResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}${namespaceQuery}`,
      {
        method: 'POST',
        body: JSON.stringify({
          manifest: manifestText,
          dry_run: dryRun,
          force: false,
        }),
      },
    )

    selectedDetail.value = payload
    editorText.value = payload.yaml
    hydrateFormDraft(payload.object)
    applyMessage.value = dryRun ? 'Dry-run 创建校验通过，后端已返回预览对象。' : 'Create 成功，资源已创建。'
    if (!dryRun) {
      isEditing.value = false
      resetCreateState()
      const successMessage = applyMessage.value
      await loadResources({
        preserveFeedback: true,
        targetKey: resourceItemKey(payload.object),
      })
      applyMessage.value = successMessage
    }
  } catch (error) {
    if (error instanceof ApiError) {
      applyError.value = error.message
    } else {
      applyError.value = '创建失败，请检查后端日志。'
    }
  } finally {
    applying.value = false
  }
}

async function submitApply(dryRun = false) {
  if (
    !selectedClusterId.value ||
    !selectedGroup.value ||
    !selectedResourceName.value ||
    !selectedItem.value ||
    !canEditYaml.value
  ) {
    return
  }

  applying.value = true
  applyError.value = ''
  applyMessage.value = ''

  const namespaceQuery =
    selectedResource.value?.namespaced && selectedNamespaceOrDefault.value
      ? `?namespace=${encodeURIComponent(selectedNamespaceOrDefault.value)}`
      : ''

  try {
    const manifestText =
      isEditing.value && editorMode.value === 'form'
        ? JSON.stringify(formDraftObject.value ?? selectedDetail.value?.object ?? {}, null, 2)
        : editorText.value
    const payload = await apiRequest<ResourceDetailResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}/${encodeURIComponent(selectedItem.value.metadata?.name || '')}/apply${namespaceQuery}`,
      {
        method: 'POST',
        body: JSON.stringify({
          manifest: manifestText,
          dry_run: dryRun,
          force: false,
        }),
      },
    )

    selectedDetail.value = payload
    editorText.value = payload.yaml
    hydrateFormDraft(payload.object)
    applyMessage.value = dryRun ? 'Dry-run 校验通过，后端已接受并返回预览对象。' : 'Apply 成功，资源已更新。'
    if (!dryRun) {
      isEditing.value = false
      const successMessage = applyMessage.value
      await loadResources({
        preserveFeedback: true,
        targetKey: resourceItemKey(payload.object),
      })
      applyMessage.value = successMessage
    }
  } catch (error) {
    if (error instanceof ApiError) {
      applyError.value = error.message
    } else {
      applyError.value = '提交失败，请检查后端日志。'
    }
  } finally {
    applying.value = false
  }
}

async function deleteResource() {
  if (
    !selectedClusterId.value ||
    !selectedGroup.value ||
    !selectedResourceName.value ||
    !selectedItem.value ||
    !canDeleteResource.value
  ) {
    return
  }

  const targetName = selectedItem.value.metadata?.name || ''
  if (!targetName) {
    return
  }

  const confirmed = window.confirm(`确认删除资源 ${targetName} 吗？这个操作不可撤销。`)
  if (!confirmed) {
    return
  }

  deleting.value = true
  applyError.value = ''
  applyMessage.value = ''

  const namespaceQuery =
    selectedResource.value?.namespaced && selectedNamespaceOrDefault.value
      ? `?namespace=${encodeURIComponent(selectedNamespaceOrDefault.value)}`
      : ''

  try {
    await apiRequest(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}/${encodeURIComponent(targetName)}${namespaceQuery}`,
      {
        method: 'DELETE',
      },
    )
    const successMessage = `资源 ${targetName} 已删除。`
    selectedItem.value = null
    selectedDetail.value = null
    editorText.value = ''
    isEditing.value = false
    await loadResources({ preserveFeedback: true })
    applyMessage.value = successMessage
  } catch (error) {
    if (error instanceof ApiError) {
      applyError.value = error.message
    } else {
      applyError.value = '删除失败，请检查后端日志。'
    }
  } finally {
    deleting.value = false
  }
}

async function loadPodLogs(options: { follow?: boolean; append?: boolean } = {}) {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value || !canViewPodLogs.value) {
    return
  }

  if (!options.append) {
    loadingLogs.value = true
  }
  if (!options.follow || !options.append) {
    logsError.value = ''
  }

  const query = new URLSearchParams({
    namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
    tail_lines: String(logTailLines.value),
    timestamps: 'true',
  })

  if (selectedLogContainer.value) {
    query.set('container', selectedLogContainer.value)
  }
  if (options.follow) {
    query.set('follow', 'true')
    const sinceTime = logFollowCursor.value || logsResponse.value?.cursor.since_time || ''
    if (sinceTime) {
      query.set('since_time', sinceTime)
    }
    if (logFollowSession.value) {
      query.set('session_id', String(logFollowSession.value.id))
    }
  }

  try {
    const payload = await apiRequest<PodLogsResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/core/v1/pods/${encodeURIComponent(selectedDetail.value.metadata.name)}/logs?${query.toString()}`,
    )
    logsResponse.value =
      options.append && logsResponse.value
        ? {
            ...payload,
            text: mergeLogText(logsResponse.value.text, payload.text),
          }
        : payload
    logFollowCursor.value = payload.cursor.since_time || logFollowCursor.value
    logFollowSession.value = payload.session
  } catch (error) {
    if (!options.append) {
      logsResponse.value = null
    }
    if (error instanceof ApiError) {
      logsError.value = error.message
    } else {
      logsError.value = '日志读取失败。'
    }
    if (options.follow) {
      logsFollowing.value = false
      logFollowLoopToken += 1
      clearLogFollowTimer()
    }
  } finally {
    if (!options.append) {
      loadingLogs.value = false
    }
  }
}

async function runLogFollowLoop(loopToken: number, append = false) {
  if (
    !logsFollowing.value ||
    loopToken !== logFollowLoopToken ||
    !selectedClusterId.value ||
    !selectedDetail.value ||
    !isPodResource.value
  ) {
    return
  }

  await loadPodLogs({ follow: true, append })

  if (logsFollowing.value && loopToken === logFollowLoopToken) {
    logFollowTimer = window.setTimeout(() => {
      void runLogFollowLoop(loopToken, true)
    }, 2200)
  }
}

function startLogFollowing() {
  if (!canViewPodLogs.value || !selectedDetail.value) {
    return
  }

  logsFollowing.value = true
  logsError.value = ''
  logFollowLoopToken += 1
  clearLogFollowTimer()
  logFollowCursor.value = logsResponse.value?.cursor.since_time || ''
  void runLogFollowLoop(logFollowLoopToken, Boolean(logsResponse.value))
}

function stopLogFollowing() {
  const sessionId = logFollowSession.value?.id ?? null
  logsFollowing.value = false
  logFollowLoopToken += 1
  clearLogFollowTimer()
  logFollowCursor.value = ''
  logFollowSession.value = null
  if (sessionId) {
    void closeStreamSession(sessionId)
  }
}

async function executePodCommand() {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value || !canExecPod.value) {
    return
  }

  executing.value = true
  execError.value = ''

  try {
    execResponse.value = await apiRequest<PodExecResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/core/v1/pods/${encodeURIComponent(selectedDetail.value.metadata.name)}/exec`,
      {
        method: 'POST',
        body: JSON.stringify({
          namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
          container: selectedExecContainer.value || undefined,
          shell_command: execCommand.value,
          timeout_seconds: execTimeoutSeconds.value,
        }),
      },
    )
    await loadExecHistory()
  } catch (error) {
    execResponse.value = null
    if (error instanceof ApiError) {
      execError.value = error.message
    } else {
      execError.value = 'Pod Exec 执行失败。'
    }
  } finally {
    executing.value = false
  }
}

async function pollTerminalOutput(loopToken: number) {
  if (!terminalSession.value || loopToken !== terminalLoopToken) {
    return
  }

  try {
    const payload = await apiRequest<TerminalOutputResponse>(
      `/api/v1/streams/sessions/${terminalSession.value.session.id}/output?cursor=${terminalCursor.value}`,
    )
    if (loopToken !== terminalLoopToken) {
      return
    }
    if (payload.text) {
      terminalOutput.value = `${terminalOutput.value}${payload.text}`.slice(-60000)
    }
    terminalCursor.value = payload.cursor
    if (payload.closed) {
      terminalSession.value = {
        ...terminalSession.value,
        session: {
          ...terminalSession.value.session,
          status: payload.status,
          closed_at: payload.closed_at,
        },
      }
      return
    }
  } catch (error) {
    if (loopToken !== terminalLoopToken) {
      return
    }
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端输出读取失败。'
    }
    return
  }

  if (terminalSession.value && loopToken === terminalLoopToken) {
    terminalPollTimer = window.setTimeout(() => {
      void pollTerminalOutput(loopToken)
    }, 900)
  }
}

async function openTerminalSession() {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value || !canOpenTerminal.value) {
    return
  }

  resetTerminalState()
  terminalConnecting.value = true
  terminalError.value = ''

  try {
    terminalSession.value = await apiRequest<TerminalSessionResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/core/v1/pods/${encodeURIComponent(selectedDetail.value.metadata.name)}/terminal`,
      {
        method: 'POST',
        body: JSON.stringify({
          namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
          container: selectedExecContainer.value || undefined,
          shell: terminalShell.value,
          rows: terminalRows.value,
          cols: terminalCols.value,
        }),
      },
    )
    terminalOutput.value = terminalSession.value.text || ''
    terminalCursor.value = terminalSession.value.cursor || 0
    terminalLoopToken += 1
    void pollTerminalOutput(terminalLoopToken)
  } catch (error) {
    terminalSession.value = null
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端建立失败。'
    }
  } finally {
    terminalConnecting.value = false
  }
}

async function sendTerminalInput(data: string) {
  if (!terminalSession.value || !data) {
    return
  }

  terminalSending.value = true
  terminalError.value = ''
  try {
    await apiRequest(`/api/v1/streams/sessions/${terminalSession.value.session.id}/input`, {
      method: 'POST',
      body: JSON.stringify({ input: data }),
    })
  } catch (error) {
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端输入发送失败。'
    }
  } finally {
    terminalSending.value = false
  }
}

async function submitTerminalInput() {
  const value = terminalInput.value
  if (!value.trim()) {
    return
  }
  terminalInput.value = ''
  await sendTerminalInput(`${value}\n`)
}

async function sendTerminalShortcut(shortcut: 'enter' | 'ctrlc') {
  await sendTerminalInput(shortcut === 'enter' ? '\n' : '\u0003')
}

async function resizeTerminal() {
  if (!terminalSession.value) {
    return
  }
  try {
    await apiRequest(`/api/v1/streams/sessions/${terminalSession.value.session.id}/resize`, {
      method: 'POST',
      body: JSON.stringify({
        rows: terminalRows.value,
        cols: terminalCols.value,
      }),
    })
  } catch (error) {
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端尺寸调整失败。'
    }
  }
}

async function runWatchLoop(loopToken: number) {
  if (
    !watchActive.value ||
    loopToken !== watchLoopToken ||
    !selectedClusterId.value ||
    !selectedGroup.value ||
    !selectedResourceName.value
  ) {
    return
  }

  watchLoading.value = true
  watchError.value = ''

  const query = new URLSearchParams({
    timeout_seconds: '8',
  })

  if (selectedResource.value?.namespaced) {
    query.set('namespace', selectedNamespace.value || discovery.value?.context.default_namespace || 'default')
  }
  if (watchCursor.value) {
    query.set('resource_version', watchCursor.value)
  }

  try {
    const payload = await apiRequest<ResourceWatchResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/watch/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}?${query.toString()}`,
    )
    if (loopToken !== watchLoopToken) {
      return
    }
    if (payload.metadata.next_resource_version) {
      watchCursor.value = payload.metadata.next_resource_version
    } else if (!watchCursor.value) {
      watchCursor.value = payload.metadata.resource_version
    }
    appendWatchEvents(payload.events)
    syncResourceListFromWatch(payload.events)
  } catch (error) {
    if (loopToken !== watchLoopToken) {
      return
    }
    watchActive.value = false
    if (error instanceof ApiError) {
      watchError.value = error.message
    } else {
      watchError.value = '资源 Watch 失败，请稍后重试。'
    }
    return
  } finally {
    if (loopToken === watchLoopToken) {
      watchLoading.value = false
    }
  }

  if (watchActive.value && loopToken === watchLoopToken) {
    watchTimer = window.setTimeout(() => {
      void runWatchLoop(loopToken)
    }, 500)
  }
}

function startWatching() {
  if (!canWatchResources.value || !selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return
  }

  stopWatching()
  watchSyncMessage.value = ''
  watchEvents.value = []
  watchError.value = ''
  watchCursor.value =
    resourceList.value?.metadata.resource_version || selectedDetail.value?.metadata.resource_version || ''
  watchActive.value = true
  watchLoopToken += 1
  void runWatchLoop(watchLoopToken)
}

onMounted(async () => {
  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }
  selectedClusterId.value = clusterStore.items[0]?.id ?? ''
})

onBeforeUnmount(() => {
  stopLogFollowing()
  resetTerminalState()
  clearDetailRefreshTimer()
  stopWatching({ keepEvents: true })
})

watch(selectedClusterId, async (value, oldValue) => {
  if (!value || value === oldValue) {
    return
  }
  await loadDiscovery()
})

watch(selectedGroupKey, () => {
  selectedResourceName.value = resources.value[0]?.name ?? ''
})

watch(
  [selectedGroupKey, selectedResourceName, selectedNamespace],
  async ([groupKey, resourceName]) => {
    if (!groupKey || !resourceName) {
      return
    }
    await loadResources()
  },
)
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel">
      <div class="section-head">
        <div>
          <div class="eyebrow" style="color: var(--kb-primary-deep)">Explorer</div>
          <h2 class="page-title">真实资源 MVP</h2>
          <p class="page-description">
            这里已经接上后端 Discovery 和通用资源列表接口。导入真实可访问的 kubeconfig 后，可以浏览集群内的常见资源。
          </p>
        </div>
        <button class="button button-secondary" :disabled="loadingDiscovery" @click="loadDiscovery">
          {{ loadingDiscovery ? '同步中...' : '刷新 Discovery' }}
        </button>
      </div>

      <div class="toolbar-grid">
        <label class="field-label">
          集群
          <select v-model="selectedClusterId">
            <option disabled value="">请选择集群</option>
            <option v-for="cluster in clusterStore.items" :key="cluster.id" :value="cluster.id">
              {{ cluster.name }}
            </option>
          </select>
        </label>

        <label class="field-label">
          API Group / Version
          <select v-model="selectedGroupKey" :disabled="!discovery">
            <option disabled value="">请选择资源组</option>
            <option v-for="group in discovery?.groups ?? []" :key="`${group.group}::${group.version}`" :value="`${group.group}::${group.version}`">
              {{ group.group }} / {{ group.version }}
            </option>
          </select>
        </label>

        <label class="field-label">
          Resource
          <select v-model="selectedResourceName" :disabled="!resources.length">
            <option disabled value="">请选择资源</option>
            <option v-for="resource in resources" :key="resource.name" :value="resource.name">
              {{ resource.name }} ({{ resource.kind }})
            </option>
          </select>
        </label>

        <label class="field-label">
          Namespace
          <select v-model="selectedNamespace" :disabled="!selectedResource?.namespaced">
            <option value="">cluster-scoped</option>
            <option v-for="namespace in namespaceOptions" :key="namespace.name" :value="namespace.name">
              {{ namespace.name }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="discoveryError" class="error-text" style="margin-top: 14px">{{ discoveryError }}</div>
      <div v-else-if="discovery" class="button-row" style="margin-top: 16px">
        <StatusBadge :value="clusterStore.items.find((cluster) => cluster.id === selectedClusterId)?.status || 'ready'" />
        <span class="muted">
          Kubernetes {{ discovery.version.gitVersion || '--' }} · 默认命名空间 {{ discovery.context.default_namespace }}
        </span>
      </div>
    </section>

    <section class="split-detail">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <h2>资源列表</h2>
            <p>
              {{
                selectedResource
                  ? `当前资源：${selectedResource.kind} / ${selectedResource.name}`
                  : '先完成 Discovery 再选择资源'
              }}
            </p>
          </div>
        </div>

        <div v-if="loadingResources" class="helper-text">正在读取资源...</div>
        <div v-else-if="resourceError" class="error-text">{{ resourceError }}</div>
        <table v-else-if="resourceList?.items.length" class="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Namespace</th>
              <th>Status</th>
              <th>Age</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in resourceList.items"
              :key="`${item.metadata?.namespace || 'cluster'}:${item.metadata?.name}`"
              :class="{
                'table-row-active':
                  selectedItem?.metadata?.name === item.metadata?.name &&
                  (selectedItem?.metadata?.namespace || '') === (item.metadata?.namespace || ''),
              }"
              @click="loadResourceDetail(item)"
              style="cursor: pointer"
            >
              <td>
                <strong>{{ item.metadata?.name || '--' }}</strong>
              </td>
              <td>{{ item.metadata?.namespace || '--' }}</td>
              <td>{{ summarizeStatus(item) }}</td>
              <td>{{ formatAge(item.metadata?.creationTimestamp) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          {{
            selectedResource
              ? '当前查询没有返回资源，可能是资源为空，或者当前账号没有读取权限。'
              : '导入真实集群并完成 Discovery 后，这里会显示实际资源。'
          }}
        </div>
      </article>

      <article class="surface-card">
        <div class="section-head">
          <div>
            <h2>详情与 YAML</h2>
            <p>现在支持资源新建、YAML/JSON 与基础表单双模式编辑，会先探测真实权限，再决定是否允许修改或创建。</p>
          </div>
          <div class="button-row">
            <button
              class="button button-secondary"
              :disabled="!selectedResource || loadingPermissions || (!canCreateResource && !isCreating)"
              @click="isCreating ? cancelEditing() : startCreating('yaml')"
            >
              {{ isCreating ? '取消新建' : '新建资源' }}
            </button>
            <button
              class="button button-secondary"
              :disabled="!selectedDetail || loadingPermissions || (isCreating ? !canCreateResource : !canEditYaml)"
              @click="isCreating ? startEditing('yaml') : isEditing && editorMode === 'yaml' ? cancelEditing() : startEditing('yaml')"
            >
              {{ isCreating ? 'YAML 草稿' : isEditing && editorMode === 'yaml' ? '取消 YAML' : 'YAML 编辑' }}
            </button>
            <button
              class="button button-secondary"
              :disabled="!selectedDetail || loadingPermissions || (isCreating ? !canCreateResource : !canEditYaml) || !supportsFormEditing"
              @click="isCreating ? startEditing('form') : isEditing && editorMode === 'form' ? cancelEditing() : startEditing('form')"
            >
              {{ isCreating ? '表单草稿' : isEditing && editorMode === 'form' ? '取消表单' : '表单编辑' }}
            </button>
            <button
              class="button button-secondary"
              :disabled="!selectedDetail || applying || !isEditing || (isCreating ? !canCreateResource : !canEditYaml)"
              @click="isCreating ? submitCreate(true) : submitApply(true)"
            >
              {{ applying ? '处理中...' : isCreating ? 'Dry-run Create' : 'Dry-run' }}
            </button>
            <button
              class="button button-primary"
              :disabled="!selectedDetail || applying || !isEditing || (isCreating ? !canCreateResource : !canEditYaml)"
              @click="isCreating ? submitCreate(false) : submitApply(false)"
            >
              {{ applying ? (isCreating ? '创建中...' : '提交中...') : isCreating ? 'Create' : 'Apply' }}
            </button>
            <button
              class="button button-secondary"
              :disabled="!selectedDetail || isCreating || applying || deleting || loadingPermissions || !canDeleteResource"
              @click="deleteResource"
            >
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </div>
        </div>

        <div v-if="detailError" class="error-text" style="margin-bottom: 12px">{{ detailError }}</div>
        <div v-if="permissionError" class="error-text" style="margin-bottom: 12px">{{ permissionError }}</div>
        <div v-if="applyError" class="error-text" style="margin-bottom: 12px">{{ applyError }}</div>
        <div v-if="applyMessage" class="helper-text" style="margin-bottom: 12px">{{ applyMessage }}</div>
        <div v-if="isCreating" class="helper-text" style="margin-bottom: 12px">
          当前处于新建草稿模式，编辑器接受 YAML 或 JSON；Create 会调用 Kubernetes 资源集合创建接口。
        </div>

        <div v-if="selectedDetail" class="pill-row" style="margin-bottom: 14px">
          <span class="pill" v-if="isCreating">Mode: create-draft</span>
          <span class="pill">Kind: {{ selectedDetail.resource.kind }}</span>
          <span class="pill">Name: {{ selectedDetail.metadata.name || '--draft--' }}</span>
          <span class="pill" v-if="selectedDetail.metadata.namespace">Namespace: {{ selectedDetail.metadata.namespace }}</span>
          <span class="pill">RV: {{ selectedDetail.metadata.resource_version || '--' }}</span>
        </div>

        <div v-if="selectedDetail" class="permission-card" style="margin-bottom: 14px">
          <div class="section-head" style="margin-bottom: 12px">
            <div>
              <h2 style="font-size: 15px">权限感知</h2>
              <p>权限结果来自 Kubernetes 自身鉴权接口，不依赖前端静态猜测。</p>
            </div>
            <span v-if="loadingPermissions" class="helper-text">探测中...</span>
          </div>

          <div v-if="permissionEntries.length" class="permission-grid">
            <div v-for="permission in permissionEntries" :key="permission.key" class="permission-chip">
              <span>{{ permission.label }}</span>
              <span
                class="status-badge"
                :class="permission.allowed ? 'status-ready' : 'status-denied'"
              >
                {{ permission.allowed ? 'allowed' : 'denied' }}
              </span>
            </div>
          </div>
          <div v-if="subresourceEntries.length" class="permission-grid" style="margin-top: 10px">
            <div v-for="permission in subresourceEntries" :key="permission.key" class="permission-chip">
              <span>{{ permission.label }}</span>
              <span
                class="status-badge"
                :class="permission.allowed ? 'status-ready' : 'status-denied'"
              >
                {{ permission.allowed ? 'allowed' : 'denied' }}
              </span>
            </div>
          </div>
          <div
            v-if="selectedDetail && !loadingPermissions && !permissionError && isCreating && !canCreateResource"
            class="helper-text"
            style="margin-top: 12px"
          >
            当前账号没有该资源的 create 权限，新建草稿已保留，但不能提交。
          </div>
          <div
            v-else-if="selectedDetail && !loadingPermissions && !permissionError && !isCreating && !canEditYaml"
            class="helper-text"
            style="margin-top: 12px"
          >
            当前账号没有该对象的更新或 patch 权限，YAML 编辑已自动转为只读模式。
          </div>
        </div>

        <div v-if="selectedResource" class="permission-card" style="margin-bottom: 14px">
          <div class="section-head" style="margin-bottom: 12px">
            <div>
              <h2 style="font-size: 15px">Schema 预览</h2>
              <p>优先使用 CRD/OpenAPI 结构，拿不到时回退到样本对象推断，先为表单编辑器铺底。</p>
            </div>
            <span v-if="loadingSchema" class="helper-text">读取中...</span>
          </div>

          <div v-if="schemaError" class="error-text" style="margin-bottom: 12px">{{ schemaError }}</div>
          <template v-else-if="resourceSchema">
            <div class="pill-row" style="margin-bottom: 12px">
              <span class="pill">Source: {{ schemaSourceLabel(resourceSchema.source) }}</span>
              <span class="pill">Schema: {{ resourceSchema.schema_name || '--' }}</span>
            </div>

            <div v-if="schemaPreviewItems.length" class="schema-list">
              <div
                v-for="field in schemaPreviewItems"
                :key="field.path"
                class="schema-item"
              >
                <div class="button-row" style="justify-content: space-between">
                  <strong :style="{ paddingLeft: `${field.depth * 12}px` }">{{ field.path }}</strong>
                  <span class="status-badge" :class="field.required ? 'status-warning' : 'status-info'">
                    {{ field.type }}
                  </span>
                </div>
                <div class="muted" style="margin-top: 8px">
                  {{ field.required ? 'required' : 'optional' }}{{ field.description ? ` · ${field.description}` : '' }}
                </div>
              </div>
            </div>
            <div v-else class="helper-text" style="margin-bottom: 12px">
              当前 schema 没有可展开的 `properties`，但原始结构仍可在下面查看。
            </div>

            <pre class="json-block" style="margin-top: 12px; max-height: 260px">{{ schemaJsonPreview }}</pre>
          </template>
          <div v-else class="helper-text">切换到具体资源后，这里会显示对应结构描述。</div>
        </div>

        <div v-if="selectedDetail" class="permission-card" style="margin-bottom: 14px">
          <div class="section-head" style="margin-bottom: 12px">
            <div>
              <h2 style="font-size: 15px">资源 Watch</h2>
              <p>基于 Kubernetes Watch API 持续拉取增量事件，用来观察资源变化而不是重复全量刷新。</p>
            </div>
            <div class="button-row">
              <button
                class="button button-secondary"
                :disabled="(!canWatchResources && !watchActive) || loadingPermissions"
                @click="watchActive ? stopWatching({ keepEvents: true }) : startWatching()"
              >
                {{ watchActive ? '停止 Watch' : watchLoading ? '连接中...' : '开始 Watch' }}
              </button>
            </div>
          </div>

          <div class="pill-row" style="margin-bottom: 12px">
            <span class="pill">Cursor: {{ watchCursor || resourceList?.metadata.resource_version || '--' }}</span>
            <span class="pill">Events: {{ watchEvents.length }}</span>
            <span class="pill">{{ watchActive ? '状态: watching' : '状态: idle' }}</span>
          </div>

          <div v-if="!canWatchResources && !loadingPermissions" class="helper-text" style="margin-bottom: 12px">
            当前账号没有该资源的 watch 权限，因此这里只展示静态列表。
          </div>
          <div v-if="watchError" class="error-text" style="margin-bottom: 12px">{{ watchError }}</div>
          <div v-if="watchSyncMessage" class="helper-text" style="margin-bottom: 12px">{{ watchSyncMessage }}</div>

          <div v-if="watchEvents.length" class="event-list">
            <div
              v-for="event in watchEvents"
              :key="`${event.type}:${event.metadata.namespace}:${event.metadata.name}:${event.metadata.resource_version}:${event.received_at}`"
              class="event-item"
            >
              <div class="button-row" style="justify-content: space-between">
                <div class="button-row">
                  <span class="status-badge" :class="watchEventBadgeClass(event.type)">
                    {{ event.type.toLowerCase() }}
                  </span>
                  <strong>{{ event.metadata.name || '--' }}</strong>
                </div>
                <span class="muted">{{ formatWatchTime(event.received_at) }}</span>
              </div>
              <div class="muted" style="margin-top: 8px">
                {{ event.metadata.kind || selectedDetail.resource.kind }} · namespace {{ event.metadata.namespace || '--' }} · rv
                {{ event.metadata.resource_version || '--' }}
              </div>
            </div>
          </div>
          <div v-else class="helper-text">
            {{ watchLoading ? 'Watch 已连接，正在等待事件...' : '开始 Watch 后，这里会显示最近的 ADDED / MODIFIED / DELETED / BOOKMARK 事件。' }}
          </div>
        </div>

        <div v-if="isEditing && editorMode === 'form'" class="permission-card" style="margin-bottom: 14px">
          <div class="section-head" style="margin-bottom: 12px">
            <div>
              <h2 style="font-size: 15px">表单编辑器 Beta</h2>
              <p>这里优先暴露 schema 中识别出的常见标量字段，复杂对象仍建议切回 YAML 模式处理。</p>
            </div>
          </div>

          <div v-if="formEditableFields.length" class="form-grid">
            <label
              v-for="field in formEditableFields"
              :key="field.path"
              class="field-label"
            >
              {{ field.path }}
              <input
                v-if="field.type === 'string'"
                :value="String(getValueAtPath(formDraftObject, field.path) ?? '')"
                type="text"
                @input="updateFormField(field.path, field.type, ($event.target as HTMLInputElement).value)"
              />
              <input
                v-else-if="field.type === 'integer' || field.type === 'number'"
                :value="String(getValueAtPath(formDraftObject, field.path) ?? '')"
                :type="field.type === 'integer' ? 'number' : 'text'"
                @input="updateFormField(field.path, field.type, ($event.target as HTMLInputElement).value)"
              />
              <select
                v-else-if="field.type === 'boolean'"
                :value="String(Boolean(getValueAtPath(formDraftObject, field.path)))"
                @change="updateFormField(field.path, field.type, ($event.target as HTMLSelectElement).value === 'true')"
              >
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
              <input
                v-else
                :value="String(getValueAtPath(formDraftObject, field.path) ?? '')"
                type="text"
                @input="updateFormField(field.path, field.type, ($event.target as HTMLInputElement).value)"
              />
              <span class="muted">
                {{ field.required ? 'required' : 'optional' }}{{ field.description ? ` · ${field.description}` : '' }}
              </span>
            </label>
          </div>
          <div v-else class="helper-text">
            当前资源没有可安全表单编辑的 schema 字段，请切换回 YAML 模式。
          </div>
        </div>
        <textarea
          v-else-if="isEditing"
          v-model="editorText"
          class="editor-surface"
          spellcheck="false"
        />
        <pre v-else class="json-block">{{ selectedDetail?.yaml || previewJson }}</pre>

        <section v-if="isPodResource && !isCreating" class="log-panel">
          <div class="section-head">
            <div>
              <h2 style="font-size: 15px">Pod 日志</h2>
              <p>现在支持基础读取和持续跟随；先用短轮询做稳定版 follow，后续再升级成真正的流式追踪。</p>
            </div>
            <div class="button-row">
              <button
                class="button button-secondary"
                :disabled="loadingLogs || !canViewPodLogs || logsFollowing"
                @click="() => loadPodLogs()"
              >
                {{ loadingLogs ? '读取中...' : logsResponse ? '刷新日志' : '查看日志' }}
              </button>
              <button
                class="button button-secondary"
                :disabled="loadingLogs || !canViewPodLogs"
                @click="logsFollowing ? stopLogFollowing() : startLogFollowing()"
              >
                {{ logsFollowing ? '停止跟随' : '开始跟随' }}
              </button>
            </div>
          </div>

          <div class="toolbar-grid logs-toolbar">
            <label class="field-label">
              Container
              <select v-model="selectedLogContainer" :disabled="!containerOptions.length || !canViewPodLogs">
                <option value="">自动选择</option>
                <option v-for="container in containerOptions" :key="container" :value="container">
                  {{ container }}
                </option>
              </select>
            </label>

            <label class="field-label">
              Tail Lines
              <input v-model.number="logTailLines" type="number" min="10" max="2000" :disabled="!canViewPodLogs" />
            </label>
          </div>

          <div v-if="logsResponse || logFollowSession" class="pill-row" style="margin-bottom: 12px">
            <span class="pill">状态: {{ logsFollowing ? 'following' : 'idle' }}</span>
            <span class="pill">Cursor: {{ logFollowCursor || logsResponse?.cursor.since_time || '--' }}</span>
            <span class="pill" v-if="logFollowSession">Session: #{{ logFollowSession.id }}</span>
          </div>

          <div v-if="!canViewPodLogs && !loadingPermissions" class="helper-text" style="margin-bottom: 12px">
            当前账号没有 `pods/log` 读取权限，日志面板已保持只读不可用。
          </div>
          <div v-if="logsError" class="error-text" style="margin-bottom: 12px">{{ logsError }}</div>
          <div v-if="logsFollowing && !logsError" class="helper-text" style="margin-bottom: 12px">
            正在持续跟随最新日志输出，切换资源或停止跟随后会自动关闭当前会话。
          </div>
          <pre v-if="logsResponse" class="json-block log-block">{{ logsResponse.text }}</pre>
        </section>

        <section v-if="isPodResource && !isCreating" class="log-panel">
          <div class="section-head">
            <div>
              <h2 style="font-size: 15px">Web Terminal Beta</h2>
              <p>这里提供持续会话型 Pod 终端，支持连接、输入、轮询输出和主动断开，适合连续排障。</p>
            </div>
            <div class="button-row">
              <button
                class="button button-secondary"
                :disabled="terminalConnecting || !canOpenTerminal || Boolean(terminalSession)"
                @click="openTerminalSession"
              >
                {{ terminalConnecting ? '连接中...' : terminalSession ? '已连接' : '打开终端' }}
              </button>
              <button
                class="button button-secondary"
                :disabled="!terminalSession"
                @click="resetTerminalState()"
              >
                断开终端
              </button>
            </div>
          </div>

          <div class="toolbar-grid terminal-toolbar">
            <label class="field-label">
              Shell
              <select v-model="terminalShell" :disabled="Boolean(terminalSession) || !canOpenTerminal">
                <option value="/bin/sh">/bin/sh</option>
                <option value="/bin/bash">/bin/bash</option>
              </select>
            </label>

            <label class="field-label">
              Rows
              <input v-model.number="terminalRows" type="number" min="12" max="120" :disabled="!canOpenTerminal" />
            </label>

            <label class="field-label">
              Cols
              <input v-model.number="terminalCols" type="number" min="40" max="240" :disabled="!canOpenTerminal" />
            </label>

            <label class="field-label">
              Action
              <button class="button button-secondary" :disabled="!terminalSession" @click="resizeTerminal">
                应用尺寸
              </button>
            </label>
          </div>

          <div v-if="terminalSession" class="pill-row" style="margin-bottom: 12px">
            <span class="pill">Session: #{{ terminalSession.session.id }}</span>
            <span class="pill">Shell: {{ terminalSession.shell }}</span>
            <span class="pill">Cursor: {{ terminalCursor }}</span>
            <span class="pill">状态: {{ terminalSession.session.status }}</span>
          </div>

          <div v-if="!canOpenTerminal && !loadingPermissions" class="helper-text" style="margin-bottom: 12px">
            当前账号没有 `pods/exec` 权限，终端功能不可用。
          </div>
          <div v-if="terminalError" class="error-text" style="margin-bottom: 12px">{{ terminalError }}</div>

          <pre class="json-block terminal-block">{{ terminalOutput || '$ terminal idle' }}</pre>

          <div class="toolbar-grid terminal-toolbar">
            <label class="field-label" style="grid-column: span 2">
              Send Input
              <textarea
                v-model="terminalInput"
                placeholder="输入命令后点发送，例如：ls -la"
                :disabled="!terminalSession"
              />
            </label>

            <label class="field-label">
              Send
              <button
                class="button button-primary"
                :disabled="!terminalSession || terminalSending || !terminalInput.trim()"
                @click="submitTerminalInput"
              >
                {{ terminalSending ? '发送中...' : '发送命令' }}
              </button>
            </label>

            <label class="field-label">
              Shortcuts
              <div class="button-row">
                <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('enter')">
                  Enter
                </button>
                <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('ctrlc')">
                  Ctrl+C
                </button>
              </div>
            </label>
          </div>
        </section>

        <section v-if="isPodResource && !isCreating" class="log-panel">
          <div class="section-head">
            <div>
              <h2 style="font-size: 15px">Pod Exec</h2>
              <p>当前先提供单次命令执行，适合快速排障和环境探针，后续再升级成交互式终端。</p>
            </div>
            <button
              class="button button-secondary"
              :disabled="executing || !canExecPod"
              @click="executePodCommand"
            >
              {{ executing ? '执行中...' : '执行命令' }}
            </button>
          </div>

          <div class="toolbar-grid logs-toolbar">
            <label class="field-label">
              Container
              <select v-model="selectedExecContainer" :disabled="!containerOptions.length || !canExecPod">
                <option value="">自动选择</option>
                <option v-for="container in containerOptions" :key="`exec:${container}`" :value="container">
                  {{ container }}
                </option>
              </select>
            </label>

            <label class="field-label">
              Timeout
              <input v-model.number="execTimeoutSeconds" type="number" min="3" max="60" :disabled="!canExecPod" />
            </label>
          </div>

          <label class="field-label" style="margin-bottom: 12px">
            Shell Command
            <textarea
              v-model="execCommand"
              placeholder="例如：id && uname -a"
              :disabled="!canExecPod"
            />
          </label>

          <div v-if="!canExecPod && !loadingPermissions" class="helper-text" style="margin-bottom: 12px">
            当前账号没有 `pods/exec` 权限，或当前集群未暴露 exec 子资源。
          </div>
          <div v-if="execError" class="error-text" style="margin-bottom: 12px">{{ execError }}</div>

          <div v-if="execResponse" class="pill-row" style="margin-bottom: 12px">
            <span class="pill">Exit: {{ execResponse.exit_code }}</span>
            <span class="pill">Duration: {{ execResponse.duration_ms }}ms</span>
            <span class="pill">Session: #{{ execResponse.session.id }}</span>
          </div>
          <pre
            v-if="execResponse"
            class="json-block log-block"
          >$ {{ execResponse.shell_command }}

{{ execResponse.stdout || '' }}{{ execResponse.stderr ? `\n[stderr]\n${execResponse.stderr}` : '' }}</pre>

          <div class="section-head" style="margin-top: 16px">
            <div>
              <h2 style="font-size: 15px">最近 Exec 历史</h2>
              <p>默认只展示当前账号在这个 Pod 上最近的执行记录，便于回看排障轨迹。</p>
            </div>
            <button
              class="button button-secondary"
              :disabled="loadingExecHistory"
              @click="loadExecHistory"
            >
              {{ loadingExecHistory ? '读取中...' : '刷新历史' }}
            </button>
          </div>

          <div v-if="execHistoryError" class="error-text" style="margin-bottom: 12px">{{ execHistoryError }}</div>
          <div v-else-if="loadingExecHistory" class="helper-text">正在同步最近的 Exec 会话...</div>
          <div v-else-if="execHistory.length" class="event-list">
            <div
              v-for="session in execHistory"
              :key="session.id"
              class="event-item"
            >
              <div class="button-row" style="justify-content: space-between">
                <div class="button-row">
                  <span class="status-badge" :class="sessionStatusClass(session.status)">
                    {{ session.status }}
                  </span>
                  <strong>#{{ session.id }}</strong>
                </div>
                <span class="muted">{{ formatDateTime(session.created_at) }}</span>
              </div>
              <div class="muted" style="margin-top: 8px">
                {{ session.container_name || 'auto-container' }} · exit {{ session.exit_code ?? '--' }} ·
                {{ session.command.join(' ') || '--' }}
              </div>
              <div v-if="session.output_excerpt" class="helper-text" style="margin-top: 8px">
                {{ session.output_excerpt }}
              </div>
            </div>
          </div>
          <div v-else class="helper-text">当前 Pod 还没有可展示的 Exec 历史。</div>
        </section>
      </article>
    </section>
  </div>
</template>
