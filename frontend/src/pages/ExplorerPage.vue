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
  TerminalSessionResponse,
} from '../types'

const clusterStore = useClusterStore()
const router = useRouter()
type WatchEventItem = ResourceWatchResponse['events'][number] & { received_at: string }
type ResourceSortKey = 'name' | 'namespace' | 'status' | 'age'

const EXPLORER_SELECTION_STORAGE_KEY = 'kuboard.explorer.selection'

interface ExplorerSelectionState {
  clusterId: string
  namespacesByCluster: Record<string, string>
}

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
const clusterMenuOpen = ref(false)
const clusterMenuRef = ref<HTMLElement | null>(null)
const namespaceMenuOpen = ref(false)
const namespaceMenuRef = ref<HTMLElement | null>(null)
const selectedTerminalContainer = ref('')
const terminalContainerMenuOpen = ref(false)
const terminalContainerMenuRef = ref<HTMLElement | null>(null)
const terminalSession = ref<TerminalSessionResponse | null>(null)
const terminalOutput = ref('')
const terminalError = ref('')
const terminalConnecting = ref(false)
const terminalSending = ref(false)
const terminalCursor = ref(0)
const terminalInput = ref('')
const terminalRows = ref(32)
const terminalCols = ref(120)
const logsResponse = ref<PodLogsResponse | null>(null)
const logsError = ref('')
const loadingLogs = ref(false)
const logsFollowing = ref(false)
const logFollowCursor = ref('')
const logFollowSession = ref<StreamSessionSummary | null>(null)
const logContainerMenuOpen = ref(false)
const logContainerMenuRef = ref<HTMLElement | null>(null)
const selectedLogContainer = ref('')
const logTailLines = ref(200)
let watchLoopToken = 0
let watchTimer: number | null = null
let detailRefreshTimer: number | null = null
let logFollowLoopToken = 0
let logFollowTimer: number | null = null
let terminalLoopToken = 0
let terminalPollTimer: number | null = null

function createEmptyExplorerSelectionState(): ExplorerSelectionState {
  return {
    clusterId: '',
    namespacesByCluster: {},
  }
}

function readExplorerSelectionState(): ExplorerSelectionState {
  if (typeof window === 'undefined') {
    return createEmptyExplorerSelectionState()
  }

  const storedValue = window.localStorage.getItem(EXPLORER_SELECTION_STORAGE_KEY)
  if (!storedValue) {
    return createEmptyExplorerSelectionState()
  }

  try {
    const parsed = JSON.parse(storedValue) as Partial<ExplorerSelectionState> | null
    const namespacesByCluster = Object.fromEntries(
      Object.entries(parsed?.namespacesByCluster ?? {}).filter(
        ([clusterId, namespace]) => Boolean(clusterId) && typeof namespace === 'string' && Boolean(namespace),
      ),
    )
    return {
      clusterId: typeof parsed?.clusterId === 'string' ? parsed.clusterId : '',
      namespacesByCluster,
    }
  } catch {
    return createEmptyExplorerSelectionState()
  }
}

function writeExplorerSelectionState(nextState: ExplorerSelectionState) {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(EXPLORER_SELECTION_STORAGE_KEY, JSON.stringify(nextState))
}

function storeSelectedCluster(clusterId: string) {
  if (!clusterId) {
    return
  }

  const nextState = readExplorerSelectionState()
  nextState.clusterId = clusterId
  writeExplorerSelectionState(nextState)
}

function storeSelectedNamespace(clusterId: string, namespace: string) {
  if (!clusterId || !namespace) {
    return
  }

  const nextState = readExplorerSelectionState()
  nextState.clusterId = clusterId
  nextState.namespacesByCluster = {
    ...nextState.namespacesByCluster,
    [clusterId]: namespace,
  }
  writeExplorerSelectionState(nextState)
}

function resolveStoredNamespace(clusterId: string) {
  if (!clusterId) {
    return ''
  }

  return readExplorerSelectionState().namespacesByCluster[clusterId] || ''
}

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
const selectedClusterLabel = computed(
  () => clusterStore.items.find((cluster) => cluster.id === selectedClusterId.value)?.name || '请选择集群',
)
const selectedNamespaceLabel = computed(() => selectedNamespace.value || 'cluster-scoped')

const selectedNamespaceOrDefault = computed(
  () => selectedItem.value?.metadata?.namespace || selectedNamespace.value || discovery.value?.context.default_namespace || 'default',
)

const containerOptions = computed(() => extractContainerNames(selectedDetail.value?.object ?? null))
const selectedLogContainerLabel = computed(() => selectedLogContainer.value || '自动选择')
const selectedTerminalContainerLabel = computed(() => selectedTerminalContainer.value || '自动选择')
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

