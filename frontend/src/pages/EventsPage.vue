<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { ClusterDiscoveryResponse, ClusterEventListResponse, ClusterEventRecord } from '../types'

const clusterStore = useClusterStore()

const EVENT_FETCH_LIMIT = 200
const EVENT_FETCH_MAX_PAGES = 10
const EVENT_SELECTION_STORAGE_KEY = 'kuboard.events.selection'

interface EventSelectionState {
  clusterId: string
  namespacesByCluster: Record<string, string>
}

const selectedClusterId = ref('')
const selectedNamespace = ref('')
const namespaces = ref<Array<{ name: string; phase: string }>>([])
const events = ref<ClusterEventRecord[]>([])
const selectedEventId = ref('')
const loading = ref(false)
const loadingDiscovery = ref(false)
const initializing = ref(true)
const errorMessage = ref('')
const discoveryError = ref('')
const keyword = ref('')
const typeFilter = ref<'all' | 'Warning' | 'Normal'>('all')
const eventPage = ref(1)
const eventPageSize = ref(20)
const eventPageSizeOptions = [20, 50, 100] as const
const typeFilterOptions = [
  { value: 'all', label: '全部类型' },
  { value: 'Warning', label: 'Warning' },
  { value: 'Normal', label: 'Normal' },
] as const
const lastSyncedAt = ref('')
const clusterMenuOpen = ref(false)
const clusterMenuRef = ref<HTMLElement | null>(null)
const namespaceMenuOpen = ref(false)
const namespaceMenuRef = ref<HTMLElement | null>(null)
const typeMenuOpen = ref(false)
const typeMenuRef = ref<HTMLElement | null>(null)
const eventPageSizeMenuOpen = ref(false)
const eventPageSizeMenuRef = ref<HTMLElement | null>(null)

function createEmptyEventSelectionState(): EventSelectionState {
  return {
    clusterId: '',
    namespacesByCluster: {},
  }
}

function readEventSelectionState(): EventSelectionState {
  if (typeof window === 'undefined') {
    return createEmptyEventSelectionState()
  }

  const storedValue = window.localStorage.getItem(EVENT_SELECTION_STORAGE_KEY)
  if (!storedValue) {
    return createEmptyEventSelectionState()
  }

  try {
    const parsed = JSON.parse(storedValue) as Partial<EventSelectionState> | null
    return {
      clusterId: typeof parsed?.clusterId === 'string' ? parsed.clusterId : '',
      namespacesByCluster: Object.fromEntries(
        Object.entries(parsed?.namespacesByCluster ?? {}).filter(
          ([clusterId, namespace]) => Boolean(clusterId) && typeof namespace === 'string',
        ),
      ),
    }
  } catch {
    return createEmptyEventSelectionState()
  }
}

function writeEventSelectionState(nextState: EventSelectionState) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(EVENT_SELECTION_STORAGE_KEY, JSON.stringify(nextState))
}

function storeSelectedCluster(clusterId: string) {
  if (!clusterId) {
    return
  }

  const nextState = readEventSelectionState()
  nextState.clusterId = clusterId
  writeEventSelectionState(nextState)
}

function storeSelectedNamespace(clusterId: string, namespace: string) {
  if (!clusterId) {
    return
  }

  const nextState = readEventSelectionState()
  nextState.clusterId = clusterId
  nextState.namespacesByCluster = {
    ...nextState.namespacesByCluster,
    [clusterId]: namespace,
  }
  writeEventSelectionState(nextState)
}

function resolveStoredNamespace(clusterId: string) {
  if (!clusterId) {
    return ''
  }

  return readEventSelectionState().namespacesByCluster[clusterId] || ''
}

const selectedEvent = computed(() => {
  if (!selectedEventId.value) {
    return null
  }

  return events.value.find((item) => item.id === selectedEventId.value) || null
})

const selectedClusterName = computed(() => {
  return clusterStore.items.find((cluster) => cluster.id === selectedClusterId.value)?.name || '--'
})

const clusterCount = computed(() => clusterStore.items.length)

const namespaceCount = computed(() => namespaces.value.length)

