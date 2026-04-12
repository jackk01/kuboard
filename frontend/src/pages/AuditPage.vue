<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import type { AuditEvent } from '../types'

const loading = ref(true)
const errorMessage = ref('')
const events = ref<AuditEvent[]>([])
const selectedEventId = ref<number | null>(null)
const auditPage = ref(1)
const auditPageSize = ref(10)
const auditPageSizeOptions = [10, 20, 50, 100] as const
const auditPageSizeMenuOpen = ref(false)
const auditPageSizeMenuRef = ref<HTMLElement | null>(null)

const keyword = ref('')
const statusFilter = ref<'all' | 'success' | 'error' | 'denied'>('all')
const severityFilter = ref<'all' | 'info' | 'warning' | 'critical'>('all')

const selectedEvent = computed(() => {
  if (!selectedEventId.value) return null
  return events.value.find((item) => item.id === selectedEventId.value) || null
})

const summary = computed(() => {
  const total = events.value.length
  const success = events.value.filter((event) => event.status === 'success').length
  const denied = events.value.filter((event) => event.status === 'denied').length
  const error = events.value.filter((event) => event.status === 'error').length
  return { total, success, denied, error }
})

const filteredEvents = computed(() => {
  const k = keyword.value.trim().toLowerCase()

  return events.value
    .filter((event) => {
      if (statusFilter.value !== 'all' && event.status !== statusFilter.value) {
        return false
      }
      if (severityFilter.value !== 'all' && event.severity !== severityFilter.value) {
        return false
      }
      if (!k) return true

      const eventText = [
        event.event_type,
        event.actor_display || '',
        event.actor_email || '',
        event.cluster_name || '',
        event.request_id || '',
      ]
        .join(' ')
        .toLowerCase()
      return eventText.includes(k)
    })
})

const auditTotalPages = computed(() => Math.max(1, Math.ceil(filteredEvents.value.length / auditPageSize.value)))

const paginatedEvents = computed(() => {
  const start = (auditPage.value - 1) * auditPageSize.value
  return filteredEvents.value.slice(start, start + auditPageSize.value)
})

const auditPageStart = computed(() => (filteredEvents.value.length ? (auditPage.value - 1) * auditPageSize.value + 1 : 0))

const auditPageEnd = computed(() =>
  filteredEvents.value.length ? Math.min(auditPage.value * auditPageSize.value, filteredEvents.value.length) : 0,
)

const selectedAuditPageSizeLabel = computed(() => `${auditPageSize.value} 条`)

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function applyStatusFilter(nextStatus: 'all' | 'success' | 'error' | 'denied') {
  statusFilter.value = nextStatus
}

function closeAuditDropdownMenus() {
  auditPageSizeMenuOpen.value = false
}

function syncSelectedEventToPage() {
  if (!paginatedEvents.value.length) {
    selectedEventId.value = null
    return
  }

  if (!paginatedEvents.value.some((event) => event.id === selectedEventId.value)) {
    selectedEventId.value = paginatedEvents.value[0].id
  }
}

function copyRequestId() {
  if (!selectedEvent.value?.request_id) return
  navigator.clipboard.writeText(selectedEvent.value.request_id)
}

function goToAuditPage(page: number) {
  auditPage.value = Math.min(Math.max(page, 1), auditTotalPages.value)
}

function toggleAuditPageSizeMenu() {
  const nextOpen = !auditPageSizeMenuOpen.value
  closeAuditDropdownMenus()
  auditPageSizeMenuOpen.value = nextOpen
}

function selectAuditPageSize(size: (typeof auditPageSizeOptions)[number]) {
  auditPageSize.value = size
  auditPageSizeMenuOpen.value = false
}

async function fetchEvents() {
  loading.value = true
  errorMessage.value = ''
  try {
    events.value = await apiRequest<AuditEvent[]>('/api/v1/audit/events?limit=100')
    if (auditPage.value > auditTotalPages.value) {
      auditPage.value = auditTotalPages.value
    }
    syncSelectedEventToPage()
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = '加载审计事件失败，请稍后重试。'
    }
  } finally {
    loading.value = false
  }
}

function handleShellCommand(event: Event) {
  const customEvent = event as CustomEvent<{ action?: string }>
  if (customEvent.detail?.action === 'audit.refresh') {
    void fetchEvents()
  }
}

