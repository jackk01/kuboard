<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError } from '../lib/api'
import { useClusterStore } from '../stores/clusters'

const clusterStore = useClusterStore()
const feedback = ref('')
const errorMessage = ref('')
const editClusterId = ref<string | null>(null)
const editLoading = ref(false)
const importPanelOpen = ref(true)
const importMode = ref<'paste' | 'upload'>('paste')
const uploadFileName = ref('')
const loadingLocalKubeconfig = ref(false)
const localKubeconfigMeta = ref<{
  source_path: string
  current_context: string
  server: string
  cluster_count: number
} | null>(null)

const searchKeyword = ref('')
const statusFilter = ref<'all' | 'ready' | 'pending' | 'error'>('all')
const environmentFilter = ref<'all' | 'test' | 'dev' | 'uat' | 'prod'>('all')

const form = reactive({
  name: '',
  environment: 'dev',
  description: '',
  kubeconfig: '',
})

const editForm = reactive({
  name: '',
  environment: 'dev',
  description: '',
  kubeconfig: '',
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

function handleShellCommand(event: Event) {
  const customEvent = event as CustomEvent<{ action?: string }>
  const action = customEvent.detail?.action
  if (action === 'clusters.open_import') {
    importPanelOpen.value = true
    return
  }
  if (action === 'clusters.health_all') {
    void runBatchHealthCheck()
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

  try {
    const payload = {
      name: form.name,
      environment: form.environment,
      description: form.description,
      kubeconfig: form.kubeconfig,
    }

    const cluster = await clusterStore.importCluster(payload)
    feedback.value = `集群 ${cluster.name} 已导入。`
    form.name = ''
    form.environment = 'dev'
    form.description = ''
    form.kubeconfig = ''
    uploadFileName.value = ''
    importMode.value = 'paste'
    importPanelOpen.value = false
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '导入失败，请检查后端日志。'
  }
}

async function fillFromLocalKubeconfig() {
  errorMessage.value = ''
  feedback.value = ''
  loadingLocalKubeconfig.value = true

  try {
    const payload = await clusterStore.fetchLocalKubeconfig()
    form.kubeconfig = payload.kubeconfig
    if (!form.name.trim()) {
      form.name = payload.current_context || 'local-kubeconfig'
    }
    localKubeconfigMeta.value = {
      source_path: payload.source_path,
      current_context: payload.current_context,
      server: payload.server,
      cluster_count: payload.cluster_count,
    }
    feedback.value = `已从 ${payload.source_path} 读取 kubeconfig。`
  } catch (error) {
    localKubeconfigMeta.value = null
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '读取本地 kubeconfig 失败，请检查后端日志。'
  } finally {
    loadingLocalKubeconfig.value = false
  }
}

function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploadFileName.value = file.name
  errorMessage.value = ''
  feedback.value = ''

  const reader = new FileReader()
  reader.onload = (e) => {
    const content = e.target?.result as string
    if (!content || !content.trim()) {
      errorMessage.value = '文件内容为空，请检查文件是否正确。'
      return
    }
    form.kubeconfig = content
    feedback.value = `已从文件 "${file.name}" 读取 kubeconfig 内容。`
  }
  reader.onerror = () => {
    errorMessage.value = '文件读取失败，请重试。'
  }
  reader.readAsText(file)
}

function triggerFileInput() {
  const input = document.getElementById('kubeconfig-file-input') as HTMLInputElement
  input?.click()
}

function clearUploadedFile() {
  uploadFileName.value = ''
  form.kubeconfig = ''
  const input = document.getElementById('kubeconfig-file-input') as HTMLInputElement
  if (input) input.value = ''
}

async function startEdit(cluster: {
  id: string
  name: string
  environment: string
  description: string
}) {
  editClusterId.value = cluster.id
  editForm.name = cluster.name
  editForm.environment = cluster.environment
  editForm.description = cluster.description ?? ''
  editForm.kubeconfig = ''
  feedback.value = ''
  errorMessage.value = ''

  editLoading.value = true
  try {
    const detail = await clusterStore.fetchCluster(cluster.id)
    editForm.name = detail.name
    editForm.environment = detail.environment
    editForm.description = detail.description ?? ''
    editForm.kubeconfig = detail.kubeconfig
  } catch (error) {
    editClusterId.value = null
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '读取集群详情失败，请稍后重试。'
  } finally {
    editLoading.value = false
  }
}

function cancelEdit() {
  editClusterId.value = null
  editLoading.value = false
}

async function saveEdit(clusterId: string) {
  errorMessage.value = ''
  feedback.value = ''
  try {
    const updated = await clusterStore.updateCluster(clusterId, {
      name: editForm.name,
      environment: editForm.environment,
      description: editForm.description,
      kubeconfig: editForm.kubeconfig,
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
  <div class="page-grid page-grid-fill">
    <section class="hero-panel cluster-hero-panel">
      <div class="section-head">
        <div>
          <h2 class="page-title">集群控制台</h2>
          <p>Kuboard 风格布局：状态总览、快速筛选、批量运维与导入。</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" @click="clusterStore.fetchClusters">刷新列表</button>
          <button class="button button-primary" :disabled="clusterStore.loading" @click="runBatchHealthCheck">批量检查</button>
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
          {{ importPanelOpen ? '隐藏导入面板' : '显示导入面板' }}
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
                    @click="startEdit(cluster)"
                  >编辑</button>
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
            <p>支持同时更新名称、环境、描述以及已导入的 kubeconfig 内容。</p>
          </div>
          <button class="button button-secondary" @click="cancelEdit">关闭</button>
        </div>
        <div v-if="editLoading" class="empty-state">正在加载集群详情...</div>
        <template v-else>
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
        <label class="field-label" style="margin-top: 12px">
          kubeconfig 内容
          <textarea
            v-model="editForm.kubeconfig"
            placeholder="在此编辑当前集群的 kubeconfig YAML 内容..."
            class="kubeconfig-textarea"
          />
        </label>
        <div class="helper-text" style="margin-top: 8px">
          保存后会用新的 kubeconfig 重新更新集群 server、默认 context，并触发一次健康检查。
        </div>
        <div class="button-row" style="margin-top: 12px">
          <button class="button button-primary" :disabled="!editForm.kubeconfig.trim()" @click="saveEdit(editClusterId)">保存修改</button>
        </div>
        </template>
      </div>

      <div v-if="importPanelOpen" class="cluster-import-panel">
        <div class="section-head" style="margin-bottom: 16px">
          <div>
            <h2>导入 Kubernetes 集群</h2>
            <p>选择一种方式提供 kubeconfig 以导入集群。</p>
          </div>
          <button class="button button-secondary" @click="importPanelOpen = false">关闭</button>
        </div>

        <!-- 基本信息 -->
        <div class="import-basic-fields">
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

        <!-- Tab 切换 -->
        <div class="import-tabs">
          <button
            class="import-tab"
            :class="{ 'import-tab-active': importMode === 'paste' }"
            @click="importMode = 'paste'"
          >
            <span class="import-tab-icon">📋</span>
            粘贴 kubeconfig 内容
          </button>
          <button
            class="import-tab"
            :class="{ 'import-tab-active': importMode === 'upload' }"
            @click="importMode = 'upload'"
          >
            <span class="import-tab-icon">📁</span>
            上传 kubeconfig 文件
          </button>
        </div>

        <!-- 粘贴 kubeconfig 内容 -->
        <div v-if="importMode === 'paste'" class="import-tab-content">
          <div class="import-tab-header">
            <p class="helper-text">将 kubeconfig 文件内容复制并粘贴到下方文本框中，也可以从服务器 ~/.kube/config 自动读取。</p>
            <button class="button button-secondary" :disabled="loadingLocalKubeconfig" @click="fillFromLocalKubeconfig">
              {{ loadingLocalKubeconfig ? '读取中...' : '从 ~/.kube/config 读取' }}
            </button>
          </div>

          <div v-if="localKubeconfigMeta" class="import-meta-bar">
            来源：<code>{{ localKubeconfigMeta.source_path }}</code>
            · Context：<code>{{ localKubeconfigMeta.current_context }}</code>
            · Server：<code>{{ localKubeconfigMeta.server }}</code>
            · Clusters：{{ localKubeconfigMeta.cluster_count }}
          </div>

          <label class="field-label">
            kubeconfig 内容
            <textarea
              v-model="form.kubeconfig"
              placeholder="在此粘贴 kubeconfig YAML 内容..."
              class="kubeconfig-textarea"
            />
          </label>
        </div>

        <!-- 上传 kubeconfig 文件 -->
        <div v-if="importMode === 'upload'" class="import-tab-content">
          <p class="helper-text" style="margin-bottom: 12px">
            选择本地的 kubeconfig 文件进行上传，系统将自动解析文件内容。
          </p>

          <input
            id="kubeconfig-file-input"
            type="file"
            accept=".yaml,.yml,.conf,.config,.txt,application/x-yaml,text/yaml,text/plain"
            style="display: none"
            @change="handleFileUpload"
          />

          <div class="import-upload-zone" @click="triggerFileInput">
            <div v-if="!uploadFileName" class="import-upload-placeholder">
              <span class="import-upload-icon">⬆️</span>
              <strong>点击选择 kubeconfig 文件</strong>
              <span class="helper-text">支持 .yaml / .yml / .conf / .config / .txt 格式</span>
            </div>
            <div v-else class="import-upload-result">
              <span class="import-upload-icon">✅</span>
              <div>
                <strong>{{ uploadFileName }}</strong>
                <span class="helper-text">文件已读取，内容已就绪</span>
              </div>
              <button class="button button-secondary" style="margin-left: auto; padding: 6px 12px" @click.stop="clearUploadedFile">
                清除
              </button>
            </div>
          </div>

          <div v-if="form.kubeconfig && uploadFileName" class="import-preview">
            <label class="field-label">
              文件内容预览
              <textarea
                :value="form.kubeconfig"
                readonly
                class="kubeconfig-textarea kubeconfig-preview"
              />
            </label>
          </div>
        </div>

        <div class="button-row" style="margin-top: 16px">
          <button class="button button-primary" :disabled="clusterStore.saving || !form.kubeconfig.trim()" @click="importCluster">
            {{ clusterStore.saving ? '导入中...' : '导入集群' }}
          </button>
          <span v-if="!form.kubeconfig.trim()" class="helper-text">请先提供 kubeconfig 内容</span>
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
