<script setup lang="ts">
import { onMounted, ref } from 'vue'

import StatCard from '../components/StatCard.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { apiRequest } from '../lib/api'
import type { DashboardSummary } from '../types'

const loading = ref(true)
const summary = ref<DashboardSummary | null>(null)

onMounted(async () => {
  try {
    summary.value = await apiRequest<DashboardSummary>('/api/v1/dashboard/summary')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel">
      <div class="section-head">
        <div>
          <div class="eyebrow" style="color: var(--kb-primary-deep)">Platform Overview</div>
          <h2 class="page-title">多集群控制平面已经初始化</h2>
          <p class="page-description">
            当前版本已经接通登录、集群导入、审计、轻量控制平面元数据存储和 Vue 前端壳层。
          </p>
        </div>
        <StatusBadge :value="(summary?.clusters.ready ?? 0) > 0 ? 'ready' : 'unknown'" />
      </div>

      <div class="stat-grid">
        <StatCard
          label="已纳管集群"
          :value="summary?.clusters.total ?? '--'"
          caption="所有已导入的 Kubernetes 集群总数"
        />
        <StatCard
          label="Ready 集群"
          :value="summary?.clusters.ready ?? '--'"
          caption="本地校验通过并已进入可用状态"
        />
        <StatCard
          label="审计事件"
          :value="summary?.recent_audit_count ?? '--'"
          caption="当前数据库中的审计事件数量"
        />
        <StatCard
          label="最近事件"
          :value="summary?.recent_events.length ?? '--'"
          caption="最近写入并展示在下方列表的审计事件数"
        />
      </div>
    </section>

    <section class="page-grid">
      <article class="surface-card">
        <div class="section-head">
          <div>
            <h2>最近活动</h2>
            <p>这里聚合了最近写入的审计事件，后续可以继续扩展到日志和告警。</p>
          </div>
        </div>

        <div v-if="loading" class="helper-text">正在加载摘要...</div>
        <div v-else-if="summary?.recent_events.length" class="event-list">
          <div v-for="event in summary.recent_events" :key="`${event.event_type}-${event.cluster__name}`" class="event-item">
            <h3>{{ event.event_type }}</h3>
            <div class="button-row">
              <StatusBadge :value="event.status" />
              <span class="muted">{{ event.cluster__name || 'system' }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">还没有审计事件，导入一个集群后这里就会开始有数据。</div>
      </article>
    </section>
  </div>
</template>