function cloneObject<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
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

function resolveServiceType(item: Record<string, any>) {
  const spec = item?.spec ?? {}
  return spec.type || 'ClusterIP'
}

function resolveServicePorts(item: Record<string, any>) {
  const spec = item?.spec ?? {}
  const ports = spec.ports ?? []
  if (!ports.length) {
    return '--'
  }
  return ports
    .map((port: Record<string, any>) => {
      const portNumber = port.port
      const targetPort = port.targetPort
      const protocol = port.protocol || 'TCP'
      const nodePort = port.nodePort
      if (nodePort) {
        return `${portNumber}:${nodePort}/${protocol}`
      }
      if (targetPort && targetPort !== portNumber) {
        return `${portNumber}->${targetPort}/${protocol}`
      }
      return `${portNumber}/${protocol}`
    })
    .join(', ')
}

function isServiceResource() {
  return selectedGroup.value?.group === 'core' && selectedResourceName.value === 'services'
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
      const storedNamespace = resolveStoredNamespace(selectedClusterId.value)
      const nextNamespace =
        options.preferredNamespace ||
        storedNamespace ||
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

function closeCustomDropdownMenus() {
  clusterMenuOpen.value = false
  namespaceMenuOpen.value = false
  logContainerMenuOpen.value = false
  terminalContainerMenuOpen.value = false
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (clusterMenuOpen.value || namespaceMenuOpen.value || logContainerMenuOpen.value || terminalContainerMenuOpen.value) {
      closeCustomDropdownMenus()
      event.preventDefault()
      return
    }
    if (yamlDialogOpen.value) {
      event.preventDefault()
      closeYamlDialog()
    }
  }
}

function handleDocumentPointerdown(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node)) {
    return
  }
  if (
    clusterMenuRef.value?.contains(target) ||
    namespaceMenuRef.value?.contains(target) ||
    logContainerMenuRef.value?.contains(target) ||
    terminalContainerMenuRef.value?.contains(target)
  ) {
    return
  }
  closeCustomDropdownMenus()
}

function toggleClusterMenu() {
  if (!clusterStore.items.length) {
    return
  }
  const nextOpen = !clusterMenuOpen.value
  closeCustomDropdownMenus()
  clusterMenuOpen.value = nextOpen
}

function selectCluster(clusterId: string) {
  selectedClusterId.value = clusterId
  clusterMenuOpen.value = false
}

function toggleNamespaceMenu() {
  if (!selectedResource.value?.namespaced) {
    return
  }
  const nextOpen = !namespaceMenuOpen.value
  closeCustomDropdownMenus()
  namespaceMenuOpen.value = nextOpen
}

function selectNamespace(namespace: string) {
  selectedNamespace.value = namespace
  namespaceMenuOpen.value = false
}

function toggleLogContainerMenu() {
  if (!containerOptions.value.length || !canViewPodLogs.value) {
    return
  }
  const nextOpen = !logContainerMenuOpen.value
  closeCustomDropdownMenus()
  logContainerMenuOpen.value = nextOpen
}

function selectLogContainer(container: string) {
  selectedLogContainer.value = container
  logContainerMenuOpen.value = false
}

function toggleTerminalContainerMenu() {
  if (!containerOptions.value.length || !canOpenTerminal.value) {
    return
  }
  const nextOpen = !terminalContainerMenuOpen.value
  closeCustomDropdownMenus()
  terminalContainerMenuOpen.value = nextOpen
}

function selectTerminalContainer(container: string) {
  selectedTerminalContainer.value = container
  terminalContainerMenuOpen.value = false
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

onMounted(async () => {
  document.addEventListener('keydown', handleGlobalKeydown)
  document.addEventListener('pointerdown', handleDocumentPointerdown)
  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }

  const storedSelection = readExplorerSelectionState()
  selectedClusterId.value = clusterStore.items.some((cluster) => cluster.id === storedSelection.clusterId)
    ? storedSelection.clusterId
    : clusterStore.items[0]?.id ?? ''
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
  stopLogFollowing()
  resetTerminalState()
  clearDetailRefreshTimer()
  stopWatching({ keepEvents: true })
})

watch(selectedClusterId, async (value, oldValue) => {
  if (!value || value === oldValue) {
    return
  }
  storeSelectedCluster(value)
  await loadDiscovery()
})

watch(selectedNamespace, (value) => {
  if (!value || !selectedClusterId.value || !selectedResource.value?.namespaced) {
    return
  }
  storeSelectedNamespace(selectedClusterId.value, value)
})

