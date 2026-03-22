<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError } from '../lib/api'
import { useClusterStore } from '../stores/clusters'

const clusterStore = useClusterStore()
const feedback = ref('')
const errorMessage = ref('')
const editClusterId = ref<string | null>(null)

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

/**
 * 从 kubeconfig 文本中提取 server URL，并判断其主机名是否为非 IP 地址。
 * 如果 server URL 使用主机名（如 https://master:6443），返回提取到的信息。
 */
const detectedServerInfo = computed(() => {
  const text = form.kubeconfig.trim()
  if (!text) return null

  // 简易正则提取 server: 行
  const serverMatch = text.match(/^\s*server:\s*(\S+)/m)
  if (!serverMatch) return null

  const serverUrl = serverMatch[1]
  try {
    const url = new URL(serverUrl)
    const hostname = url.hostname

    // 检查是否为 IP 地址（IPv4 或 IPv6）
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
    // URL 解析失败，忽略
  }

  return null
})

// 当检测到不需要 override 时，清空 server_override
watch(detectedServerInfo, (info) => {
  if (!info || !info.needsOverride) {
    form.server_override = ''
  }
})

onMounted(async () => {
  await clusterStore.fetchClusters()
})

async function importCluster() {
  errorMessage.value = ''
  feedback.value = ''

  // 如果检测到主机名但用户没有填写 IP，给出提示
  if (detectedServerInfo.value?.needsOverride && !form.server_override.trim()) {
    errorMessage.value = `kubeconfig 中的 server 地址使用了主机名 "${detectedServerInfo.value.hostname}"，请在下方填写该主机名对应的 IP 地址。`
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
    feedback.value = `集群 ${cluster.name} 已导入，当前上下文为 ${cluster.default_context}。`
    form.name = ''
    form.environment = 'dev'
    form.description = ''
    form.kubeconfig = ''
    form.server_override = ''
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

// 删除确认对话框状态
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
    <section class="surface-card">
      <div class="section-head">
        <div>
          <h2>导入 Kubernetes 集群</h2>
          <p>当前版本会先做 kubeconfig 结构校验，并默认拒绝 exec 与 insecure-skip-tls-verify。</p>
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
            placeholder="粘贴 kubeconfig 内容。当前初始化版会先完成安全校验和加密存储。"
          />
        </label>
      </div>

      <div v-if="detectedServerInfo?.needsOverride" class="server-override-section" style="margin-top: 16px">
        <div class="helper-text" style="margin-bottom: 8px; color: var(--color-warning, #e6a23c)">
          ⚠ 检测到 kubeconfig 中的 server 地址使用了主机名
          <code>{{ detectedServerInfo.hostname }}</code>（{{ detectedServerInfo.serverUrl }}），
          请填写该主机名对应的实际 IP 地址，以确保 Kuboard 能正确连接到集群。
        </div>
        <label class="field-label">
          API Server 实际 IP 地址
          <input
            v-model="form.server_override"
            placeholder="例如：192.168.1.100"
          />
        </label>
      </div>

      <div v-if="feedback" class="helper-text" style="margin-top: 12px">{{ feedback }}</div>
      <div v-if="errorMessage" class="error-text" style="margin-top: 12px">{{ errorMessage }}</div>

      <div class="button-row" style="margin-top: 18px">
        <button class="button button-primary" :disabled="clusterStore.saving" @click="importCluster">
          {{ clusterStore.saving ? '导入中...' : '导入集群' }}
        </button>
      </div>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <h2>已纳管集群</h2>
          <p>这里展示已经进入控制平面的集群元数据。真正的资源内容仍以 Kubernetes API 为准。</p>
        </div>
      </div>

      <div v-if="clusterStore.loading" class="helper-text">正在加载集群列表...</div>
      <div v-else-if="clusterStore.items.length" class="cluster-card-grid">
        <article v-for="cluster in clusterStore.items" :key="cluster.id" class="cluster-card">
          <div class="cluster-card-head">
            <div>
              <h3 style="margin: 0">{{ cluster.name }}</h3>
              <div class="muted" style="margin-top: 6px">{{ cluster.server }}</div>
            </div>
            <StatusBadge :value="cluster.status" />
          </div>

          <div class="button-row" style="margin-top: 14px">
            <span class="tag">{{ cluster.environment }}</span>
            <StatusBadge :value="cluster.health?.status || cluster.health_state" />
          </div>

          <div class="mini-kv" style="margin-top: 16px">
            <div>
              <span>默认 Context</span>
              <strong>{{ cluster.default_context }}</strong>
            </div>
            <div>
              <span>健康状态</span>
              <strong>{{ cluster.health?.message || '等待进一步探测' }}</strong>
            </div>
            <div>
              <span>发现的 API Group</span>
              <strong>{{ cluster.capability?.discovered_api_groups.join(', ') }}</strong>
            </div>
            <div>
              <span>Impersonation</span>
              <strong>{{ cluster.capability?.supports_impersonation ? 'enabled' : 'disabled' }}</strong>
            </div>
          </div>

          <div class="button-row" style="margin-top: 16px">
            <button class="button button-secondary" @click="clusterStore.healthCheck(cluster.id)">
              重新健康检查
            </button>
            <button class="button button-secondary" @click="startEdit(cluster)">
              编辑
            </button>
            <button
              class="button button-danger"
              :disabled="clusterStore.deletingIds.includes(cluster.id)"
              @click="removeCluster(cluster)"
            >
              {{ clusterStore.deletingIds.includes(cluster.id) ? '删除中...' : '删除' }}
            </button>
          </div>

          <div v-if="editClusterId === cluster.id" class="cluster-edit-form">
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
            <div class="button-row">
              <button
                class="button button-primary"
                :disabled="clusterStore.updatingIds.includes(cluster.id)"
                @click="saveEdit(cluster.id)"
              >
                {{ clusterStore.updatingIds.includes(cluster.id) ? '保存中...' : '保存修改' }}
              </button>
              <button class="button button-secondary" @click="cancelEdit">取消</button>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-state">还没有集群，先导入第一个 kubeconfig 开始吧。</div>
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
