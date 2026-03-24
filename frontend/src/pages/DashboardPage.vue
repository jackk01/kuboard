<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { DashboardSummary } from '../types'

interface ReadinessPayload {
  status: string
  checks: {
    database: { ok: boolean; message: string }
    cache: { ok: boolean; message: string }
  }
}

const loading = ref(true)
const readinessLoading = ref(true)
const summary = ref<DashboardSummary | null>(null)
const readiness = ref<ReadinessPayload | null>(null)
const errorMessage = ref('')
const clusterStore = useClusterStore()

const clusterStats = computed(() => {
  const clusters = clusterStore.items
  return {
    ready: clusters.filter((cluster) => cluster.status === 'ready').length,
    pending: clusters.filter((cluster) => cluster.status === 'pending').length,
    error: clusters.filter((cluster) => cluster.status === 'error').length,
    healthy: clusters.filter((cluster) => cluster.health_state === 'healthy').length,
    degraded: clusters.filter((cluster) => cluster.health_state === 'degraded').length,
    unknown: clusters.filter((cluster) => cluster.health_state === 'unknown').length,
  }
})

const platformStatus = computed(() => {
  if (readinessLoading.value) return 'unknown'
  if (readiness.value?.status === 'ok') return 'ready'
  return 'degraded'
})

const featureItems = computed(() => {
  const features = summary.value?.features
  return [
    { label: 'SQLite 模式', enabled: Boolean(features?.sqlite_mode) },
    { label: 'RBAC Bridge', enabled: Boolean(features?.rbac_bridge) },
    { label: 'Stream Hub', enabled: Boolean(features?.stream_hub) },
  ]
})

async function fetchDashboard() {
  errorMessage.value = ''
  loading.value = true
  readinessLoading.value = true
  try {
    const [summaryPayload, readinessPayload] = await Promise.all([
      apiRequest<DashboardSummary>('/api/v1/dashboard/summary'),
      apiRequest<ReadinessPayload>('/api/v1/health/ready', {
        skipAuth: true,
        acceptErrorResponse: true,
      }),
      clusterStore.fetchClusters(),
    ])
    summary.value = summaryPayload
    readiness.value = readinessPayload
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = '加载总览失败，请稍后重试。'
    }
  } finally {
    loading.value = false
    readinessLoading.value = false
  }
}

onMounted(async () => {
  await fetchDashboard()
})
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel dashboard-hero-panel">
      <div class="section-head">
        <div>
          <h2 class="page-title">平台总览</h2>
          <p>与集群页统一的面板化架构：核心状态、可操作入口、最近活动。</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" :disabled="loading" @click="fetchDashboard">刷新总览</button>
          <RouterLink class="button button-primary" :to="{ name: 'clusters' }">进入集群</RouterLink>
        </div>
      </div>

      <div class="cluster-summary-grid dashboard-summary-grid">
        <article class="cluster-summary-card">
          <span>Ready</span>
          <strong class="is-ready">{{ clusterStats.ready }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>Pending</span>
          <strong class="is-pending">{{ clusterStats.pending }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>Error</span>
          <strong class="is-error">{{ clusterStats.error }}</strong>
        </article>
      </div>
    </section>

    <section class="surface-card dashboard-workspace">
      <div v-if="errorMessage" class="error-text">{{ errorMessage }}</div>

      <div class="dual-grid dashboard-top-grid">
        <article class="dashboard-panel">
          <div class="section-head" style="margin-bottom: 10px">
            <div>
              <h2>平台运行态</h2>
              <p>后端就绪状态与集群健康分布。</p>
            </div>
            <StatusBadge :value="platformStatus" />
          </div>

          <div class="dashboard-health-grid">
            <div class="dashboard-health-item">
              <span>健康</span>
              <strong>{{ clusterStats.healthy }}</strong>
            </div>
            <div class="dashboard-health-item">
              <span>退化</span>
              <strong class="is-error">{{ clusterStats.degraded }}</strong>
            </div>
            <div class="dashboard-health-item">
              <span>未知</span>
              <strong class="is-pending">{{ clusterStats.unknown }}</strong>
            </div>
          </div>

          <div class="dashboard-check-row">
            <span>Database</span>
            <StatusBadge :value="readiness?.checks.database.ok ? 'ready' : 'error'" />
          </div>
          <div class="dashboard-check-row">
            <span>Cache</span>
            <StatusBadge :value="readiness?.checks.cache.ok ? 'ready' : 'error'" />
          </div>
        </article>

        <article class="dashboard-panel">
          <div class="section-head" style="margin-bottom: 10px">
            <div>
              <h2>快捷入口</h2>
              <p>高频运维动作直达。</p>
            </div>
          </div>

          <div class="dashboard-action-grid">
            <RouterLink class="button button-secondary" :to="{ name: 'clusters' }">集群管理</RouterLink>
            <RouterLink class="button button-secondary" :to="{ name: 'explorer' }">资源浏览</RouterLink>
            <RouterLink class="button button-secondary" :to="{ name: 'audit' }">审计中心</RouterLink>
            <RouterLink class="button button-secondary" :to="{ name: 'settings' }">系统设置</RouterLink>
          </div>

          <div class="pill-row" style="margin-top: 12px">
            <span
              v-for="feature in featureItems"
              :key="feature.label"
              class="pill"
              :class="feature.enabled ? 'dashboard-pill-enabled' : 'dashboard-pill-disabled'"
            >
              {{ feature.label }}: {{ feature.enabled ? 'on' : 'off' }}
            </span>
          </div>
        </article>
      </div>

      <article class="dashboard-panel">
        <div class="section-head" style="margin-bottom: 10px">
          <div>
            <h2>最近活动</h2>
            <p>来自审计事件流，帮助快速定位最近变更。</p>
          </div>
          <span class="tag">{{ summary?.recent_audit_count ?? 0 }} 条</span>
        </div>

        <div v-if="loading" class="empty-state">正在加载总览...</div>
        <div v-else-if="summary?.recent_events.length" class="event-list">
          <div
            v-for="event in summary.recent_events"
            :key="`${event.event_type}-${event.cluster__name || 'system'}`"
            class="event-item"
          >
            <h3>{{ event.event_type }}</h3>
            <div class="button-row">
              <StatusBadge :value="event.status" />
              <span class="muted">{{ event.cluster__name || 'system' }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">还没有审计事件，导入并操作一个集群后这里会开始更新。</div>
      </article>
    </section>
  </div>
</template>