const selectedClusterLabel = computed(() => {
  return clusterStore.items.find((cluster) => cluster.id === selectedClusterId.value)?.name || '请选择集群'
})

const selectedNamespaceLabel = computed(() => selectedNamespace.value || '全部 namespace')

const selectedTypeFilterLabel = computed(() => {
  return typeFilterOptions.find((option) => option.value === typeFilter.value)?.label || '全部类型'
})

const selectedEventPageSizeLabel = computed(() => `${eventPageSize.value} 条`)

const summary = computed(() => {
  const total = events.value.length
  const warning = events.value.filter((item) => item.type.toLowerCase() === 'warning').length
  const normal = events.value.filter((item) => item.type.toLowerCase() === 'normal').length
  const namespaceCount = new Set(events.value.map((item) => item.namespace).filter(Boolean)).size
  return { total, warning, normal, namespaceCount }
})

const filteredEvents = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase()

  return events.value.filter((item) => {
    if (typeFilter.value !== 'all' && item.type.toLowerCase() !== typeFilter.value.toLowerCase()) {
      return false
    }

    if (!normalizedKeyword) {
      return true
    }

    const haystack = [
      item.namespace,
      item.type,
      item.reason,
      item.message,
      item.action,
      item.regarding.kind,
      item.regarding.name,
      item.regarding.field_path,
      item.source.component,
      item.source.instance,
    ]
      .join(' ')
      .toLowerCase()

    return haystack.includes(normalizedKeyword)
  })
})

const eventTotalPages = computed(() => Math.max(1, Math.ceil(filteredEvents.value.length / eventPageSize.value)))

const paginatedEvents = computed(() => {
  const start = (eventPage.value - 1) * eventPageSize.value
  return filteredEvents.value.slice(start, start + eventPageSize.value)
})

const eventPageStart = computed(() => (filteredEvents.value.length ? (eventPage.value - 1) * eventPageSize.value + 1 : 0))

const eventPageEnd = computed(() =>
  filteredEvents.value.length ? Math.min(eventPage.value * eventPageSize.value, filteredEvents.value.length) : 0,
)

function parseTime(value: string) {
  if (!value) {
    return 0
  }

  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function resolveEventTimestamp(item: ClusterEventRecord) {
  return item.last_seen || item.event_time || item.metadata.creation_timestamp || item.first_seen
}

function sortClusterEvents(items: ClusterEventRecord[]) {
  return [...items].sort((left, right) => {
    const timeDiff = parseTime(resolveEventTimestamp(right)) - parseTime(resolveEventTimestamp(left))
    if (timeDiff !== 0) {
      return timeDiff
    }

    const countDiff = right.count - left.count
    if (countDiff !== 0) {
      return countDiff
    }

    return `${left.namespace}/${left.name}`.localeCompare(`${right.namespace}/${right.name}`, 'zh-CN')
  })
}

function formatDateTime(value: string) {
  if (!value) {
    return '--'
  }

  const target = new Date(value)
  if (Number.isNaN(target.getTime())) {
    return value
  }

  return target.toLocaleString('zh-CN', { hour12: false })
}

function formatRefreshTime(value: string) {
  if (!value) {
    return '--'
  }
  return formatDateTime(value)
}

function resolveRegardingLabel(item: ClusterEventRecord) {
  const kind = item.regarding.kind || 'Object'
  const name = item.regarding.name || item.name || '--'
  return `${kind}/${name}`
}

function resolveSourceLabel(item: ClusterEventRecord) {
  if (item.source.component && item.source.instance) {
    return `${item.source.component} @ ${item.source.instance}`
  }
  return item.source.component || item.source.instance || '--'
}

function applyTypeFilter(nextType: 'all' | 'Warning' | 'Normal') {
  typeFilter.value = nextType
}

function closeEventDropdownMenus() {
  clusterMenuOpen.value = false
  namespaceMenuOpen.value = false
  typeMenuOpen.value = false
  eventPageSizeMenuOpen.value = false
}

function syncSelectedEventToPage() {
  if (!paginatedEvents.value.length) {
    selectedEventId.value = ''
    return
  }

  if (!paginatedEvents.value.some((item) => item.id === selectedEventId.value)) {
    selectedEventId.value = paginatedEvents.value[0].id
  }
}

function goToEventPage(page: number) {
  eventPage.value = Math.min(Math.max(page, 1), eventTotalPages.value)
}

async function fetchEvents() {
  if (!selectedClusterId.value) {
    events.value = []
    selectedEventId.value = ''
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    let continueToken = ''
    const collected: ClusterEventRecord[] = []
    const seenIds = new Set<string>()

    for (let pageIndex = 0; pageIndex < EVENT_FETCH_MAX_PAGES; pageIndex += 1) {
      const query = new URLSearchParams({
        limit: String(EVENT_FETCH_LIMIT),
      })

      if (selectedNamespace.value) {
        query.set('namespace', selectedNamespace.value)
      }
      if (continueToken) {
        query.set('continue_token', continueToken)
      }

      const payload = await apiRequest<ClusterEventListResponse>(
        `/api/v1/clusters/${selectedClusterId.value}/events?${query.toString()}`,
      )

      payload.items.forEach((item) => {
        if (seenIds.has(item.id)) {
          return
        }
        seenIds.add(item.id)
        collected.push(item)
      })

      continueToken = payload.metadata.continue || ''
      if (!continueToken) {
        break
      }
    }

    events.value = sortClusterEvents(collected)
    if (eventPage.value > eventTotalPages.value) {
      eventPage.value = eventTotalPages.value
    }
    syncSelectedEventToPage()
    lastSyncedAt.value = new Date().toISOString()
  } catch (error) {
    events.value = []
    selectedEventId.value = ''
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = '加载 Kubernetes 事件失败，请稍后重试。'
    }
  } finally {
    loading.value = false
  }
}

