<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import { useSessionStore } from '../stores/session'
import type {
  AdminUserRecord,
  AdminUserGroupRecord,
  ClusterImpersonationConfig,
  ImpersonationPreview,
  SubjectMapping,
} from '../types'

const clusterStore = useClusterStore()
const sessionStore = useSessionStore()

const selectedClusterId = ref('')
const impersonationConfig = ref<ClusterImpersonationConfig | null>(null)
const preview = ref<ImpersonationPreview | null>(null)
const mappings = ref<SubjectMapping[]>([])
const users = ref<AdminUserRecord[]>([])
const groups = ref<AdminUserGroupRecord[]>([])
const previewError = ref('')
const mappingError = ref('')
const feedback = ref('')
const userError = ref('')
const userFeedback = ref('')
const groupError = ref('')
const groupFeedback = ref('')
const loadingPreview = ref(false)
const loadingMappings = ref(false)
const loadingUsers = ref(false)
const loadingGroups = ref(false)
const saving = ref(false)
const savingUser = ref(false)
const savingGroup = ref(false)
const editingMappingId = ref<number | null>(null)
const editingUserId = ref<number | null>(null)
const editingGroupId = ref<number | null>(null)

const form = reactive({
  source_type: 'user',
  source_identifier: '',
  kubernetes_username: '',
  kubernetes_groups_text: '',
  cluster: '',
  is_enabled: true,
})

const userForm = reactive({
  email: '',
  display_name: '',
  password: '',
  is_staff: false,
  is_superuser: false,
  password_needs_reset: true,
})

const groupForm = reactive({
  name: '',
  description: '',
  member_emails_text: '',
})

const isAdmin = computed(
  () => Boolean(sessionStore.currentUser?.is_staff || sessionStore.currentUser?.is_superuser),
)

const availableClusters = computed(() => clusterStore.items)

const visibleMappings = computed(() =>
  mappings.value.filter((mapping) => !mapping.cluster || mapping.cluster === selectedClusterId.value),
)

function resetForm() {
  editingMappingId.value = null
  form.source_type = 'user'
  form.source_identifier = ''
  form.kubernetes_username = ''
  form.kubernetes_groups_text = ''
  form.cluster = selectedClusterId.value
  form.is_enabled = true
}

function resetUserForm() {
  editingUserId.value = null
  userForm.email = ''
  userForm.display_name = ''
  userForm.password = ''
  userForm.is_staff = false
  userForm.is_superuser = false
  userForm.password_needs_reset = true
}

function resetGroupForm() {
  editingGroupId.value = null
  groupForm.name = ''
  groupForm.description = ''
  groupForm.member_emails_text = ''
}

async function loadPreview() {
  if (!selectedClusterId.value) {
    return
  }

  loadingPreview.value = true
  previewError.value = ''

  try {
    preview.value = await apiRequest<ImpersonationPreview>(
      `/api/v1/rbac/me?cluster_id=${encodeURIComponent(selectedClusterId.value)}`,
    )
  } catch (error) {
    preview.value = null
    if (error instanceof ApiError) {
      previewError.value = error.message
    } else {
      previewError.value = '身份预览读取失败。'
    }
  } finally {
    loadingPreview.value = false
  }
}

async function loadImpersonationConfig() {
  if (!selectedClusterId.value || !isAdmin.value) {
    return
  }

  try {
    impersonationConfig.value = await apiRequest<ClusterImpersonationConfig>(
      `/api/v1/rbac/clusters/${selectedClusterId.value}/impersonation`,
    )
  } catch {
    impersonationConfig.value = null
  }
}

async function loadMappings() {
  if (!isAdmin.value) {
    return
  }

  loadingMappings.value = true
  mappingError.value = ''

  try {
    mappings.value = await apiRequest<SubjectMapping[]>('/api/v1/rbac/mappings')
  } catch (error) {
    mappings.value = []
    if (error instanceof ApiError) {
      mappingError.value = error.message
    } else {
      mappingError.value = '映射列表读取失败。'
    }
  } finally {
    loadingMappings.value = false
  }
}