watch(selectedGroupKey, () => {
  if (!resources.value.some((resource) => resource.name === selectedResourceName.value)) {
    selectedResourceName.value = resources.value[0]?.name ?? ''
  }
})

watch(resourceSearchKeyword, () => {
  resourcePage.value = 1
})

watch(
  () => clusterStore.items.length,
  (count) => {
    if (!count) {
      clusterMenuOpen.value = false
    }
  },
)

watch(
  () => Boolean(selectedResource.value?.namespaced),
  (enabled) => {
    if (!enabled) {
      namespaceMenuOpen.value = false
    }
  },
)

watch([containerOptions, canOpenTerminal], ([containers, enabled]) => {
  if (!enabled || !containers.length) {
    terminalContainerMenuOpen.value = false
  }
})

watch([containerOptions, canViewPodLogs], ([containers, enabled]) => {
  if (!enabled || !containers.length) {
    logContainerMenuOpen.value = false
  }
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
  <div class="page-grid page-grid-fill">
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

      <div class="toolbar-grid explorer-toolbar-grid">
        <label class="field-label explorer-toolbar-dropdown-field">
          <span class="pod-quick-field-label">集群</span>
          <div
            ref="clusterMenuRef"
            class="pod-quick-dropdown"
            :class="{ 'pod-quick-dropdown-open': clusterMenuOpen }"
          >
            <button
              type="button"
              class="pod-quick-dropdown-trigger"
              :disabled="!clusterStore.items.length"
              :aria-expanded="clusterMenuOpen"
              aria-haspopup="menu"
              @click="toggleClusterMenu"
            >
              <span class="pod-quick-dropdown-value">{{ selectedClusterLabel }}</span>
              <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
            </button>

            <div v-if="clusterMenuOpen" class="pod-quick-dropdown-menu">
              <button
                v-for="cluster in clusterStore.items"
                :key="cluster.id"
                type="button"
                class="pod-quick-dropdown-option"
                :class="{ 'pod-quick-dropdown-option-active': selectedClusterId === cluster.id }"
                @click="selectCluster(cluster.id)"
              >
                {{ cluster.name }}
              </button>
            </div>
          </div>
        </label>

        <label class="field-label explorer-toolbar-dropdown-field">
          <span class="pod-quick-field-label">名称空间</span>
          <div
            ref="namespaceMenuRef"
            class="pod-quick-dropdown"
            :class="{ 'pod-quick-dropdown-open': namespaceMenuOpen }"
          >
            <button
              type="button"
              class="pod-quick-dropdown-trigger"
              :disabled="!selectedResource?.namespaced"
              :aria-expanded="namespaceMenuOpen"
              aria-haspopup="menu"
              @click="toggleNamespaceMenu"
            >
              <span class="pod-quick-dropdown-value">{{ selectedNamespaceLabel }}</span>
              <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
            </button>

            <div v-if="namespaceMenuOpen" class="pod-quick-dropdown-menu">
              <button
                type="button"
                class="pod-quick-dropdown-option"
                :class="{ 'pod-quick-dropdown-option-active': !selectedNamespace }"
                @click="selectNamespace('')"
              >
                cluster-scoped
              </button>
              <button
                v-for="namespace in namespaceOptions"
                :key="namespace.name"
                type="button"
                class="pod-quick-dropdown-option"
                :class="{ 'pod-quick-dropdown-option-active': selectedNamespace === namespace.name }"
                @click="selectNamespace(namespace.name)"
              >
                {{ namespace.name }}
              </button>
            </div>
          </div>
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
              <th v-if="isServiceResource()">类型</th>
              <th v-if="isServiceResource()">端口</th>
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
              <td v-if="isServiceResource()">{{ resolveServiceType(item) }}</td>
              <td v-if="isServiceResource()">{{ resolveServicePorts(item) }}</td>
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

        <section v-if="isPodResource && !isCreating" class="log-panel pod-quick-panel">
          <div class="pod-quick-header">
            <div>
              <h2 class="pod-quick-title">Pod 操作</h2>
              <p class="pod-quick-description">保留日志与终端入口，统一到同一操作区，方便快速排查。</p>
            </div>
            <div class="pod-quick-actions">
              <button class="button button-primary pod-quick-action" :disabled="!canViewPodLogs" @click="openPodLogsInNewTab">
                查看日志
              </button>
              <button
                class="button button-secondary pod-quick-action"
                :disabled="!canOpenTerminal"
                @click="openPodTerminalInNewTab('/bin/sh')"
              >
                sh
              </button>
              <button
                class="button button-secondary pod-quick-action"
                :disabled="!canOpenTerminal"
                @click="openPodTerminalInNewTab('/bin/bash')"
              >
                bash
              </button>
            </div>
          </div>

          <div class="pod-quick-grid">
            <section class="pod-quick-group">
              <h3 class="pod-quick-group-title">日志配置</h3>
              <div class="toolbar-grid pod-quick-toolbar pod-quick-toolbar-logs">
                <label class="field-label pod-quick-field">
                  <span class="pod-quick-field-label">日志容器</span>
                  <div
                    ref="logContainerMenuRef"
                    class="pod-quick-dropdown"
                    :class="{ 'pod-quick-dropdown-open': logContainerMenuOpen }"
                  >
                    <button
                      type="button"
                      class="pod-quick-dropdown-trigger"
                      :disabled="!containerOptions.length || !canViewPodLogs"
                      :aria-expanded="logContainerMenuOpen"
                      aria-haspopup="menu"
                      @click="toggleLogContainerMenu"
                    >
                      <span class="pod-quick-dropdown-value">{{ selectedLogContainerLabel }}</span>
                      <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
                    </button>

                    <div v-if="logContainerMenuOpen" class="pod-quick-dropdown-menu">
                      <button
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': !selectedLogContainer }"
                        @click="selectLogContainer('')"
                      >
                        自动选择
                      </button>
                      <button
                        v-for="container in containerOptions"
                        :key="`log:${container}`"
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': selectedLogContainer === container }"
                        @click="selectLogContainer(container)"
                      >
                        {{ container }}
                      </button>
                    </div>
                  </div>
                </label>

                <label class="field-label pod-quick-field">
                  <span class="pod-quick-field-label">初始日志行数</span>
                  <input v-model.number="logTailLines" type="number" min="10" max="2000" :disabled="!canViewPodLogs" />
                </label>
              </div>
              <div v-if="!canViewPodLogs && !loadingPermissions" class="helper-text pod-quick-helper">
                当前账号没有 `pods/log` 读取权限，暂时无法打开日志页签。
              </div>
              <div v-else class="helper-text pod-quick-helper">
                打开后默认跟随最新输出，如需回看历史日志，可在新页签内调整。
              </div>
            </section>

            <section class="pod-quick-group">
              <h3 class="pod-quick-group-title">终端配置</h3>
              <div class="toolbar-grid pod-quick-toolbar pod-quick-toolbar-terminal">
                <label class="field-label pod-quick-field pod-quick-terminal-field">
                  <span class="pod-quick-field-label">终端容器</span>
                  <div
                    ref="terminalContainerMenuRef"
                    class="pod-quick-dropdown"
                    :class="{ 'pod-quick-dropdown-open': terminalContainerMenuOpen }"
                  >
                    <button
                      type="button"
                      class="pod-quick-dropdown-trigger"
                      :disabled="!containerOptions.length || !canOpenTerminal"
                      :aria-expanded="terminalContainerMenuOpen"
                      aria-haspopup="menu"
                      @click="toggleTerminalContainerMenu"
                    >
                      <span class="pod-quick-dropdown-value">{{ selectedTerminalContainerLabel }}</span>
                      <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
                    </button>

                    <div v-if="terminalContainerMenuOpen" class="pod-quick-dropdown-menu">
                      <button
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': !selectedTerminalContainer }"
                        @click="selectTerminalContainer('')"
                      >
                        自动选择
                      </button>
                      <button
                        v-for="container in containerOptions"
                        :key="`terminal:${container}`"
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': selectedTerminalContainer === container }"
                        @click="selectTerminalContainer(container)"
                      >
                        {{ container }}
                      </button>
                    </div>
                  </div>
                </label>

                <label class="field-label pod-quick-field">
                  <span class="pod-quick-field-label">终端行数</span>
                  <input v-model.number="terminalRows" type="number" min="12" max="120" :disabled="!canOpenTerminal" />
                </label>

                <label class="field-label pod-quick-field">
                  <span class="pod-quick-field-label">终端列数</span>
                  <input v-model.number="terminalCols" type="number" min="40" max="240" :disabled="!canOpenTerminal" />
                </label>
              </div>
              <div v-if="!canOpenTerminal && !loadingPermissions" class="helper-text pod-quick-helper">
                当前账号没有 `pods/exec` 权限，暂时无法建立终端会话。
              </div>
              <div v-else class="helper-text pod-quick-helper">
                新页签会直接连接目标容器，支持命令输入、回车、Ctrl+C 和终端尺寸调整。
              </div>
            </section>
          </div>
        </section>
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
                    ? '这里支持查看并编辑当前资源的 YAML 内容，已自动隐藏 status、managedFields 等系统字段。'
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
