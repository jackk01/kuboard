<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const quickSearch = ref('')
const recentRouteNames = ref<string[]>([])
const commandOpen = ref(false)
const commandQuery = ref('')
const commandActiveIndex = ref(0)

const navItems = [
  { label: '总览', to: { name: 'dashboard' }, icon: '01' },
  { label: '集群', to: { name: 'clusters' }, icon: '02' },
  { label: '资源', to: { name: 'explorer' }, icon: '03' },
  { label: '审计', to: { name: 'audit' }, icon: '04' },
  { label: '设置', to: { name: 'settings' }, icon: '05' },
]

const pageTitle = computed(() => {
  return navItems.find((item) => item.to.name === route.name)?.label ?? 'Kuboard'
})

const quickLinks = computed(() => {
  const keyword = quickSearch.value.trim().toLowerCase()
  if (!keyword) {
    return navItems.filter((item) => item.to.name !== route.name).slice(0, 4)
  }
  return navItems.filter((item) => item.label.toLowerCase().includes(keyword))
})

const recentNavItems = computed(() =>
  recentRouteNames.value
    .map((name) => navItems.find((item) => item.to.name === name))
    .filter((item): item is (typeof navItems)[number] => Boolean(item)),
)

const commandItems = computed(() => {
  const pages = navItems.map((item) => ({
    id: `nav:${String(item.to.name)}`,
    label: `打开${item.label}`,
    description: `跳转到${item.label}页面`,
  }))
  const actions = [
    { id: 'action:refresh', label: '刷新当前页面', description: '重新请求当前路由页面' },
    { id: 'action:clusters', label: '跳转并导入集群', description: '前往集群页继续导入/运维' },
    { id: 'action:clusters.health_all', label: '批量健康检查', description: '在集群页执行批量健康检查' },
    { id: 'action:clusters.discovery_all', label: '批量同步 Discovery', description: '在集群页执行批量 Discovery 同步' },
    { id: 'action:audit.refresh', label: '刷新审计数据', description: '在审计页重新加载事件列表' },
    { id: 'action:logout', label: '退出登录', description: '注销并回到登录页' },
  ]
  return [...pages, ...actions]
})

const filteredCommandItems = computed(() => {
  const q = commandQuery.value.trim().toLowerCase()
  if (!q) return commandItems.value
  return commandItems.value.filter((item) => {
    const text = `${item.label} ${item.description}`.toLowerCase()
    return text.includes(q)
  })
})

function readRecentRoutes() {
  try {
    const raw = window.localStorage.getItem('kuboard:recent-routes')
    const parsed = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) {
      recentRouteNames.value = parsed.filter((item) => typeof item === 'string')
    }
  } catch {
    recentRouteNames.value = []
  }
}

function writeRecentRoutes(names: string[]) {
  window.localStorage.setItem('kuboard:recent-routes', JSON.stringify(names))
}

function markRecentRoute(name: string) {
  const deduped = [name, ...recentRouteNames.value.filter((item) => item !== name)].slice(0, 6)
  recentRouteNames.value = deduped
  writeRecentRoutes(deduped)
}

function jumpTo(item: (typeof navItems)[number]) {
  router.push(item.to)
  quickSearch.value = ''
}

async function handleLogout() {
  await sessionStore.logout()
  await router.push({ name: 'login' })
}

function openCommandPalette() {
  commandOpen.value = true
  commandQuery.value = ''
  commandActiveIndex.value = 0
}

function closeCommandPalette() {
  commandOpen.value = false
}

function dispatchShellAction(action: string) {
  window.setTimeout(() => {
    window.dispatchEvent(new CustomEvent('kuboard:command', { detail: { action } }))
  }, 50)
}

async function executeCommand(commandId: string) {
  if (commandId.startsWith('nav:')) {
    const targetName = commandId.replace('nav:', '')
    const target = navItems.find((item) => String(item.to.name) === targetName)
    if (target) {
      await router.push(target.to)
    }
    closeCommandPalette()
    return
  }

  if (commandId === 'action:refresh') {
    closeCommandPalette()
    window.location.reload()
    return
  }

  if (commandId === 'action:clusters') {
    await router.push({ name: 'clusters' })
    closeCommandPalette()
    return
  }

  if (commandId === 'action:clusters.health_all') {
    await router.push({ name: 'clusters' })
    closeCommandPalette()
    dispatchShellAction('clusters.health_all')
    return
  }

  if (commandId === 'action:clusters.discovery_all') {
    await router.push({ name: 'clusters' })
    closeCommandPalette()
    dispatchShellAction('clusters.discovery_all')
    return
  }

  if (commandId === 'action:audit.refresh') {
    await router.push({ name: 'audit' })
    closeCommandPalette()
    dispatchShellAction('audit.refresh')
    return
  }

  if (commandId === 'action:logout') {
    closeCommandPalette()
    await handleLogout()
  }
}