async function loadUsers() {
  if (!isAdmin.value) {
    return
  }

  loadingUsers.value = true
  userError.value = ''

  try {
    users.value = await apiRequest<AdminUserRecord[]>('/api/v1/users')
  } catch (error) {
    users.value = []
    if (error instanceof ApiError) {
      userError.value = error.message
    } else {
      userError.value = '用户列表读取失败。'
    }
  } finally {
    loadingUsers.value = false
  }
}

async function loadGroups() {
  if (!isAdmin.value) {
    return
  }

  loadingGroups.value = true
  groupError.value = ''

  try {
    groups.value = await apiRequest<AdminUserGroupRecord[]>('/api/v1/user-groups')
  } catch (error) {
    groups.value = []
    if (error instanceof ApiError) {
      groupError.value = error.message
    } else {
      groupError.value = '用户组列表读取失败。'
    }
  } finally {
    loadingGroups.value = false
  }
}

async function toggleImpersonation(enabled: boolean) {
  if (!selectedClusterId.value || !isAdmin.value) {
    return
  }

  saving.value = true
  feedback.value = ''
  mappingError.value = ''

  try {
    impersonationConfig.value = await apiRequest<ClusterImpersonationConfig>(
      `/api/v1/rbac/clusters/${selectedClusterId.value}/impersonation`,
      {
        method: 'PATCH',
        body: JSON.stringify({ supports_impersonation: enabled }),
      },
    )
    await clusterStore.fetchClusters()
    await loadPreview()
    feedback.value = enabled
      ? '该集群已开启 impersonation，后续资源访问会按当前登录用户映射到 Kubernetes Subject。'
      : '该集群已关闭 impersonation，资源访问会恢复使用控制平面凭据直连。'
  } catch (error) {
    if (error instanceof ApiError) {
      mappingError.value = error.message
    } else {
      mappingError.value = '集群 impersonation 开关更新失败。'
    }
  } finally {
    saving.value = false
  }
}

function editMapping(mapping: SubjectMapping) {
  editingMappingId.value = mapping.id
  form.source_type = mapping.source_type
  form.source_identifier = mapping.source_identifier
  form.kubernetes_username = mapping.kubernetes_username
  form.kubernetes_groups_text = mapping.kubernetes_groups.join(', ')
  form.cluster = mapping.cluster || ''
  form.is_enabled = mapping.is_enabled
}

