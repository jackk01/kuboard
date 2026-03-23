<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError } from '../lib/api'
import { useClusterStore } from '../stores/clusters'

const clusterStore = useClusterStore()
const feedback = ref('')
const errorMessage = ref('')
const editClusterId = ref<string | null>(null)
const importPanelOpen = ref(true)

const searchKeyword = ref('')
const statusFilter = ref<'all' | 'ready' | 'pending' | 'error'>('all')
const environmentFilter = ref<'all' | 'test' | 'dev' | 'uat' | 'prod'>('all')

const form = reactive({
  name: '',
  environment: 'dev',
  description: '',
  kubeconfig: '',
  server_override: '',
})

const editForm = reactive({
  name: '',
  environment: 'dev',
  description: '',
})

const detectedServerInfo = computed(() => {
  const text = form.kubeconfig.trim()
  if (!text) return null

  const serverMatch = text.match(/^\s*server:\s*(\S+)/m)
  if (!serverMatch) return null

  const serverUrl = serverMatch[1]
  try {
    const url = new URL(serverUrl)
    const hostname = url.hostname

    const ipv4Pattern = /^\d{1,3}(\.\d{1,3}){3}$/
    const ipv6Pattern = /^[\da-fA-F:]+$/
    const isIp = ipv4Pattern.test(hostname) || ipv6Pattern.test(hostname.replace(/^\[|\]$/g, ''))

    if (!isIp) {
      return {
        serverUrl,
        hostname,
        needsOverride: true,
      }
    }
  } catch {
    return null
  }

  return null
})

watch(detectedServerInfo, (info) => {
  if (!info?.needsOverride) {
    form.server_override = ''
  }
})

const statusSummary = computed(() => {
  const total = clusterStore.items.length
  const ready = clusterStore.items.filter((item) => item.status === 'ready').length
  const pending = clusterStore.items.filter((item) => item.status === 'pending').length
  const error = clusterStore.items.filter((item) => item.status === 'error').length
  return { total, ready, pending, error }
})

const filteredClusters = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  return [...clusterStore.items]
    .filter((cluster) => {
      if (statusFilter.value !== 'all' && cluster.status !== statusFilter.value) {
        return false
      }
      if (environmentFilter.value !== 'all' && cluster.environment !== environmentFilter.value) {
        return false
      }
      if (!keyword) {
        return true
      }
      const haystack = [
        cluster.name,
        cluster.server,
        cluster.description || '',
        cluster.default_context || '',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(keyword)
    })
    .sort((a, b) => {
      const ta = new Date(a.updated_at).getTime()
      const tb = new Date(b.updated_at).getTime()
      return tb - ta
    })
})

const environments = ['test', 'dev', 'uat', 'prod'] as const

onMounted(async () => {
  await clusterStore.fetchClusters()
})

function formatDateTime(value: string | null) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function runHealthCheck(clusterId: string) {
  errorMessage.value = ''
  feedback.value = ''
  try {
    await clusterStore.healthCheck(clusterId)
    feedback.value = '健康检查完成，状态已刷新。'
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '健康检查失败，请稍后重试。'
  }
}

async function runDiscovery(clusterId: string) {
  errorMessage.value = ''
  feedback.value = ''
  try {
    await clusterStore.syncDiscovery(clusterId)
    feedback.value = 'Discovery 同步完成。'
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = 'Discovery 同步失败，请稍后重试。'
  }
}

async function runBatchHealthCheck() {
  errorMessage.value = ''
  feedback.value = ''
  const targets = filteredClusters.value
  if (!targets.length) {
    feedback.value = '当前筛选结果为空，无需执行健康检查。'
    return
  }

  const results = await Promise.allSettled(targets.map((cluster) => clusterStore.healthCheck(cluster.id)))
  const failedCount = results.filter((item) => item.status === 'rejected').length
  if (failedCount > 0) {
    errorMessage.value = `批量健康检查完成：${targets.length - failedCount} 成功，${failedCount} 失败。`
    return
  }
  feedback.value = `批量健康检查完成：共 ${targets.length} 个集群。`
}