function handleCommandKeydown(event: KeyboardEvent) {
  const isMetaK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k'
  if (isMetaK) {
    event.preventDefault()
    if (commandOpen.value) {
      closeCommandPalette()
    } else {
      openCommandPalette()
    }
    return
  }

  if (!commandOpen.value) {
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    closeCommandPalette()
    return
  }

  if (!filteredCommandItems.value.length) {
    return
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    commandActiveIndex.value = (commandActiveIndex.value + 1) % filteredCommandItems.value.length
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    commandActiveIndex.value =
      (commandActiveIndex.value - 1 + filteredCommandItems.value.length) % filteredCommandItems.value.length
    return
  }

  if (event.key === 'Enter') {
    event.preventDefault()
    const target = filteredCommandItems.value[commandActiveIndex.value]
    if (target) {
      void executeCommand(target.id)
    }
  }
}

readRecentRoutes()
onMounted(() => {
  window.addEventListener('keydown', handleCommandKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleCommandKeydown)
})

watch(
  () => route.name,
  (value) => {
    if (typeof value === 'string' && navItems.some((item) => item.to.name === value)) {
      markRecentRoute(value)
    }
  },
  { immediate: true },
)

watch(
  () => commandQuery.value,
  () => {
    commandActiveIndex.value = 0
  },
)
</script>

<template>
  <div class="app-shell">
    <aside class="shell-sidebar">
      <div class="brand-row">
        <div class="brand-mark">K</div>
        <div class="brand-text">
          <strong>Kuboard</strong>
          <span>多集群管理面板</span>
        </div>
      </div>

      <nav class="nav-list">
        <RouterLink
          v-for="item in navItems"
          :key="item.label"
          class="nav-link"
          :to="item.to"
        >
          <span class="tag">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-card">
        <div class="helper-text">当前用户</div>
        <div style="margin-top: 8px; font-weight: 700">{{ sessionStore.displayName }}</div>
        <div class="muted" style="margin-top: 6px">{{ sessionStore.currentUser?.email || '--' }}</div>
      </div>
    </aside>

    <main class="shell-main">
      <header class="shell-topbar">
        <div>
          <div class="helper-text">Kuboard / {{ pageTitle }}</div>
          <h1 class="page-title">{{ pageTitle }}</h1>
        </div>
        <div class="shell-top-actions">
          <button class="button button-secondary" style="padding: 8px 14px" @click="handleLogout">退出登录</button>
        </div>
      </header>

      <section class="surface-card shell-quick-card">
        <div class="shell-quick-row">
          <input
            v-model="quickSearch"
            class="cluster-search"
            placeholder="全局快捷搜索：总览 / 集群 / 资源 / 审计 / 设置"
          />
          <div class="button-row">
            <button
              v-for="item in quickLinks"
              :key="`quick-${item.label}`"
              class="button button-secondary"
              style="padding: 8px 12px"
              @click="jumpTo(item)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div class="pill-row" style="margin-top: 10px">
          <button class="button button-secondary shell-recent-btn" @click="openCommandPalette">
            命令面板 (Ctrl/Cmd + K)
          </button>
          <span class="muted">最近访问</span>
          <button
            v-for="item in recentNavItems"
            :key="`recent-${item.label}`"
            class="button button-secondary shell-recent-btn"
            @click="jumpTo(item)"
          >
            {{ item.label }}
          </button>
        </div>
      </section>

      <RouterView />
    </main>

    <div v-if="commandOpen" class="command-backdrop" @click.self="closeCommandPalette">
      <div class="command-panel">
        <label class="field-label">
          命令面板
          <input
            v-model="commandQuery"
            class="cluster-search"
            placeholder="输入命令，如：打开集群 / 刷新当前页面 / 退出登录"
            autofocus
          />
        </label>

        <div v-if="filteredCommandItems.length" class="command-list">
          <button
            v-for="(item, index) in filteredCommandItems"
            :key="item.id"
            class="command-item"
            :class="{ 'command-item-active': index === commandActiveIndex }"
            @click="executeCommand(item.id)"
          >
            <strong>{{ item.label }}</strong>
            <span>{{ item.description }}</span>
          </button>
        </div>
        <div v-else class="empty-state">没有匹配命令，试试输入“打开集群”或“刷新”。</div>
      </div>
    </div>
  </div>
</template>