async function loadClusterContext() {
  if (!selectedClusterId.value) {
    namespaces.value = []
    events.value = []
    selectedEventId.value = ''
    return
  }

  loadingDiscovery.value = true
  discoveryError.value = ''
  errorMessage.value = ''
  events.value = []
  selectedEventId.value = ''

  try {
    const payload = await apiRequest<ClusterDiscoveryResponse>(`/api/v1/clusters/${selectedClusterId.value}/discovery`)
    namespaces.value = [...payload.namespaces].sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))

    if (selectedNamespace.value && !namespaces.value.some((namespace) => namespace.name === selectedNamespace.value)) {
      selectedNamespace.value = ''
      storeSelectedNamespace(selectedClusterId.value, '')
    }

    const hasEventResource = payload.groups.some((group) => group.resources.some((resource) => resource.name === 'events'))
    if (!hasEventResource) {
      discoveryError.value = '当前集群 Discovery 未发现可用的 Events 资源。'
      return
    }

    await fetchEvents()
  } catch (error) {
    namespaces.value = []
    events.value = []
    selectedEventId.value = ''
    if (error instanceof ApiError) {
      discoveryError.value = error.message
    } else {
      discoveryError.value = '加载集群资源发现信息失败，请稍后重试。'
    }
  } finally {
    loadingDiscovery.value = false
  }
}

async function initializePage() {
  initializing.value = true
  errorMessage.value = ''
  discoveryError.value = ''

  try {
    await clusterStore.fetchClusters()
    if (!clusterStore.items.length) {
      selectedClusterId.value = ''
      selectedNamespace.value = ''
      namespaces.value = []
      return
    }

    const storedState = readEventSelectionState()
    const initialClusterId = clusterStore.items.some((cluster) => cluster.id === storedState.clusterId)
      ? storedState.clusterId
      : clusterStore.items[0].id

    selectedClusterId.value = initialClusterId
    selectedNamespace.value = resolveStoredNamespace(initialClusterId)
    storeSelectedCluster(initialClusterId)
    await loadClusterContext()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = '加载集群列表失败，请稍后重试。'
    }
  } finally {
    initializing.value = false
  }
}

function toggleClusterMenu() {
  if (!clusterStore.items.length || clusterStore.loading || loadingDiscovery.value) {
    return
  }

  const nextOpen = !clusterMenuOpen.value
  closeEventDropdownMenus()
  clusterMenuOpen.value = nextOpen
}