function handleDocumentPointerdown(event: PointerEvent) {
  const target = event.target
  if (!(target instanceof Node)) {
    return
  }
  if (auditPageSizeMenuRef.value?.contains(target)) {
    return
  }
  closeAuditDropdownMenus()
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && auditPageSizeMenuOpen.value) {
    closeAuditDropdownMenus()
    event.preventDefault()
  }
}

onMounted(() => {
  window.addEventListener('kuboard:command', handleShellCommand as EventListener)
  window.addEventListener('keydown', handleGlobalKeydown)
  document.addEventListener('pointerdown', handleDocumentPointerdown)
  void fetchEvents()
})

onBeforeUnmount(() => {
  window.removeEventListener('kuboard:command', handleShellCommand as EventListener)
  window.removeEventListener('keydown', handleGlobalKeydown)
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
})

watch([keyword, statusFilter, severityFilter], () => {
  auditPage.value = 1
})

watch(auditPageSize, () => {
  auditPage.value = 1
})

watch(filteredEvents, () => {
  if (auditPage.value > auditTotalPages.value) {
    auditPage.value = auditTotalPages.value
  }
})

watch(paginatedEvents, () => {
  syncSelectedEventToPage()
})
</script>

<template>
  <div class="page-grid page-grid-fill">
    <section class="hero-panel audit-hero-panel">
      <div class="section-head">
        <div>
          <h2 class="page-title">审计中心</h2>
          <p>统一面板化体验：筛选工具栏、高密度表格、侧边详情。</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" :disabled="loading" @click="fetchEvents">刷新审计</button>
        </div>
      </div>

      <div class="cluster-summary-grid audit-summary-grid">
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': statusFilter === 'all' }"
          @click="applyStatusFilter('all')"
        >
          <span>总事件数</span>
          <strong>{{ summary.total }}</strong>
        </button>
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': statusFilter === 'success' }"
          @click="applyStatusFilter('success')"
        >
          <span>成功</span>
          <strong class="is-ready">{{ summary.success }}</strong>
        </button>
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': statusFilter === 'denied' }"
          @click="applyStatusFilter('denied')"
        >
          <span>拒绝</span>
          <strong class="is-pending">{{ summary.denied }}</strong>
        </button>
        <button
          type="button"
          class="cluster-summary-card audit-summary-card-button"
          :class="{ 'audit-summary-card-active': statusFilter === 'error' }"
          @click="applyStatusFilter('error')"
        >
          <span>错误</span>
          <strong class="is-error">{{ summary.error }}</strong>
        </button>
      </div>
    </section>

    <section class="surface-card audit-workspace">
      <div class="audit-toolbar">
        <input
          v-model="keyword"
          class="cluster-search"
          placeholder="搜索 event_type / 用户 / 集群 / request_id"
        />
        <select v-model="statusFilter" class="cluster-filter">
          <option value="all">全部状态</option>
          <option value="success">success</option>
          <option value="denied">denied</option>
          <option value="error">error</option>
        </select>
        <select v-model="severityFilter" class="cluster-filter">
          <option value="all">全部级别</option>
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="critical">critical</option>
        </select>
      </div>

      <div v-if="errorMessage" class="error-text">{{ errorMessage }}</div>

      <div class="split-detail audit-split">
        <div class="audit-table-wrap">
          <div v-if="filteredEvents.length && !loading" class="audit-table-summary">
            共 {{ filteredEvents.length }} 条，当前显示第 {{ auditPageStart || 0 }} - {{ auditPageEnd || 0 }} 条。
          </div>
          <div v-if="loading" class="empty-state">正在加载审计事件...</div>
          <template v-else-if="filteredEvents.length">
            <div class="audit-table-panel">
              <table class="table audit-table">
                <thead>
                  <tr>
                    <th>事件</th>
                    <th>状态</th>
                    <th>级别</th>
                    <th>操作者</th>
                    <th>目标集群</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="event in paginatedEvents"
                    :key="event.id"
                    :class="{ 'table-row-active': selectedEventId === event.id }"
                    @click="selectedEventId = event.id"
                    style="cursor: pointer"
                  >
                    <td>
                      <div class="audit-cell-main">
                        <strong>{{ event.event_type }}</strong>
                        <span class="muted">{{ event.request_id || 'no-request-id' }}</span>
                      </div>
                    </td>
                    <td><StatusBadge :value="event.status" /></td>
                    <td><StatusBadge :value="event.severity" /></td>
                    <td>{{ event.actor_display || event.actor_email || 'system' }}</td>
                    <td>{{ event.cluster_name || '--' }}</td>
                    <td>{{ formatDateTime(event.created_at) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="explorer-pagination">
              <div class="explorer-pagination-pill">
                第 {{ auditPage }} / {{ auditTotalPages }} 页
              </div>
              <div class="explorer-pagination-controls">
                <label class="field-label explorer-page-size-field">
                  <div
                    ref="auditPageSizeMenuRef"
                    class="pod-quick-dropdown"
                    :class="{ 'pod-quick-dropdown-open': auditPageSizeMenuOpen }"
                  >
                    <button
                      type="button"
                      class="pod-quick-dropdown-trigger"
                      :aria-expanded="auditPageSizeMenuOpen"
                      aria-haspopup="menu"
                      @click="toggleAuditPageSizeMenu"
                    >
                      <span class="pod-quick-dropdown-value">{{ selectedAuditPageSizeLabel }}</span>
                      <span class="pod-quick-dropdown-caret" aria-hidden="true"></span>
                    </button>

                    <div v-if="auditPageSizeMenuOpen" class="pod-quick-dropdown-menu">
                      <button
                        v-for="size in auditPageSizeOptions"
                        :key="size"
                        type="button"
                        class="pod-quick-dropdown-option"
                        :class="{ 'pod-quick-dropdown-option-active': auditPageSize === size }"
                        @click="selectAuditPageSize(size)"
                      >
                        {{ size }} 条
                      </button>
                    </div>
                  </div>
                </label>
              </div>
              <div class="button-row explorer-pagination-actions">
                <button class="button button-secondary explorer-pagination-button" :disabled="auditPage <= 1" @click="goToAuditPage(1)">
                  首
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="auditPage <= 1"
                  @click="goToAuditPage(auditPage - 1)"
                >
                  上一页
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="auditPage >= auditTotalPages"
                  @click="goToAuditPage(auditPage + 1)"
                >
                  下一页
                </button>
                <button
                  class="button button-secondary explorer-pagination-button"
                  :disabled="auditPage >= auditTotalPages"
                  @click="goToAuditPage(auditTotalPages)"
                >
                  末
                </button>
              </div>
            </div>
          </template>
          <div v-else class="empty-state">当前筛选条件下没有审计事件。</div>
        </div>

        <aside class="audit-detail-panel">
          <div class="section-head" style="margin-bottom: 10px">
            <div>
              <h2>事件详情</h2>
              <p>选中左侧事件查看上下文。</p>
            </div>
          </div>

          <div v-if="selectedEvent" class="audit-detail-grid">
            <div class="audit-detail-item">
              <span>事件类型</span>
              <strong>{{ selectedEvent.event_type }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>状态 / 级别</span>
              <div class="button-row" style="margin-top: 6px">
                <StatusBadge :value="selectedEvent.status" />
                <StatusBadge :value="selectedEvent.severity" />
              </div>
            </div>
            <div class="audit-detail-item">
              <span>操作者</span>
              <strong>{{ selectedEvent.actor_display || selectedEvent.actor_email || 'system' }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>目标集群</span>
              <strong>{{ selectedEvent.cluster_name || '--' }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>时间</span>
              <strong>{{ formatDateTime(selectedEvent.created_at) }}</strong>
            </div>
            <div class="audit-detail-item">
              <span>Request ID</span>
              <div class="button-row" style="margin-top: 6px">
                <code>{{ selectedEvent.request_id || 'no-request-id' }}</code>
                <button class="button button-secondary" :disabled="!selectedEvent.request_id" @click="copyRequestId">
                  复制
                </button>
              </div>
            </div>

            <div class="audit-detail-item">
              <span>Target</span>
              <pre class="json-block">{{ JSON.stringify(selectedEvent.target, null, 2) }}</pre>
            </div>
            <div class="audit-detail-item">
              <span>Metadata</span>
              <pre class="json-block">{{ JSON.stringify(selectedEvent.metadata, null, 2) }}</pre>
            </div>
          </div>
          <div v-else class="empty-state">请选择一条事件查看详情。</div>
        </aside>
      </div>
    </section>
  </div>
</template>