async function saveMapping() {
  if (!isAdmin.value) {
    return
  }

  saving.value = true
  feedback.value = ''
  mappingError.value = ''

  const payload = {
    source_type: form.source_type,
    source_identifier: form.source_identifier.trim(),
    kubernetes_username: form.kubernetes_username.trim(),
    kubernetes_groups: form.kubernetes_groups_text
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    cluster: form.cluster || null,
    is_enabled: form.is_enabled,
  }

  try {
    if (editingMappingId.value) {
      await apiRequest<SubjectMapping>(`/api/v1/rbac/mappings/${editingMappingId.value}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      feedback.value = '映射已更新。'
    } else {
      await apiRequest<SubjectMapping>('/api/v1/rbac/mappings', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      feedback.value = '映射已创建。'
    }

    await loadMappings()
    await loadPreview()
    resetForm()
  } catch (error) {
    if (error instanceof ApiError) {
      mappingError.value = error.message
    } else {
      mappingError.value = '映射保存失败。'
    }
  } finally {
    saving.value = false
  }
}

async function deleteMapping(mapping: SubjectMapping) {
  if (!isAdmin.value) {
    return
  }
  const confirmed = window.confirm(`确认删除映射 ${mapping.source_identifier} 吗？`)
  if (!confirmed) {
    return
  }

  saving.value = true
  feedback.value = ''
  mappingError.value = ''

  try {
    await apiRequest(`/api/v1/rbac/mappings/${mapping.id}`, { method: 'DELETE' })
    await loadMappings()
    await loadPreview()
    if (editingMappingId.value === mapping.id) {
      resetForm()
    }
    feedback.value = '映射已删除。'
  } catch (error) {
    if (error instanceof ApiError) {
      mappingError.value = error.message
    } else {
      mappingError.value = '映射删除失败。'
    }
  } finally {
    saving.value = false
  }
}

function editUser(user: AdminUserRecord) {
  editingUserId.value = user.id
  userForm.email = user.email
  userForm.display_name = user.display_name
  userForm.password = ''
  userForm.is_staff = user.is_staff
  userForm.is_superuser = user.is_superuser
  userForm.password_needs_reset = user.password_needs_reset
}

async function saveUser() {
  if (!isAdmin.value) {
    return
  }

  savingUser.value = true
  userError.value = ''
  userFeedback.value = ''

  const payload = {
    email: userForm.email.trim(),
    display_name: userForm.display_name.trim(),
    password: userForm.password,
    is_staff: userForm.is_staff,
    is_superuser: userForm.is_superuser,
    password_needs_reset: userForm.password_needs_reset,
  }

  try {
    if (editingUserId.value) {
      await apiRequest<AdminUserRecord>(`/api/v1/users/${editingUserId.value}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      userFeedback.value = '用户已更新。'
    } else {
      await apiRequest<AdminUserRecord>('/api/v1/users', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      userFeedback.value = '用户已创建。'
    }

    await loadUsers()
    resetUserForm()
  } catch (error) {
    if (error instanceof ApiError) {
      userError.value = error.message
    } else {
      userError.value = '用户保存失败。'
    }
  } finally {
    savingUser.value = false
  }
}

async function deleteUser(user: AdminUserRecord) {
  if (!isAdmin.value) {
    return
  }
  const confirmed = window.confirm(`确认删除用户 ${user.email} 吗？`)
  if (!confirmed) {
    return
  }

  savingUser.value = true
  userError.value = ''
  userFeedback.value = ''

  try {
    await apiRequest(`/api/v1/users/${user.id}`, { method: 'DELETE' })
    await loadUsers()
    if (editingUserId.value === user.id) {
      resetUserForm()
    }
    userFeedback.value = '用户已删除。'
  } catch (error) {
    if (error instanceof ApiError) {
      userError.value = error.message
    } else {
      userError.value = '用户删除失败。'
    }
  } finally {
    savingUser.value = false
  }
}

function editGroup(group: AdminUserGroupRecord) {
  editingGroupId.value = group.id
  groupForm.name = group.name
  groupForm.description = group.description
  groupForm.member_emails_text = group.member_emails.join(', ')
}

async function saveGroup() {
  if (!isAdmin.value) {
    return
  }

  savingGroup.value = true
  groupError.value = ''
  groupFeedback.value = ''

  const payload = {
    name: groupForm.name.trim(),
    description: groupForm.description.trim(),
    member_emails: groupForm.member_emails_text
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  }

  try {
    if (editingGroupId.value) {
      await apiRequest<AdminUserGroupRecord>(`/api/v1/user-groups/${editingGroupId.value}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      groupFeedback.value = '用户组已更新。'
    } else {
      await apiRequest<AdminUserGroupRecord>('/api/v1/user-groups', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      groupFeedback.value = '用户组已创建。'
    }
    await loadGroups()
    resetGroupForm()
  } catch (error) {
    if (error instanceof ApiError) {
      groupError.value = error.message
    } else {
      groupError.value = '用户组保存失败。'
    }
  } finally {
    savingGroup.value = false
  }
}

async function deleteGroup(group: AdminUserGroupRecord) {
  if (!isAdmin.value) {
    return
  }
  const confirmed = window.confirm(`确认删除用户组 ${group.name} 吗？`)
  if (!confirmed) {
    return
  }

  savingGroup.value = true
  groupError.value = ''
  groupFeedback.value = ''

  try {
    await apiRequest(`/api/v1/user-groups/${group.id}`, { method: 'DELETE' })
    await loadGroups()
    if (editingGroupId.value === group.id) {
      resetGroupForm()
    }
    groupFeedback.value = '用户组已删除。'
  } catch (error) {
    if (error instanceof ApiError) {
      groupError.value = error.message
    } else {
      groupError.value = '用户组删除失败。'
    }
  } finally {
    savingGroup.value = false
  }
}

onMounted(async () => {
  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }
  selectedClusterId.value = clusterStore.items[0]?.id ?? ''
  resetForm()
  resetUserForm()
  resetGroupForm()
  if (isAdmin.value) {
    await loadUsers()
    await loadGroups()
  }
})

watch(
  selectedClusterId,
  async (value) => {
    if (!value) {
      return
    }
    resetForm()
    feedback.value = ''
    await loadPreview()
    await loadImpersonationConfig()
    await loadMappings()
  },
  { immediate: false },
)
</script>

<template>
  <div class="page-grid">
    <section class="surface-card">
      <div class="section-head">
        <div>
          <h2>RBAC 桥接</h2>
          <p>这里管理 Kuboard 用户到 Kubernetes Subject 的映射，以及每个集群是否启用 impersonation。</p>
        </div>
      </div>

      <div class="toolbar-grid">
        <label class="field-label">
          目标集群
          <select v-model="selectedClusterId">
            <option disabled value="">请选择集群</option>
            <option v-for="cluster in availableClusters" :key="cluster.id" :value="cluster.id">
              {{ cluster.name }}
            </option>
          </select>
        </label>

        <label v-if="isAdmin" class="field-label">
          Impersonation
          <select
            :value="String(impersonationConfig?.supports_impersonation ?? false)"
            :disabled="!selectedClusterId || saving"
            @change="toggleImpersonation(($event.target as HTMLSelectElement).value === 'true')"
          >
            <option value="false">关闭</option>
            <option value="true">开启</option>
          </select>
        </label>
      </div>

      <div v-if="feedback" class="helper-text" style="margin-top: 12px">{{ feedback }}</div>
      <div v-if="previewError" class="error-text" style="margin-top: 12px">{{ previewError }}</div>
      <div v-if="mappingError" class="error-text" style="margin-top: 12px">{{ mappingError }}</div>

      <div v-if="preview" class="triple-grid" style="margin-top: 18px">
        <div class="stat-card">
          <h3>当前预览用户名</h3>
          <div class="stat-caption" style="margin-top: 10px">{{ preview.username }}</div>
        </div>
        <div class="stat-card">
          <h3>Impersonation 状态</h3>
          <div class="stat-caption" style="margin-top: 10px">
            {{ preview.enabled ? '已启用，当前资源访问会按下方 Subject 落权。' : '未启用，当前仍走控制平面凭据。' }}
          </div>
        </div>
        <div class="stat-card">
          <h3>命中映射</h3>
          <div class="stat-caption" style="margin-top: 10px">
            {{ preview.mapping_ids.length ? `#${preview.mapping_ids.join(', #')}` : '未命中显式映射，当前使用默认邮箱身份。' }}
          </div>
        </div>
      </div>

      <div v-if="preview" class="pill-row" style="margin-top: 16px">
        <span v-for="group in preview.groups" :key="group" class="pill">{{ group }}</span>
      </div>
    </section>

    <section v-if="isAdmin" class="surface-card">
      <div class="section-head">
        <div>
          <h2>{{ editingMappingId ? '编辑映射' : '新增映射' }}</h2>
          <p>支持 user / group 两类来源。未填集群时，表示全局映射。</p>
        </div>
      </div>

      <div class="dual-grid">
        <div class="form-grid">
          <label class="field-label">
            来源类型
            <select v-model="form.source_type">
              <option value="user">user</option>
              <option value="group">group</option>
            </select>
          </label>

          <label class="field-label">
            来源标识
            <input
              v-model="form.source_identifier"
              :placeholder="form.source_type === 'user' ? '例如：viewer@example.com' : '例如：platform-team'"
            />
          </label>

          <label class="field-label">
            Kubernetes Username
            <input v-model="form.kubernetes_username" placeholder="留空时默认使用 Kuboard 用户邮箱" />
          </label>
        </div>

        <div class="form-grid">
          <label class="field-label">
            Kubernetes Groups
            <textarea
              v-model="form.kubernetes_groups_text"
              placeholder="逗号分隔，例如：team:platform, role:readonly"
            />
          </label>

          <label class="field-label">
            生效集群
            <select v-model="form.cluster">
              <option value="">全局映射</option>
              <option v-for="cluster in availableClusters" :key="cluster.id" :value="cluster.id">
                {{ cluster.name }}
              </option>
            </select>
          </label>

          <label class="field-label">
            是否启用
            <select v-model="form.is_enabled">
              <option :value="true">启用</option>
              <option :value="false">停用</option>
            </select>
          </label>
        </div>
      </div>

      <div class="button-row" style="margin-top: 18px">
        <button class="button button-primary" :disabled="saving" @click="saveMapping">
          {{ saving ? '保存中...' : editingMappingId ? '更新映射' : '创建映射' }}
        </button>
        <button class="button button-secondary" :disabled="saving" @click="resetForm">
          取消编辑
        </button>
      </div>
    </section>

    <section v-if="isAdmin" class="surface-card">
      <div class="section-head">
        <div>
          <h2>{{ editingUserId ? '编辑用户' : '新增用户' }}</h2>
          <p>这里维护 Kuboard 本地登录账号，适合作为后续 OIDC / LDAP 接入前的基础用户底座。</p>
        </div>
      </div>

      <div v-if="userFeedback" class="helper-text" style="margin-bottom: 12px">{{ userFeedback }}</div>
      <div v-if="userError" class="error-text" style="margin-bottom: 12px">{{ userError }}</div>

      <div class="dual-grid">
        <div class="form-grid">
          <label class="field-label">
            邮箱
            <input v-model="userForm.email" placeholder="例如：viewer@example.com" />
          </label>

          <label class="field-label">
            显示名称
            <input v-model="userForm.display_name" placeholder="例如：Viewer" />
          </label>

          <label class="field-label">
            {{ editingUserId ? '重置密码（可选）' : '初始密码' }}
            <input v-model="userForm.password" type="password" placeholder="留空则不变更" />
          </label>
        </div>

        <div class="form-grid">
          <label class="field-label">
            Staff
            <select v-model="userForm.is_staff">
              <option :value="false">普通用户</option>
              <option :value="true">管理员</option>
            </select>
          </label>

          <label class="field-label">
            Superuser
            <select v-model="userForm.is_superuser">
              <option :value="false">否</option>
              <option :value="true">是</option>
            </select>
          </label>

          <label class="field-label">
            首次登录强制改密
            <select v-model="userForm.password_needs_reset">
              <option :value="true">开启</option>
              <option :value="false">关闭</option>
            </select>
          </label>
        </div>
      </div>

      <div class="button-row" style="margin-top: 18px">
        <button class="button button-primary" :disabled="savingUser" @click="saveUser">
          {{ savingUser ? '保存中...' : editingUserId ? '更新用户' : '创建用户' }}
        </button>
        <button class="button button-secondary" :disabled="savingUser" @click="resetUserForm">
          取消编辑
        </button>
      </div>

      <div v-if="loadingUsers" class="helper-text" style="margin-top: 16px">正在加载用户列表...</div>
      <table v-else-if="users.length" class="table" style="margin-top: 16px">
        <thead>
          <tr>
            <th>Email</th>
            <th>Display Name</th>
            <th>Role</th>
            <th>Reset</th>
            <th>Last Seen</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.email }}</td>
            <td>{{ user.display_name || '--' }}</td>
            <td>{{ user.is_superuser ? 'superuser' : user.is_staff ? 'staff' : 'user' }}</td>
            <td>{{ user.password_needs_reset ? 'yes' : 'no' }}</td>
            <td>{{ user.last_seen_at || '--' }}</td>
            <td>
              <div class="button-row">
                <button class="button button-secondary" @click="editUser(user)">编辑</button>
                <button class="button button-secondary" @click="deleteUser(user)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state" style="margin-top: 16px">
        当前还没有额外的本地用户，可以先创建一个只读或管理员账号。
      </div>
    </section>

    <section v-if="isAdmin" class="surface-card">
      <div class="section-head">
        <div>
          <h2>{{ editingGroupId ? '编辑用户组' : '新增用户组' }}</h2>
          <p>本地用户组可直接参与 RBAC 映射，适合把一组 Kuboard 用户映射到同一组 Kubernetes Subject。</p>
        </div>
      </div>

      <div v-if="groupFeedback" class="helper-text" style="margin-bottom: 12px">{{ groupFeedback }}</div>
      <div v-if="groupError" class="error-text" style="margin-bottom: 12px">{{ groupError }}</div>

      <div class="dual-grid">
        <div class="form-grid">
          <label class="field-label">
            用户组名称
            <input v-model="groupForm.name" placeholder="例如：platform-team" />
          </label>

          <label class="field-label">
            描述
            <input v-model="groupForm.description" placeholder="例如：Platform Team" />
          </label>
        </div>

        <div class="form-grid">
          <label class="field-label">
            成员邮箱
            <textarea
              v-model="groupForm.member_emails_text"
              placeholder="逗号分隔，例如：dev1@example.com, dev2@example.com"
            />
          </label>
        </div>
      </div>

      <div class="button-row" style="margin-top: 18px">
        <button class="button button-primary" :disabled="savingGroup" @click="saveGroup">
          {{ savingGroup ? '保存中...' : editingGroupId ? '更新用户组' : '创建用户组' }}
        </button>
        <button class="button button-secondary" :disabled="savingGroup" @click="resetGroupForm">
          取消编辑
        </button>
      </div>

      <div v-if="loadingGroups" class="helper-text" style="margin-top: 16px">正在加载用户组...</div>
      <table v-else-if="groups.length" class="table" style="margin-top: 16px">
        <thead>
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Members</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in groups" :key="group.id">
            <td>{{ group.name }}</td>
            <td>{{ group.description || '--' }}</td>
            <td>{{ group.member_emails.join(', ') || '--' }}</td>
            <td>
              <div class="button-row">
                <button class="button button-secondary" @click="editGroup(group)">编辑</button>
                <button class="button button-secondary" @click="deleteGroup(group)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state" style="margin-top: 16px">
        当前还没有本地用户组，可以先创建一个供 RBAC group 映射复用。
      </div>
    </section>

    <section class="surface-card">
      <div class="section-head">
        <div>
          <h2>{{ isAdmin ? '映射列表' : '当前状态说明' }}</h2>
          <p>
            {{
              isAdmin
                ? '这里展示全局映射和当前集群映射。当前筛选会优先展示与所选集群相关的规则。'
                : '当前账号没有管理员权限，所以这里只展示你的最终身份预览，不展示映射管理能力。'
            }}
          </p>
        </div>
      </div>

      <div v-if="isAdmin && loadingMappings" class="helper-text">正在加载映射列表...</div>
      <table v-else-if="isAdmin && visibleMappings.length" class="table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Cluster</th>
            <th>K8s Username</th>
            <th>Groups</th>
            <th>Status</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="mapping in visibleMappings" :key="mapping.id">
            <td>{{ mapping.source_type }} / {{ mapping.source_identifier }}</td>
            <td>{{ mapping.cluster_name || 'global' }}</td>
            <td>{{ mapping.kubernetes_username || '--' }}</td>
            <td>{{ mapping.kubernetes_groups.join(', ') || '--' }}</td>
            <td>{{ mapping.is_enabled ? 'enabled' : 'disabled' }}</td>
            <td>
              <div class="button-row">
                <button class="button button-secondary" @click="editMapping(mapping)">编辑</button>
                <button class="button button-secondary" @click="deleteMapping(mapping)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        {{
          isAdmin
            ? '当前还没有与所选集群相关的映射，可以先创建一条 user 或 group 规则。'
            : '当前页面为只读模式。若要维护映射，请使用管理员账号登录。'
        }}
      </div>
    </section>
  </div>
</template>
