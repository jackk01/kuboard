<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type {
  ClusterDiscoveryResponse,
  DiscoveryResource,
  PodLogsResponse,
  ResourceDetailResponse,
  ResourceListResponse,
  ResourcePermissionResponse,
  ResourceSchemaResponse,
  ResourceWatchResponse,
  StreamSessionSummary,
  TerminalOutputResponse,
  TerminalSessionResponse,
} from '../types'

const clusterStore = useClusterStore()
const router = useRouter()
type WatchEventItem = ResourceWatchResponse['events'][number] & { received_at: string }
type ResourceSortKey = 'name' | 'namespace' | 'status' | 'age'

const selectedClusterId = ref('')
const selectedGroupKey = ref('')
const selectedResourceName = ref('')
const selectedNamespace = ref('')
const resourceSearchKeyword = ref('')
const resourcePage = ref(1)
const resourcePageSize = ref(10)
const resourcePageSizeOptions = [10, 20, 50, 100] as const
const resourceSortKey = ref<ResourceSortKey | ''>('')
const resourceSortDirection = ref<'asc' | 'desc'>('asc')
const RESOURCE_LIST_FETCH_LIMIT = 200
const RESOURCE_LIST_MAX_PAGES = 50

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
const yamlDialogOpen = ref(false)
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
const deleteDialogVisible = ref(false)
const pendingDeleteName = ref('')
const watchActive = ref(false)
const watchLoading = ref(false)
const watchEvents = ref<WatchEventItem[]>([])
const watchError = ref('')
const watchCursor = ref('')
const watchSyncMessage = ref('')
const selectedTerminalContainer = ref('')
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

const commonResourcePresets = [
  {
    key: 'deployments',
    label: 'Deployment',
    labelZh: '部署',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'apps',
    version: 'v1',
    resource: 'deployments',
  },
  {
    key: 'statefulsets',
    label: 'StatefulSet',
    labelZh: '有状态应用',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'apps',
    version: 'v1',
    resource: 'statefulsets',
  },
  {
    key: 'daemonsets',
    label: 'DaemonSet',
    labelZh: '守护进程集',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'apps',
    version: 'v1',
    resource: 'daemonsets',
  },
  {
    key: 'pods',
    label: 'Pod',
    labelZh: 'Pod 实例',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'core',
    version: 'v1',
    resource: 'pods',
  },
  {
    key: 'jobs',
    label: 'Job',
    labelZh: '一次性任务',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'batch',
    version: 'v1',
    resource: 'jobs',
  },
  {
    key: 'cronjobs',
    label: 'CronJob',
    labelZh: '定时任务',
    category: 'workload',
    categoryZh: '工作负载',
    group: 'batch',
    version: 'v1',
    resource: 'cronjobs',
  },
  {
    key: 'services',
    label: 'Service',
    labelZh: '服务发现',
    category: 'network',
    categoryZh: '网络访问',
    group: 'core',
    version: 'v1',
    resource: 'services',
  },
  {
    key: 'ingresses',
    label: 'Ingress',
    labelZh: '入口路由',
    category: 'network',
    categoryZh: '网络访问',
    group: 'networking.k8s.io',
    version: 'v1',
    resource: 'ingresses',
  },
  {
    key: 'configmaps',
    label: 'ConfigMap',
    labelZh: '配置',
    category: 'config',
    categoryZh: '配置与密钥',
    group: 'core',
    version: 'v1',
    resource: 'configmaps',
  },
  {
    key: 'secrets',
    label: 'Secret',
    labelZh: '密钥',
    category: 'config',
    categoryZh: '配置与密钥',
    group: 'core',
    version: 'v1',
    resource: 'secrets',
  },
] as const

const commonResourceItems = computed(() =>
  commonResourcePresets.map((preset) => {
    const groupKey = `${preset.group}::${preset.version}`
    const group = discovery.value?.groups.find(
      (item) => item.group === preset.group && item.version === preset.version,
    )
    const matchedResource = group?.resources.find((item) => item.name === preset.resource)
    return {
      ...preset,
      groupKey,
      available: Boolean(matchedResource),
      namespaced: Boolean(matchedResource?.namespaced),
      active: selectedGroupKey.value === groupKey && selectedResourceName.value === preset.resource,
    }
  }),
)

const availableCommonResources = computed(() =>
  commonResourceItems.value.filter((item) => item.available),
)

const selectedQuickCategory = ref<'workload' | 'network' | 'config'>('workload')

const groupedCommonResources = computed(() => {
  const order = ['workload', 'network', 'config'] as const
  return order.reduce<Array<{
    category: (typeof order)[number]
    title: string
    items: typeof availableCommonResources.value
  }>>((acc, category) => {
      const items = availableCommonResources.value.filter((item) => item.category === category)
      if (!items.length) return acc
      acc.push({
        category,
        title: items[0].categoryZh,
        items,
      })
      return acc
    }, [])
})

