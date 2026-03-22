<script setup lang="ts">
import { onMounted, ref } from 'vue'

import StatusBadge from '../components/StatusBadge.vue'
import { apiRequest } from '../lib/api'
import type { AuditEvent } from '../types'

const loading = ref(true)
const events = ref<AuditEvent[]>([])

onMounted(async () => {
  try {
    events.value = await apiRequest<AuditEvent[]>('/api/v1/audit/events?limit=20')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page-grid">
    <section class="surface-card">
      <div class="section-head">
        <div>
          <h2>审计中心</h2>
          <p>初始化版本已经对登录、登出、集群导入和健康检查做了审计落库。</p>
        </div>
      </div>

      <div v-if="loading" class="helper-text">正在加载审计事件...</div>
      <table v-else-if="events.length" class="table">
        <thead>
          <tr>
            <th>事件</th>
            <th>操作者</th>
            <th>目标集群</th>
            <th>状态</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="event in events" :key="event.id">
            <td>
              <strong>{{ event.event_type }}</strong>
              <div class="muted">{{ event.request_id || 'no-request-id' }}</div>
            </td>
            <td>{{ event.actor_display || event.actor_email || 'system' }}</td>
            <td>{{ event.cluster_name || '--' }}</td>
            <td><StatusBadge :value="event.status" /></td>
            <td>{{ new Date(event.created_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">还没有审计数据，先登录或导入一个集群试试看。</div>
    </section>
  </div>
</template>