function toggleNamespaceMenu() {
  if (!selectedClusterId.value || loadingDiscovery.value) {
    return
  }

  const nextOpen = !namespaceMenuOpen.value
  closeEventDropdownMenus()
  namespaceMenuOpen.value = nextOpen
}

function toggleTypeMenu() {
  const nextOpen = !typeMenuOpen.value
  closeEventDropdownMenus()
  typeMenuOpen.value = nextOpen
}

function toggleEventPageSizeMenu() {
  const nextOpen = !eventPageSizeMenuOpen.value
  closeEventDropdownMenus()
  eventPageSizeMenuOpen.value = nextOpen
}

async function selectCluster(nextClusterId: string) {
  closeEventDropdownMenus()
  if (nextClusterId === selectedClusterId.value) {
    return
  }

  selectedClusterId.value = nextClusterId
  selectedNamespace.value = resolveStoredNamespace(nextClusterId)
  storeSelectedCluster(nextClusterId)
  await loadClusterContext()
}

async function selectNamespace(nextNamespace: string) {
  closeEventDropdownMenus()
  if (!selectedClusterId.value || nextNamespace === selectedNamespace.value) {
    return
  }

  selectedNamespace.value = nextNamespace
  storeSelectedNamespace(selectedClusterId.value, selectedNamespace.value)
  await fetchEvents()
}

function selectTypeFilter(nextType: 'all' | 'Warning' | 'Normal') {
  typeFilter.value = nextType
  typeMenuOpen.value = false
}

function selectEventPageSize(size: (typeof eventPageSizeOptions)[number]) {
  eventPageSize.value = size
  eventPageSizeMenuOpen.value = false
}

function handleDocumentPointerdown(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node)) {
    return
  }

  if (
    clusterMenuRef.value?.contains(target) ||
    namespaceMenuRef.value?.contains(target) ||
    typeMenuRef.value?.contains(target) ||
    eventPageSizeMenuRef.value?.contains(target)
  ) {
    return
  }

  closeEventDropdownMenus()
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (
    event.key === 'Escape' &&
    (clusterMenuOpen.value || namespaceMenuOpen.value || typeMenuOpen.value || eventPageSizeMenuOpen.value)
  ) {
    closeEventDropdownMenus()
    event.preventDefault()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown)
  document.addEventListener('pointerdown', handleDocumentPointerdown)
  void initializePage()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
})

watch([keyword, typeFilter], () => {
  eventPage.value = 1
})

watch(eventPageSize, () => {
  eventPage.value = 1
})

watch(filteredEvents, () => {
  if (eventPage.value > eventTotalPages.value) {
    eventPage.value = eventTotalPages.value
  }
})

watch(paginatedEvents, () => {
  syncSelectedEventToPage()
})
</script>