const quickCategoryTabs = computed(() =>
  groupedCommonResources.value.map((group) => ({
    category: group.category,
    title: group.title,
    count: group.items.length,
  })),
)

const quickCategoryResources = computed(
  () => groupedCommonResources.value.find((group) => group.category === selectedQuickCategory.value)?.items ?? [],
)

const unavailableCommonResources = computed(() =>
  commonResourceItems.value.filter((item) => !item.available).map((item) => `${item.labelZh}(${item.label})`),
)

const explorerSummary = computed(() => ({
  groups: discovery.value?.groups.length ?? 0,
  resources: resources.value.length,
  namespaces: namespaceOptions.value.length,
  listed: resourceList.value?.metadata.count ?? resourceList.value?.items.length ?? 0,
}))

const normalizedResourceSearchKeyword = computed(() =>
  normalizeSearchText(resourceSearchKeyword.value),
)
const resourceSearchTerms = computed(() => tokenizeSearchText(normalizedResourceSearchKeyword.value))

const filteredResourceItems = computed(() => {
  const items = resourceList.value?.items ?? []
  const searchKeyword = normalizedResourceSearchKeyword.value
  let matchedItems: Array<Record<string, any>> = []

  if (!searchKeyword) {
    matchedItems = [...items]
  } else {
    const searchTerms = resourceSearchTerms.value
    const scoredItems = items
      .map((item) => {
        const name = normalizeSearchText(resolveSearchableResourceName(item))
        if (!name) {
          return null
        }

        const nameTerms = tokenizeSearchText(name)
        let score = 0

        if (name === searchKeyword) {
          score = 400
        } else if (name.startsWith(searchKeyword)) {
          score = 300
        } else if (nameTerms.some((term) => term.startsWith(searchKeyword))) {
          score = 240
        } else if (searchTerms.every((term) => nameTerms.some((nameTerm) => nameTerm.startsWith(term)))) {
          score = 180
        } else if (searchTerms.every((term) => name.includes(term))) {
          score = 120
        }

        if (!score) {
          return null
        }

        return {
          item,
          name,
          score,
        }
      })
      .filter((entry): entry is { item: Record<string, any>; name: string; score: number } => Boolean(entry))

    scoredItems.sort((left, right) => right.score - left.score || left.name.localeCompare(right.name))
    matchedItems = scoredItems.map((entry) => entry.item)
  }

  return sortResourceItems(matchedItems)
})

const resourceTotalPages = computed(() => Math.max(1, Math.ceil(filteredResourceItems.value.length / resourcePageSize.value)))

const paginatedResourceItems = computed(() => {
  const start = (resourcePage.value - 1) * resourcePageSize.value
  return filteredResourceItems.value.slice(start, start + resourcePageSize.value)
})

const resourcePageStart = computed(() =>
  filteredResourceItems.value.length ? (resourcePage.value - 1) * resourcePageSize.value + 1 : 0,
)

