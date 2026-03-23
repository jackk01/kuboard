<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import type { AuditEvent } from '../types'

const loading = ref(true)
const errorMessage = ref('')
const events = ref<AuditEvent[]>([])
const selectedEventId = ref<number | null>(null)

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

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function copyRequestId() {
  if (!selectedEvent.value?.request_id) return
  navigator.clipboard.writeText(selectedEvent.value.request_id)
}

async function fetchEvents() {
  loading.value = true
  errorMessage.value = ''
  try {
    events.value = await apiRequest<AuditEvent[]>('/api/v1/audit/events?limit=100')
    if (!selectedEventId.value && events.value.length) {
      selectedEventId.value = events.value[0].id
    }
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

onMounted(async () => {
  await fetchEvents()
})

function handleShellCommand(event: Event) {
  const customEvent = event as CustomEvent<{ action?: string }>
  if (customEvent.detail?.action === 'audit.refresh') {
    void fetchEvents()
  }
}

onMounted(() => {
  window.addEventListener('kuboard:command', handleShellCommand as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('kuboard:command', handleShellCommand as EventListener)
})
</script>

<template>
  <div class="page-grid">
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
        <article class="cluster-summary-card">
          <span>总事件数</span>
          <strong>{{ summary.total }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>成功</span>
          <strong class="is-ready">{{ summary.success }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>拒绝</span>
          <strong class="is-pending">{{ summary.denied }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>错误</span>
          <strong class="is-error">{{ summary.error }}</strong>
        </article>
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
          <div v-if="loading" class="empty-state">正在加载审计事件...</div>
          <table v-else-if="filteredEvents.length" class="table audit-table">
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
                v-for="event in filteredEvents"
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
