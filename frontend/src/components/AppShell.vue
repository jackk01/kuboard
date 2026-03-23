<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const recentRouteNames = ref<string[]>([])

const navItems = [
  { label: '总览', icon: '总', to: { name: 'dashboard' } },
  { label: '集群', icon: '集', to: { name: 'clusters' } },
  { label: '资源', icon: '资', to: { name: 'explorer' } },
  { label: '审计', icon: '审', to: { name: 'audit' } },
  { label: '设置', icon: '设', to: { name: 'settings' } },
]

type QuickEntry = {
  key: string
  label: string
  caption: string
  to: { name: string }
  action?: string
}

const quickEntries: QuickEntry[] = [
  { key: 'import', label: '导入集群', caption: '跳转到集群页并展开导入面板', to: { name: 'clusters' }, action: 'clusters.open_import' },
  { key: 'health-all', label: '批量健康检查', caption: '在集群页执行批量健康检查', to: { name: 'clusters' }, action: 'clusters.health_all' },
  { key: 'explorer', label: '资源浏览', caption: '打开资源浏览器', to: { name: 'explorer' } },
  { key: 'audit-refresh', label: '刷新审计', caption: '跳转审计中心并刷新事件', to: { name: 'audit' }, action: 'audit.refresh' },
]

const pageTitle = computed(() => {
  return navItems.find((item) => item.to.name === route.name)?.label ?? 'Kuboard'
})

const recentNavItems = computed(() =>
  recentRouteNames.value
    .map((name) => navItems.find((item) => item.to.name === name))
    .filter((item): item is (typeof navItems)[number] => Boolean(item)),
)

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
}

async function handleLogout() {
  await sessionStore.logout()
  await router.push({ name: 'login' })
}

function dispatchShellAction(action: string) {
  window.setTimeout(() => {
    window.dispatchEvent(new CustomEvent('kuboard:command', { detail: { action } }))
  }, 60)
}

async function runQuickEntry(entry: QuickEntry) {
  await router.push(entry.to)
  if (entry.action) {
    dispatchShellAction(entry.action)
  }
}

readRecentRoutes()

watch(
  () => route.name,
  (value) => {
    if (typeof value === 'string' && navItems.some((item) => item.to.name === value)) {
      markRecentRoute(value)
    }
  },
  { immediate: true },
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
          <span class="nav-link-icon">{{ item.icon }}</span>
          <span class="nav-link-text">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <section class="sidebar-quick">
        <div class="sidebar-title">快捷入口</div>
        <button
          v-for="entry in quickEntries"
          :key="entry.key"
          class="sidebar-entry"
          type="button"
          @click="runQuickEntry(entry)"
        >
          <strong>{{ entry.label }}</strong>
          <span>{{ entry.caption }}</span>
        </button>
      </section>

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
        <div class="pill-row">
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
  </div>
</template>