<template>
  <div class="page-grid page-grid-fill">
    <section class="hero-panel audit-hero-panel events-hero-panel">
      <div class="section-head">
        <div>
          <h2 class="page-title">事件中心</h2>
          <p>独立查看 Kubernetes Events，默认支持跨 namespace 汇总，再按对象和原因快速筛查。</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" :disabled="loading || loadingDiscovery || !selectedClusterId" @click="fetchEvents">
            刷新事件
          </button>
        </div>
      </div>

      <div class="audit-toolbar events-toolbar">
        <label class="field-label explorer-toolbar-dropdown-field">
          <span class="explorer-toolbar-label">
            <span class="pod-quick-field-label">集群</span>
            <span class="explorer-toolbar-count">{{ clusterCount }}</span>
          </span>
          <div
            ref="clusterMenuRef"
            class="pod-quick-dropdown"
            :class="{ 'pod-quick-dropdown-open': clusterMenuOpen }"
          >
            <button
              type="button"
              class="pod-quick-dropdown-trigger"
              :disabled="clusterStore.loading || loadingDiscovery || !clusterStore.items.length"
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
          <span class="explorer-toolbar-label">
            <span class="pod-quick-field-label">名称空间</span>
            <span class="explorer-toolbar-count">{{ namespaceCount }}</span>
          </span>
          <div
            ref="namespaceMenuRef"
            class="pod-quick-dropdown"
            :class="{ 'pod-quick-dropdown-open': namespaceMenuOpen }"
          >
            <button
              type="button"
              class="pod-quick-dropdown-trigger"
              :disabled="!selectedClusterId || loadingDiscovery"
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
                全部 namespace
              </button>
              <button
                v-for="namespace in namespaces"
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

        <label class="field-label explorer-toolbar-dropdown-field">
          <span class="pod-quick-field-label">类型</span>
          <div
            ref="typeMenuRef"
            class="pod-quick-dropdown"
            :class="{ 'pod-quick-dropdown-open': typeMenuOpen }"
          >
            <button
              type="button"
              class="pod-quick-dropdown-trigger"
              :aria-expanded="typeMenuOpen"
              aria-haspopup="menu"
              @click="toggleTypeMenu"
            >
              <span class="pod-quick-dropdown-value">{{ selectedTypeFilterLabel }}</span>
              <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
            </button>

            <div v-if="typeMenuOpen" class="pod-quick-dropdown-menu">
              <button
                v-for="option in typeFilterOptions"
                :key="option.value"
                type="button"
                class="pod-quick-dropdown-option"
                :class="{ 'pod-quick-dropdown-option-active': typeFilter === option.value }"
                @click="selectTypeFilter(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </label>

        <label class="field-label">
          <span class="pod-quick-field-label">搜索</span>
          <input
            v-model="keyword"
            class="cluster-search"
            type="text"
            placeholder="搜索 namespace / reason / 对象 / source / message"
          />
        </label>
      </div>

      <div class="cluster-summary-grid audit-summary-grid events-summary-grid">
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': typeFilter === 'all' }"
          @click="applyTypeFilter('all')"
        >
          <span>总事件数</span>
          <strong>{{ summary.total }}</strong>
        </button>
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': typeFilter === 'Warning' }"
          @click="applyTypeFilter('Warning')"
        >
          <span>Warning</span>
          <strong class="is-error">{{ summary.warning }}</strong>
        </button>
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': typeFilter === 'Normal' }"
          @click="applyTypeFilter('Normal')"
        >
          <span>Normal</span>
          <strong class="is-ready">{{ summary.normal }}</strong>
        </button>
        <div class="cluster-summary-card">
          <span>涉及 namespace</span>
          <strong>{{ summary.namespaceCount }}</strong>
        </div>
      </div>

      <div class="button-row events-meta-bar">
        <span class="muted">最近刷新：{{ formatRefreshTime(lastSyncedAt) }}</span>
      </div>

      <div v-if="discoveryError" class="error-text" style="margin-top: 12px">{{ discoveryError }}</div>
      <div v-else-if="errorMessage" class="error-text" style="margin-top: 12px">{{ errorMessage }}</div>
      <div v-else-if="loadingDiscovery || initializing" class="helper-text" style="margin-top: 12px">
        正在同步集群资源发现信息...
      </div>
    </section>

    <section class="surface-card audit-workspace">
      <div v-if="!clusterStore.items.length && !clusterStore.loading && !initializing" class="empty-state">
        当前还没有可用集群，先到“集群”页面接入 Kubernetes 集群。
      </div>
      <div v-else class="split-detail audit-split events-split">
        <div class="audit-table-wrap">
          <div v-if="filteredEvents.length && !loading" class="audit-table-summary">
            共 {{ filteredEvents.length }} 条，当前显示第 {{ eventPageStart || 0 }} - {{ eventPageEnd || 0 }} 条。
          </div>

          <div v-if="loading" class="empty-state">正在加载 Kubernetes Events...</div>
          <template v-else-if="filteredEvents.length">
            <div class="audit-table-panel">
              <table class="table audit-table events-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>Namespace</th>
                    <th>类型</th>
                    <th>Reason</th>
                    <th>对象</th>
                    <th>Message</th>
                    <th>次数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="item in paginatedEvents"
                    :key="item.id"
                    :class="{ 'table-row-active': selectedEventId === item.id }"
                    @click="selectedEventId = item.id"
                    style="cursor: pointer"
                  >
                    <td>{{ formatDateTime(resolveEventTimestamp(item)) }}</td>
                    <td>{{ item.namespace || '--' }}</td>
                    <td><StatusBadge :value="item.type" /></td>
                    <td>{{ item.reason || '--' }}</td>
                    <td>
                      <div class="audit-cell-main events-object-cell">
                        <strong>{{ resolveRegardingLabel(item) }}</strong>
                        <span class="muted">{{ item.regarding.field_path || item.action || '--' }}</span>
                      </div>
                    </td>
                    <td class="events-message-cell">
                      <div class="events-message-text">{{ item.message || '--' }}</div>
                    </td>
                    <td>{{ item.count }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="explorer-pagination">
              <div class="explorer-pagination-pill">
                第 {{ eventPage }} / {{ eventTotalPages }} 页
              </div>
              <div class="explorer-pagination-controls">
                <label class="field-label explorer-page-size-field">
                  <div
                    ref="eventPageSizeMenuRef"
                    class="pod-quick-dropdown"
                    :class="{ 'pod-quick-dropdown-open': eventPageSizeMenuOpen }"
                  >
                    <button
                      type="button"
                      class="pod-quick-dropdown-trigger"
                      :aria-expanded="eventPageSizeMenuOpen"
                      aria-haspopup="menu"
                      @click="toggleEventPageSizeMenu"
                    >
                      <span class="pod-quick-dropdown-value">{{ selectedEventPageSizeLabel }}</span>
                      <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
                    </button>

                    <div v-if="eventPageSizeMenuOpen" class="pod-quick-dropdown-menu">
                      <button
                        v-for="size in eventPageSizeOptions"
                        :key="size"
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': eventPageSize === size }"
                        @click="selectEventPageSize(size)"
                      >
                        {{ size }} 条
                      </button>
                    </div>
                  </div>
                </label>
              </div>
              <div class="button-row explorer-pagination-actions">
                <button class="button button-secondary explorer-pagination-button" :disabled="eventPage <= 1" @click="goToEventPage(1)">
                  首
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="eventPage <= 1"
                  @click="goToEventPage(eventPage - 1)"
                >
                  上一页
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="eventPage >= eventTotalPages"
                  @click="goToEventPage(eventPage + 1)"
                >
                  下一页
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="eventPage >= eventTotalPages"
                  @click="goToEventPage(eventTotalPages)"
                >
                  末
                </button>
              </div>
            </div>
          </template>
          <div v-else class="empty-state">
            {{ selectedClusterId ? '当前筛选条件下没有事件。' : '请选择一个集群开始查看事件。' }}
          </div>
        </div>

        <aside class="audit-detail-panel">
          <div class="section-head" style="margin-bottom: 10px">
            <div>
              <h2>事件详情</h2>
              <p>选中左侧事件查看对象、来源和原始负载。</p>
            </div>
          </div>

          <div v-if="selectedEvent" class="audit-detail-grid">
            <div class="audit-detail-item">
              <span>集群 / Namespace</span>
              <strong>{{ selectedClusterName }} / {{ selectedEvent.namespace || '--' }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>类型 / Reason</span>
              <div class="button-row" style="margin-top: 6px">
                <StatusBadge :value="selectedEvent.type" />
                <code>{{ selectedEvent.reason || '--' }}</code>
              </div>
            </div>
            <div class="audit-detail-item">
              <span>对象</span>
              <strong>{{ resolveRegardingLabel(selectedEvent) }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>Source</span>
              <strong>{{ resolveSourceLabel(selectedEvent) }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>发生次数</span>
              <strong>{{ selectedEvent.count }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>首次 / 最近一次</span>
              <strong>{{ formatDateTime(selectedEvent.first_seen) }} / {{ formatDateTime(selectedEvent.last_seen) }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>Message</span>
              <pre class="json-block events-message-detail">{{ selectedEvent.message || '--' }}</pre>
            </div>
            <div class="audit-detail-item">
              <span>Raw Event</span>
              <pre class="json-block">{{ JSON.stringify(selectedEvent.raw, null, 2) }}</pre>
            </div>
          </div>
          <div v-else class="empty-state">请选择一条事件查看详情。</div>
        </aside>
      </div>
    </section>
  </div>
</template>