async function runBatchDiscovery() {
  errorMessage.value = ''
  feedback.value = ''
  const targets = filteredClusters.value
  if (!targets.length) {
    feedback.value = '当前筛选结果为空，无需执行 Discovery 同步。'
    return
  }

  const results = await Promise.allSettled(targets.map((cluster) => clusterStore.syncDiscovery(cluster.id)))
  const failedCount = results.filter((item) => item.status === 'rejected').length
  if (failedCount > 0) {
    errorMessage.value = `批量 Discovery 同步完成：${targets.length - failedCount} 成功，${failedCount} 失败。`
    return
  }
  feedback.value = `批量 Discovery 同步完成：共 ${targets.length} 个集群。`
}

function handleShellCommand(event: Event) {
  const customEvent = event as CustomEvent<{ action?: string }>
  const action = customEvent.detail?.action
  if (action === 'clusters.health_all') {
    void runBatchHealthCheck()
    return
  }
  if (action === 'clusters.discovery_all') {
    void runBatchDiscovery()
  }
}

onMounted(() => {
  window.addEventListener('kuboard:command', handleShellCommand as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('kuboard:command', handleShellCommand as EventListener)
})

async function importCluster() {
  errorMessage.value = ''
  feedback.value = ''

  if (detectedServerInfo.value?.needsOverride && !form.server_override.trim()) {
    errorMessage.value = `kubeconfig 中的 server 地址使用了主机名 "${detectedServerInfo.value.hostname}"，请填写对应 IP。`
    return
  }

  try {
    const payload: Record<string, string> = {
      name: form.name,
      environment: form.environment,
      description: form.description,
      kubeconfig: form.kubeconfig,
    }
    if (form.server_override.trim()) {
      payload.server_override = form.server_override.trim()
    }

    const cluster = await clusterStore.importCluster(payload as any)
    feedback.value = `集群 ${cluster.name} 已导入。`
    form.name = ''
    form.environment = 'dev'
    form.description = ''
    form.kubeconfig = ''
    form.server_override = ''
    importPanelOpen.value = false
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '导入失败，请检查后端日志。'
  }
}

function startEdit(cluster: {
  id: string
  name: string
  environment: string
  description: string
}) {
  editClusterId.value = cluster.id
  editForm.name = cluster.name
  editForm.environment = cluster.environment
  editForm.description = cluster.description ?? ''
  feedback.value = ''
  errorMessage.value = ''
}

function cancelEdit() {
  editClusterId.value = null
}

async function saveEdit(clusterId: string) {
  errorMessage.value = ''
  feedback.value = ''
  try {
    const updated = await clusterStore.updateCluster(clusterId, {
      name: editForm.name,
      environment: editForm.environment,
      description: editForm.description,
    })
    feedback.value = `集群 ${updated.name} 的信息已更新。`
    editClusterId.value = null
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '更新失败，请稍后重试。'
  }
}

const deleteDialogVisible = ref(false)
const pendingDeleteCluster = ref<{ id: string; name: string } | null>(null)

function removeCluster(cluster: { id: string; name: string }) {
  errorMessage.value = ''
  feedback.value = ''
  pendingDeleteCluster.value = cluster
  deleteDialogVisible.value = true
}

function cancelDelete() {
  deleteDialogVisible.value = false
  pendingDeleteCluster.value = null
}

async function confirmDelete() {
  const cluster = pendingDeleteCluster.value
  if (!cluster) return

  deleteDialogVisible.value = false
  pendingDeleteCluster.value = null

  try {
    await clusterStore.deleteCluster(cluster.id)
    feedback.value = `集群 ${cluster.name} 已删除。`
    if (editClusterId.value === cluster.id) {
      editClusterId.value = null
    }
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '删除失败，请稍后重试。'
  }
}
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel cluster-hero-panel">
      <div class="section-head">
        <div>
          <h2 class="page-title">集群控制台</h2>
          <p>参考 Kuboard 面板风格重构：高密度总览 + 快速操作 + 分层详情。</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" @click="clusterStore.fetchClusters">刷新列表</button>
          <button class="button button-primary" :disabled="clusterStore.loading" @click="runBatchHealthCheck">批量健康检查</button>
        </div>
      </div>

      <div class="cluster-summary-grid">
        <article class="cluster-summary-card">
          <span>已纳管</span>
          <strong>{{ statusSummary.total }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>Ready</span>
          <strong class="is-ready">{{ statusSummary.ready }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>Pending</span>
          <strong class="is-pending">{{ statusSummary.pending }}</strong>
        </article>
        <article class="cluster-summary-card">
          <span>Error</span>
          <strong class="is-error">{{ statusSummary.error }}</strong>
        </article>
      </div>
    </section>

    <section class="surface-card cluster-workspace">
      <div class="cluster-toolbar">
        <input
          v-model="searchKeyword"
          class="cluster-search"
          placeholder="按名称 / server / context 搜索"
        />
        <select v-model="statusFilter" class="cluster-filter">
          <option value="all">全部状态</option>
          <option value="ready">Ready</option>
          <option value="pending">Pending</option>
          <option value="error">Error</option>
        </select>
        <select v-model="environmentFilter" class="cluster-filter">
          <option value="all">全部环境</option>
          <option v-for="env in environments" :key="env" :value="env">{{ env }}</option>
        </select>
        <button class="button button-secondary" @click="importPanelOpen = !importPanelOpen">
          {{ importPanelOpen ? '收起导入面板' : '展开导入面板' }}
        </button>
      </div>

      <div v-if="feedback" class="helper-text" style="margin-top: 8px">{{ feedback }}</div>
      <div v-if="errorMessage" class="error-text" style="margin-top: 8px">{{ errorMessage }}</div>

      <div v-if="clusterStore.loading" class="empty-state" style="margin-top: 14px">正在加载集群列表...</div>
      <div v-else-if="filteredClusters.length" class="cluster-overview-table-wrap">
        <table class="table cluster-overview-table">
          <thead>
            <tr>
              <th>集群</th>
              <th>状态</th>
              <th>环境</th>
              <th>版本 / Context</th>
              <th>健康信息</th>
              <th>最后检查</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cluster in filteredClusters" :key="cluster.id">
              <td>
                <div class="cluster-name-cell">
                  <strong>{{ cluster.name }}</strong>
                  <span>{{ cluster.server }}</span>
                  <span class="muted" v-if="cluster.description">{{ cluster.description }}</span>
                </div>
              </td>
              <td>
                <div class="cluster-status-pair">
                  <StatusBadge :value="cluster.status" />
                  <StatusBadge :value="cluster.health?.status || cluster.health_state" />
                </div>
              </td>
              <td><span class="tag">{{ cluster.environment }}</span></td>
              <td>
                <div class="cluster-meta-cell">
                  <span>{{ cluster.kube_version || '--' }}</span>
                  <span class="muted">{{ cluster.default_context }}</span>
                </div>
              </td>
              <td>
                <div class="cluster-health-cell">{{ cluster.health?.message || '等待健康探测' }}</div>
                <div class="helper-text" style="margin-top: 4px">
                  API Groups: {{ cluster.capability?.discovered_api_groups?.length || 0 }}
                </div>
              </td>
              <td>
                <div class="cluster-meta-cell">
                  <span>{{ formatDateTime(cluster.health?.last_checked_at || null) }}</span>
                  <span class="muted">更新 {{ formatDateTime(cluster.updated_at) }}</span>
                </div>
              </td>
              <td>
                <div class="button-row">
                  <button
                    class="button button-secondary"
                    :disabled="clusterStore.checkingIds.includes(cluster.id)"
                    @click="runHealthCheck(cluster.id)"
                  >
                    {{ clusterStore.checkingIds.includes(cluster.id) ? '检查中...' : '健康检查' }}
                  </button>
                  <button
                    class="button button-secondary"
                    :disabled="clusterStore.discoveringIds.includes(cluster.id)"
                    @click="runDiscovery(cluster.id)"
                  >
                    {{ clusterStore.discoveringIds.includes(cluster.id) ? '同步中...' : '同步 Discovery' }}
                  </button>
                  <button class="button button-secondary" @click="startEdit(cluster)">编辑</button>
                  <button
                    class="button button-danger"
                    :disabled="clusterStore.deletingIds.includes(cluster.id)"
                    @click="removeCluster(cluster)"
                  >
                    {{ clusterStore.deletingIds.includes(cluster.id) ? '删除中...' : '删除' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state" style="margin-top: 14px">当前筛选条件下没有集群。</div>

      <div v-if="editClusterId" class="cluster-edit-panel">
        <div class="section-head" style="margin-bottom: 12px">
          <div>
            <h2>编辑集群</h2>
          </div>
          <button class="button button-secondary" @click="cancelEdit">关闭</button>
        </div>
        <div class="triple-grid">
          <label class="field-label">
            集群名称
            <input v-model="editForm.name" />
          </label>
          <label class="field-label">
            环境
            <select v-model="editForm.environment">
              <option value="test">test</option>
              <option value="dev">dev</option>
              <option value="uat">uat</option>
              <option value="prod">prod</option>
            </select>
          </label>
          <label class="field-label">
            描述
            <input v-model="editForm.description" />
          </label>
        </div>
        <div class="button-row" style="margin-top: 12px">
          <button class="button button-primary" @click="saveEdit(editClusterId)">保存修改</button>
        </div>
      </div>

      <div v-if="importPanelOpen" class="cluster-import-panel">
        <div class="section-head" style="margin-bottom: 12px">
          <div>
            <h2>导入 Kubernetes 集群</h2>
            <p>支持 kubeconfig 安全校验、自动健康检查与自动 Discovery。</p>
          </div>
        </div>

        <div class="dual-grid">
          <div class="form-grid">
            <label class="field-label">
              集群名称
              <input v-model="form.name" placeholder="例如：prod-cn-hangzhou" />
            </label>
            <label class="field-label">
              环境
              <select v-model="form.environment">
                <option value="test">test</option>
                <option value="dev">dev</option>
                <option value="uat">uat</option>
                <option value="prod">prod</option>
              </select>
            </label>
            <label class="field-label">
              描述
              <input v-model="form.description" placeholder="例如：核心生产环境集群" />
            </label>
          </div>

          <label class="field-label">
            kubeconfig
            <textarea
              v-model="form.kubeconfig"
              placeholder="粘贴 kubeconfig 内容。"
            />
          </label>
        </div>

        <div v-if="detectedServerInfo?.needsOverride" class="helper-text" style="margin-top: 10px">
          检测到主机名 <code>{{ detectedServerInfo.hostname }}</code>，请填写可访问 IP。
        </div>
        <label v-if="detectedServerInfo?.needsOverride" class="field-label" style="margin-top: 10px">
          API Server 实际 IP 地址
          <input v-model="form.server_override" placeholder="例如：192.168.1.100" />
        </label>

        <div class="button-row" style="margin-top: 14px">
          <button class="button button-primary" :disabled="clusterStore.saving" @click="importCluster">
            {{ clusterStore.saving ? '导入中...' : '导入集群' }}
          </button>
        </div>
      </div>
    </section>

    <ConfirmDialog
      :visible="deleteDialogVisible"
      title="删除集群"
      :message="pendingDeleteCluster ? `确认删除集群 ${pendingDeleteCluster.name} 吗？该操作无法撤销。` : ''"
      confirm-text="删除"
      cancel-text="取消"
      :danger="true"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>