const resourcePageEnd = computed(() =>
  filteredResourceItems.value.length
    ? Math.min(resourcePage.value * resourcePageSize.value, filteredResourceItems.value.length)
    : 0,
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
const schemaSampleHint = computed(() => {
  if (!resourceSchema.value || resourceSchema.value.source !== 'inferred' || !resourceSchema.value.metadata.empty_sample) {
    return ''
  }
  const namespace = String(resourceSchema.value.metadata.sample_namespace || selectedNamespace.value || '--')
  return `当前名称空间 ${namespace} 下暂无该资源实例，Schema 预览已回退为基础结构。`
})
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
const canOpenTerminal = computed(
  () =>
    Boolean(
      isPodResource.value &&
        resourcePermissions.value?.subresources.exec?.allowed,
    ),
)
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
const isPodListResource = computed(
  () => selectedGroup.value?.group === 'core' && selectedResourceName.value === 'pods',
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
  yamlDialogOpen.value = false
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

function schemaSourceLabel(source?: string) {
  if (source === 'crd') return 'CRD Schema'
  if (source === 'openapi-v3') return 'OpenAPI v3'
  if (source === 'inferred') return '样本推断'
  return '--'
}

function activateCommonResource(item: {
  available: boolean
  groupKey: string
  resource: string
  namespaced: boolean
}) {
  if (!item.available) {
    return
  }
  selectedGroupKey.value = item.groupKey
  selectedResourceName.value = item.resource
  if (!item.namespaced) {
    selectedNamespace.value = ''
  } else if (!selectedNamespace.value) {
    selectedNamespace.value = discovery.value?.context.default_namespace || 'default'
  }
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

function resolveResourceName(item: Record<string, any> | null) {
  if (!item || typeof item !== 'object') {
    return ''
  }

  return String(item.metadata?.name || item.name || item.metadata?.generateName || '')
}

function resolveSearchableResourceName(item: Record<string, any> | null) {
  if (!item || typeof item !== 'object') {
    return ''
  }
  return String(item.metadata?.name || item.name || '')
}

function normalizeSearchText(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, ' ')
}

function tokenizeSearchText(value: string) {
  const normalizedValue = normalizeSearchText(value)
  if (!normalizedValue) {
    return [] as string[]
  }
  return normalizedValue.split(/[\s\-._/]+/).filter(Boolean)
}

function resolveCreationTimestamp(item: Record<string, any> | null) {
  const timestamp = item?.metadata?.creationTimestamp
  if (!timestamp) {
    return 0
  }
  const timeValue = new Date(String(timestamp)).getTime()
  return Number.isNaN(timeValue) ? 0 : timeValue
}

function compareResourceText(left: string, right: string) {
  return left.localeCompare(right, 'zh-CN', { numeric: true, sensitivity: 'base' })
}

function getResourceSortText(item: Record<string, any>, key: Exclude<ResourceSortKey, 'age'>) {
  if (key === 'name') {
    return resolveResourceName(item)
  }
  if (key === 'namespace') {
    return String(item.metadata?.namespace || '')
  }
  return summarizeStatus(item)
}

function sortResourceItems(items: Array<Record<string, any>>) {
  if (!resourceSortKey.value || items.length < 2) {
    return items
  }

  const key = resourceSortKey.value
  const direction = resourceSortDirection.value === 'asc' ? 1 : -1
  return [...items].sort((left, right) => {
    let result = 0

    if (key === 'age') {
      result = resolveCreationTimestamp(left) - resolveCreationTimestamp(right)
    } else {
      result = compareResourceText(
        getResourceSortText(left, key).toLowerCase(),
        getResourceSortText(right, key).toLowerCase(),
      )
    }

    if (!result) {
      result = compareResourceText(
        resolveResourceName(left).toLowerCase(),
        resolveResourceName(right).toLowerCase(),
      )
    }

    return result * direction
  })
}

function toggleResourceSort(key: ResourceSortKey) {
  if (resourceSortKey.value !== key) {
    resourceSortKey.value = key
    resourceSortDirection.value = key === 'age' ? 'desc' : 'asc'
    return
  }

  if (resourceSortDirection.value === 'asc') {
    resourceSortDirection.value = 'desc'
    return
  }

  resourceSortKey.value = ''
  resourceSortDirection.value = 'asc'
}

function resourceSortIndicator(key: ResourceSortKey) {
  if (resourceSortKey.value !== key) {
    return '↕'
  }
  return resourceSortDirection.value === 'asc' ? '↑' : '↓'
}

function dedupeResourceItems(items: Array<Record<string, any>>) {
  const keys = new Set<string>()
  const dedupedItems: Array<Record<string, any>> = []

  for (const item of items) {
    const key = resourceItemKey(item)
    if (keys.has(key)) {
      continue
    }
    keys.add(key)
    dedupedItems.push(item)
  }

  return dedupedItems
}

async function fetchResourceListAllPages() {
  if (!selectedClusterId.value || !selectedGroup.value || !selectedResourceName.value) {
    return null
  }

  let continueToken = ''
  let firstPagePayload: ResourceListResponse | null = null
  let latestResourceVersion = ''
  const visitedContinueTokens = new Set<string>()
  const mergedItems: Array<Record<string, any>> = []

  for (let index = 0; index < RESOURCE_LIST_MAX_PAGES; index += 1) {
    const query = new URLSearchParams({
      limit: String(RESOURCE_LIST_FETCH_LIMIT),
    })

    if (selectedResource.value?.namespaced && selectedNamespace.value) {
      query.set('namespace', selectedNamespace.value)
    }
    if (continueToken) {
      query.set('continue', continueToken)
    }

    const payload = await apiRequest<ResourceListResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/resources/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}?${query.toString()}`,
    )
    if (!firstPagePayload) {
      firstPagePayload = payload
    }
    mergedItems.push(...payload.items)
    latestResourceVersion = payload.metadata.resource_version || latestResourceVersion

    const nextContinueToken = payload.metadata.continue || ''
    if (!nextContinueToken) {
      continueToken = ''
      break
    }
    if (visitedContinueTokens.has(nextContinueToken)) {
      continueToken = nextContinueToken
      break
    }

    visitedContinueTokens.add(nextContinueToken)
    continueToken = nextContinueToken
  }

  if (!firstPagePayload) {
    return null
  }

  const dedupedItems = dedupeResourceItems(mergedItems)
  return {
    ...firstPagePayload,
    items: dedupedItems,
    metadata: {
      count: dedupedItems.length,
      continue: continueToken,
      resource_version: latestResourceVersion || firstPagePayload.metadata.resource_version,
    },
  }
}

function updateContainerSelection(nextContainers: string[]) {
  if (!nextContainers.length) {
    selectedLogContainer.value = ''
    selectedTerminalContainer.value = ''
    return
  }
  if (!selectedLogContainer.value || !nextContainers.includes(selectedLogContainer.value)) {
    selectedLogContainer.value = nextContainers[0] ?? ''
  }
  if (!selectedTerminalContainer.value || !nextContainers.includes(selectedTerminalContainer.value)) {
    selectedTerminalContainer.value = nextContainers[0] ?? ''
  }
}

function syncResourcePageToSelectedItem() {
  if (!selectedItem.value) {
    return
  }

  const selectedKey = resourceItemKey(selectedItem.value)
  const index = filteredResourceItems.value.findIndex((item) => resourceItemKey(item) === selectedKey)
  if (index < 0) {
    return
  }

  resourcePage.value = Math.floor(index / resourcePageSize.value) + 1
}

function goToResourcePage(page: number) {
  resourcePage.value = Math.min(Math.max(page, 1), resourceTotalPages.value)
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
  yamlDialogOpen.value = false
  detailError.value = ''
  permissionError.value = ''
  applyError.value = ''
  applyMessage.value = ''
  resetLogState()
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

function normalizeReplicaCount(value: unknown, fallback = 0) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed < 0) {
    return fallback
  }
  return Math.floor(parsed)
}

function summarizeStatus(item: Record<string, any>) {
  const isDeploymentResource =
    selectedResourceName.value === 'deployments' &&
    (selectedGroup.value?.group === 'apps' || String(item.apiVersion || '').startsWith('apps/'))

  if (isDeploymentResource) {
    const status = item.status ?? {}
    const spec = item.spec ?? {}
    const readyReplicas = normalizeReplicaCount(status.readyReplicas, 0)
    const desiredReplicas = normalizeReplicaCount(
      spec.replicas,
      normalizeReplicaCount(status.replicas, 1),
    )
    return `${readyReplicas}/${desiredReplicas}`
  }

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

async function loadDiscovery(options: { preserveSelection?: boolean; resetState?: boolean; preferredNamespace?: string } = {}) {
  if (!selectedClusterId.value) {
    return
  }

  loadingDiscovery.value = true
  discoveryError.value = ''
  const resetState = options.resetState !== false

  if (resetState) {
    stopWatching()
    clearDetailRefreshTimer()
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
    resetTerminalState()
    resetSchemaState()
    resetFormEditorState()
    resetCreateState()
  }

  try {
    const payload = await apiRequest<ClusterDiscoveryResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/discovery`,
    )
    discovery.value = payload
    await clusterStore.fetchClusters()
    const preferredGroup =
      payload.groups.find((group) => group.group === 'core' && group.version === 'v1') ?? payload.groups[0]
    const preferredGroupKey = preferredGroup ? `${preferredGroup.group}::${preferredGroup.version}` : ''
    const currentGroup = payload.groups.find(
      (group) => `${group.group}::${group.version}` === selectedGroupKey.value,
    )

    if (options.preserveSelection && currentGroup) {
      selectedGroupKey.value = `${currentGroup.group}::${currentGroup.version}`
      if (!currentGroup.resources.some((resource) => resource.name === selectedResourceName.value)) {
        selectedResourceName.value =
          currentGroup.resources.find((resource) => resource.name === 'pods')?.name ??
          currentGroup.resources[0]?.name ??
          ''
      }
    } else {
      selectedGroupKey.value = preferredGroupKey
      selectedResourceName.value =
        preferredGroup?.resources.find((resource) => resource.name === 'pods')?.name ??
        preferredGroup?.resources[0]?.name ??
        ''
    }

    if (selectedResource.value?.namespaced) {
      const nextNamespace =
        options.preferredNamespace ||
        selectedNamespace.value ||
        payload.context.default_namespace ||
        payload.namespaces[0]?.name ||
        'default'
      selectedNamespace.value = payload.namespaces.some((namespace) => namespace.name === nextNamespace)
        ? nextNamespace
        : payload.context.default_namespace || payload.namespaces[0]?.name || 'default'
    } else {
      selectedNamespace.value = ''
    }
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
    const query = new URLSearchParams()
    if (selectedResource.value?.namespaced && selectedNamespace.value) {
      query.set('namespace', selectedNamespace.value)
    }
    resourceSchema.value = await apiRequest<ResourceSchemaResponse>(
      `/api/v1/clusters/${selectedClusterId.value}/schemas/${selectedGroup.value.group}/${selectedGroup.value.version}/${selectedResourceName.value}${query.toString() ? `?${query.toString()}` : ''}`,
    )
  } catch (error) {
    resourceSchema.value = null
    if (error instanceof ApiError) {
      schemaError.value = error.status >= 500 ? '当前资源暂无可用 Schema，已等待后端返回基础结构。' : error.message
    } else {
      schemaError.value = '资源 Schema 读取失败。'
    }
  } finally {
    loadingSchema.value = false
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
    if (!(payload.resource.group === 'core' && payload.resource.name === 'pods') && !options.preserveStreams) {
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
  resetTerminalState()
  resetSchemaState()
  resetFormEditorState()
  resetCreateState()

  try {
    resourceList.value = await fetchResourceListAllPages()
    if (!resourceList.value) {
      return
    }
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
  yamlDialogOpen.value = mode === 'yaml'
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
  yamlDialogOpen.value = mode === 'yaml'
  detailError.value = ''
  applyError.value = ''
  applyMessage.value = ''
  watchSyncMessage.value = ''
  resetLogState()
  resetTerminalState()
}

async function cancelEditing() {
  if (isCreating.value) {
    const originItem = createOriginItem.value ? cloneObject(createOriginItem.value) : null
    resetCreateState()
    isEditing.value = false
    editorMode.value = 'yaml'
    yamlDialogOpen.value = false
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
  yamlDialogOpen.value = false
  editorText.value = selectedDetail.value?.yaml || ''
  hydrateFormDraft(selectedDetail.value?.object ?? null)
  applyError.value = ''
  applyMessage.value = ''
}

function openYamlDialog() {
  if (!selectedDetail.value) {
    return
  }
  if (!isEditing.value || editorMode.value !== 'yaml') {
    startEditing('yaml')
    return
  }
  yamlDialogOpen.value = true
}

function closeYamlDialog() {
  yamlDialogOpen.value = false
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !yamlDialogOpen.value) {
    return
  }
  event.preventDefault()
  closeYamlDialog()
}

function openPodLogsInNewTab() {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value || !canViewPodLogs.value) {
    return
  }

  const target = router.resolve({
    name: 'pod-logs',
    query: {
      cluster: selectedClusterId.value,
      pod: selectedDetail.value.metadata.name,
      namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
      container: selectedLogContainer.value || undefined,
      tail_lines: String(logTailLines.value),
      follow: 'true',
    },
  })

  window.open(target.href, '_blank', 'noopener,noreferrer')
}

function openPodTerminalInNewTab(shell: '/bin/sh' | '/bin/bash') {
  if (!selectedClusterId.value || !selectedDetail.value || !isPodResource.value || !canOpenTerminal.value) {
    return
  }

  const target = router.resolve({
    name: 'pod-terminal',
    query: {
      cluster: selectedClusterId.value,
      pod: selectedDetail.value.metadata.name,
      namespace: selectedDetail.value.metadata.namespace || selectedNamespaceOrDefault.value,
      container: selectedTerminalContainer.value || undefined,
      shell,
      rows: String(terminalRows.value),
      cols: String(terminalCols.value),
    },
  })

  window.open(target.href, '_blank', 'noopener,noreferrer')
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
    yamlDialogOpen.value = dryRun || isCreating.value
    applyMessage.value = dryRun ? 'Dry-run 创建校验通过，后端已返回预览对象。' : 'Create 成功，资源已创建。'
    if (!dryRun) {
      isEditing.value = false
      yamlDialogOpen.value = false
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
    yamlDialogOpen.value = dryRun
    applyMessage.value = dryRun ? 'Dry-run 校验通过，后端已接受并返回预览对象。' : 'Apply 成功，资源已更新。'
    if (!dryRun) {
      isEditing.value = false
      yamlDialogOpen.value = false
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

  pendingDeleteName.value = targetName
  deleteDialogVisible.value = true
}

function cancelDeleteResource() {
  deleteDialogVisible.value = false
  pendingDeleteName.value = ''
}

async function confirmDeleteResource() {
  if (
    !selectedClusterId.value ||
    !selectedGroup.value ||
    !selectedResourceName.value ||
    !selectedItem.value ||
    !canDeleteResource.value
  ) {
    cancelDeleteResource()
    return
  }

  const targetName = pendingDeleteName.value || selectedItem.value.metadata?.name || ''
  if (!targetName) {
    cancelDeleteResource()
    return
  }

  deleteDialogVisible.value = false

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
    pendingDeleteName.value = ''
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
          container: selectedTerminalContainer.value || undefined,
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
  document.addEventListener('keydown', handleGlobalKeydown)
  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }
  selectedClusterId.value = clusterStore.items[0]?.id ?? ''
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
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
  if (!resources.value.some((resource) => resource.name === selectedResourceName.value)) {
    selectedResourceName.value = resources.value[0]?.name ?? ''
  }
})

watch(resourceSearchKeyword, () => {
  resourcePage.value = 1
})

watch(resourcePageSize, () => {
  resourcePage.value = 1
})

watch([resourceSortKey, resourceSortDirection], () => {
  resourcePage.value = 1
})

watch(filteredResourceItems, () => {
  if (resourcePage.value > resourceTotalPages.value) {
    resourcePage.value = resourceTotalPages.value
  }
})

watch(
  () => resourceItemKey(selectedItem.value),
  () => {
    syncResourcePageToSelectedItem()
  },
)

watch(
  () => quickCategoryTabs.value,
  (tabs) => {
    if (!tabs.length) {
      return
    }
    if (!tabs.some((item) => item.category === selectedQuickCategory.value)) {
      selectedQuickCategory.value = tabs[0].category
    }
  },
  { immediate: true },
)

watch(
  [selectedGroupKey, selectedResourceName, selectedNamespace],
  async ([groupKey, resourceName, namespace], [, , previousNamespace]) => {
    if (!groupKey || !resourceName) {
      return
    }
    if (namespace !== previousNamespace && selectedClusterId.value) {
      await loadDiscovery({
        preserveSelection: true,
        resetState: false,
        preferredNamespace: namespace,
      })
    }
    await loadResources()
  },
)
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel explorer-hero-panel">
      <div class="section-head">
        <div>
          <div class="eyebrow" style="color: var(--kb-primary-deep)">Explorer</div>
          <h2 class="page-title">资源浏览</h2>
          <p class="page-description">
            这里会在切换集群时自动同步 Discovery 和通用资源列表接口。导入可访问的 kubeconfig 后，可以直接浏览集群内的常见资源。
          </p>
        </div>
        <span class="helper-text">{{ loadingDiscovery ? '正在自动同步 Discovery...' : 'Discovery 自动同步已开启' }}</span>
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
          名称空间
          <select v-model="selectedNamespace" :disabled="!selectedResource?.namespaced">
            <option value="">cluster-scoped</option>
            <option v-for="namespace in namespaceOptions" :key="namespace.name" :value="namespace.name">
              {{ namespace.name }}
            </option>
          </select>
        </label>
      </div>

      <div class="explorer-quick-surface">
        <div class="section-head" style="margin-bottom: 10px">
          <div>
            <h2>常用资源</h2>
            <p>点击资源名称即可查看。</p>
          </div>
        </div>
        <div class="explorer-quick-tabs">
          <button
            v-for="tab in quickCategoryTabs"
            :key="tab.category"
            class="button explorer-quick-tab"
            :class="selectedQuickCategory === tab.category ? 'explorer-quick-tab-active' : 'button-secondary'"
            @click="selectedQuickCategory = tab.category"
          >
            {{ tab.title }} ({{ tab.count }})
          </button>
        </div>
        <div class="explorer-quick-grid" style="margin-top: 10px">
          <button
            v-for="item in quickCategoryResources"
            :key="item.key"
            class="button explorer-quick-btn"
            :class="item.active ? 'explorer-quick-btn-active' : 'button-secondary'"
            @click="activateCommonResource(item)"
          >
            <span class="explorer-quick-name">{{ item.labelZh }}</span>
            <span class="explorer-quick-sub">{{ item.label }}</span>
          </button>
          <div v-if="!quickCategoryResources.length" class="helper-text">
            当前分组没有可用资源，请切换其他分组。
          </div>
        </div>
        <div v-if="unavailableCommonResources.length" class="helper-text" style="margin-top: 8px">
          当前集群未发现：{{ unavailableCommonResources.join('、') }}
        </div>
      </div>

      <div class="cluster-summary-grid explorer-summary-grid" style="margin-top: 12px">
        <article class="cluster-summary-card">
          <span>名称空间</span>
          <strong class="is-pending">{{ explorerSummary.namespaces }}</strong>
        </article>
      </div>

      <div v-if="discoveryError" class="error-text" style="margin-top: 14px">{{ discoveryError }}</div>
      <div v-else-if="discovery" class="button-row" style="margin-top: 16px">
        <StatusBadge :value="clusterStore.items.find((cluster) => cluster.id === selectedClusterId)?.status || 'ready'" />
        <span class="muted">
          Kubernetes {{ discovery.version.gitVersion || '--' }} · 默认命名空间 {{ discovery.context.default_namespace }}
        </span>
      </div>
    </section>

    <section class="split-detail explorer-split" :class="{ 'explorer-split-pods-equal': isPodListResource }">
      <article class="surface-card explorer-list-panel">
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
          <div v-if="resourceList" class="explorer-list-head-actions">
            <label class="field-label explorer-search-field">
              <input
                v-model="resourceSearchKeyword"
                class="explorer-search-input"
                type="text"
                placeholder="按 Name 搜索（优先精确/前缀匹配）"
              />
            </label>
          </div>
        </div>

        <div v-if="resourceList" class="helper-text explorer-list-summary">
          {{ resourceList.metadata.continue ? `已加载 ${resourceList.metadata.count} 条资源（仍有更多）` : `共 ${resourceList.metadata.count} 条资源` }}，匹配 {{ filteredResourceItems.length }} 条，
          当前显示第 {{ resourcePageStart || 0 }} - {{ resourcePageEnd || 0 }} 条。
        </div>

        <div v-if="loadingResources" class="helper-text">正在读取资源...</div>
        <div v-else-if="resourceError" class="error-text">{{ resourceError }}</div>
        <table v-else-if="paginatedResourceItems.length" class="table">
          <thead>
            <tr>
              <th>
                <button type="button" class="explorer-sort-button" @click="toggleResourceSort('name')">
                  Name
                  <span class="explorer-sort-indicator">{{ resourceSortIndicator('name') }}</span>
                </button>
              </th>
              <th>
                <button type="button" class="explorer-sort-button" @click="toggleResourceSort('namespace')">
                  名称空间
                  <span class="explorer-sort-indicator">{{ resourceSortIndicator('namespace') }}</span>
                </button>
              </th>
              <th>
                <button type="button" class="explorer-sort-button" @click="toggleResourceSort('status')">
                  Status
                  <span class="explorer-sort-indicator">{{ resourceSortIndicator('status') }}</span>
                </button>
              </th>
              <th>
                <button type="button" class="explorer-sort-button" @click="toggleResourceSort('age')">
                  Age
                  <span class="explorer-sort-indicator">{{ resourceSortIndicator('age') }}</span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in paginatedResourceItems"
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
                <strong>{{ resolveResourceName(item) || '--' }}</strong>
              </td>
              <td>{{ item.metadata?.namespace || '--' }}</td>
              <td>{{ summarizeStatus(item) }}</td>
              <td>{{ formatAge(item.metadata?.creationTimestamp) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="filteredResourceItems.length" class="explorer-pagination">
          <div class="explorer-pagination-pill">
            第 {{ resourcePage }} / {{ resourceTotalPages }} 页
          </div>
          <div class="explorer-pagination-controls">
            <label class="field-label explorer-page-size-field">
              <select v-model.number="resourcePageSize">
                <option v-for="size in resourcePageSizeOptions" :key="size" :value="size">
                  {{ size }}
                </option>
              </select>
            </label>
          </div>
          <div class="button-row explorer-pagination-actions">
            <button class="button button-secondary explorer-pagination-button" :disabled="resourcePage <= 1" @click="goToResourcePage(1)">
              首
            </button>
            <button
              class="button button-secondary explorer-pagination-button"
              :disabled="resourcePage <= 1"
              @click="goToResourcePage(resourcePage - 1)"
            >
              上一页
            </button>
            <button
              class="button button-secondary explorer-pagination-button"
              :disabled="resourcePage >= resourceTotalPages"
              @click="goToResourcePage(resourcePage + 1)"
            >
              下一页
            </button>
            <button
              class="button button-secondary explorer-pagination-button"
              :disabled="resourcePage >= resourceTotalPages"
              @click="goToResourcePage(resourceTotalPages)"
            >
              末
            </button>
          </div>
        </div>
        <div v-else class="empty-state">
          {{
            resourceList?.items.length
              ? '没有匹配到符合条件的资源，请调整 Name 搜索关键字后重试。'
              : selectedResource
                ? '当前查询没有返回资源，可能是资源为空，或者当前账号没有读取权限。'
                : '导入真实集群并完成 Discovery 后，这里会显示实际资源。'
          }}
        </div>
      </article>

      <article class="surface-card explorer-detail-panel">
        <div class="section-head">
          <div>
            <h2>详情与 YAML</h2>
            <p>现在支持资源新建与 YAML/JSON 编辑，会先探测真实权限，再决定是否允许修改或创建。</p>
          </div>
          <div class="explorer-detail-actions">
            <button
              class="button explorer-detail-action button-primary"
              :disabled="!selectedResource || loadingPermissions || (!canCreateResource && !isCreating)"
              @click="isCreating ? cancelEditing() : startCreating('yaml')"
            >
              {{ isCreating ? '取消新建' : '新建' }}
            </button>
            <button
              class="button explorer-detail-action button-secondary"
              :disabled="!selectedDetail || loadingPermissions || (isCreating ? !canCreateResource : !canEditYaml)"
              @click="openYamlDialog"
            >
              查看
            </button>
            <button
              class="button explorer-detail-action button-danger"
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

        <div v-if="isPodResource && !isCreating" class="pod-tools-grid">
          <section class="log-panel pod-tool-card">
            <div class="pod-tool-header">
              <div class="pod-tool-summary">
                <h2 style="font-size: 15px">Pod 日志</h2>
                <p>选择好容器和输出行数后，会在新的浏览器页签中打开日志视图，并默认开启追踪模式。</p>
              </div>
              <div class="pod-tool-actions">
                <button class="button button-primary" :disabled="!canViewPodLogs" @click="openPodLogsInNewTab">
                  查看日志
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

            <div v-if="!canViewPodLogs && !loadingPermissions" class="helper-text pod-tool-helper">
              当前账号没有 `pods/log` 读取权限，日志面板已保持只读不可用。
            </div>
            <div v-else class="helper-text pod-tool-helper">
              打开的日志页会默认追踪最新输出，你也可以在新页签中暂停追踪并调整输出行数后再刷新。
            </div>
          </section>

          <section class="log-panel pod-tool-card">
            <div class="pod-tool-header">
              <div class="pod-tool-summary">
                <h2 style="font-size: 15px">网页终端</h2>
                <p>选择容器后在新的浏览器页签中打开终端，可直接进入 `/bin/sh` 或 `/bin/bash`。</p>
              </div>
              <div class="button-row pod-tool-actions">
                <button
                  class="button button-primary"
                  :disabled="!canOpenTerminal"
                  @click="openPodTerminalInNewTab('/bin/sh')"
                >
                  打开 sh 终端
                </button>
                <button
                  class="button button-secondary"
                  :disabled="!canOpenTerminal"
                  @click="openPodTerminalInNewTab('/bin/bash')"
                >
                  打开 bash 终端
                </button>
              </div>
            </div>

            <div class="toolbar-grid terminal-toolbar">
              <label class="field-label">
                Container
                <select v-model="selectedTerminalContainer" :disabled="!containerOptions.length || !canOpenTerminal">
                  <option value="">自动选择</option>
                  <option v-for="container in containerOptions" :key="`terminal:${container}`" :value="container">
                    {{ container }}
                  </option>
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
            </div>

            <div v-if="!canOpenTerminal && !loadingPermissions" class="helper-text pod-tool-helper">
              当前账号没有 `pods/exec` 权限，终端功能不可用。
            </div>
            <div v-else class="helper-text pod-tool-helper">
              新页签终端会直接连接到目标容器，并支持发送命令、回车、Ctrl+C 和终端尺寸调整。
            </div>
          </section>
        </div>
      </article>
    </section>

    <div v-if="yamlDialogOpen && selectedDetail" class="yaml-dialog-backdrop" @click.self="closeYamlDialog">
      <section class="yaml-dialog">
        <div class="section-head" style="margin-bottom: 12px">
          <div>
            <h2>YAML 编辑器</h2>
            <p>
              {{
                isCreating
                  ? '当前是新建草稿，可以直接编辑 YAML 或 JSON 后执行 Create。'
                  : canEditYaml
                    ? '这里支持查看并编辑当前资源的 YAML 内容。'
                    : '当前资源仅支持只读查看 YAML。'
              }}
            </p>
          </div>
          <div class="button-row">
            <button
              class="button button-secondary"
              :disabled="applying || deleting"
              @click="isCreating ? cancelEditing() : closeYamlDialog()"
            >
              {{ isCreating ? '取消草稿' : '关闭' }}
            </button>
          </div>
        </div>

        <div v-if="applyError" class="error-text" style="margin-bottom: 12px">{{ applyError }}</div>
        <div v-if="applyMessage" class="helper-text" style="margin-bottom: 12px">{{ applyMessage }}</div>

        <textarea
          v-model="editorText"
          class="editor-surface"
          spellcheck="false"
          :readonly="!isCreating && !canEditYaml"
        />

        <div class="button-row" style="margin-top: 14px; justify-content: flex-end">
          <button
            class="button button-secondary"
            :disabled="!selectedDetail || applying || (!isCreating && !canEditYaml)"
            @click="isCreating ? submitCreate(true) : submitApply(true)"
          >
            {{ applying ? '处理中...' : isCreating ? 'Dry-run Create' : 'Dry-run' }}
          </button>
          <button
            class="button button-primary"
            :disabled="!selectedDetail || applying || (!isCreating && !canEditYaml)"
            @click="isCreating ? submitCreate(false) : submitApply(false)"
          >
            {{ applying ? (isCreating ? '创建中...' : '提交中...') : isCreating ? 'Create' : 'Apply' }}
          </button>
        </div>
      </section>
    </div>

    <ConfirmDialog
      :visible="deleteDialogVisible"
      title="删除资源"
      :message="pendingDeleteName ? `确认删除资源 ${pendingDeleteName} 吗？该操作不可撤销。` : ''"
      confirm-text="删除"
      cancel-text="取消"
      :danger="true"
      @confirm="confirmDeleteResource"
      @cancel="cancelDeleteResource"
    />
  </div>
</template>
