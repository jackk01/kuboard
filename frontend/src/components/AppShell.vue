<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const sidebarCollapsed = ref(false)

const navItems = [
  { label: '总览', short: '总', description: '平台运行态与快捷入口', to: { name: 'dashboard' } },
  { label: '集群', short: '集', description: '集群接入、状态与健康检查', to: { name: 'clusters' } },
  { label: '资源', short: '资', description: '工作负载与资源浏览操作', to: { name: 'explorer' } },
  { label: '审计', short: '审', description: '事件筛选、追踪与详情查看', to: { name: 'audit' } },
  { label: '设置', short: '设', description: '账号、映射与系统配置', to: { name: 'settings' } },
]

const pageTitle = computed(() => {
  return (route.meta.title as string | undefined) || navItems.find((item) => item.to.name === route.name)?.label || 'Kuboard'
})

const pageDescription = computed(() => {
  return (
    (route.meta.description as string | undefined) ||
    navItems.find((item) => item.to.name === route.name)?.description ||
    '多集群工作台'
  )
})

const userInitial = computed(() => {
  const value = sessionStore.displayName?.trim() || sessionStore.currentUser?.email?.trim() || 'U'
  return value.slice(0, 1).toUpperCase()
})

const userDisplayName = computed(() => {
  return sessionStore.displayName?.trim() || sessionStore.currentUser?.email?.trim() || '当前用户'
})

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

async function handleLogout() {
  await sessionStore.logout()
  await router.push({ name: 'login' })
}

onMounted(() => {
  sidebarCollapsed.value = window.localStorage.getItem('kuboard.sidebar.collapsed') === 'true'
})

watch(sidebarCollapsed, (value) => {
  window.localStorage.setItem('kuboard.sidebar.collapsed', String(value))
})
</script>

<template>
  <div class="app-shell" :class="{ 'app-shell-collapsed': sidebarCollapsed }">
    <aside class="shell-sidebar" :class="{ 'shell-sidebar-collapsed': sidebarCollapsed }">
      <div class="brand-row">
        <div class="brand-mark">K</div>
        <div v-if="!sidebarCollapsed" class="brand-text">
          <strong>Kuboard</strong>
          <span>多集群管理</span>
        </div>
        <button
          class="sidebar-toggle"
          type="button"
          :aria-label="sidebarCollapsed ? '展开左侧菜单' : '折叠左侧菜单'"
          :title="sidebarCollapsed ? '展开左侧菜单' : '折叠左侧菜单'"
          @click="toggleSidebar"
        >
          <span class="sidebar-toggle-icon" :class="{ 'sidebar-toggle-icon-collapsed': sidebarCollapsed }" />
        </button>
      </div>

      <nav class="nav-list">
        <RouterLink
          v-for="item in navItems"
          :key="item.label"
          class="nav-link"
          active-class=""
          exact-active-class="router-link-active"
          :to="item.to"
          :title="sidebarCollapsed ? item.label : undefined"
        >
          <span class="nav-link-badge">{{ item.short }}</span>
          <span class="nav-link-content">
            <span class="nav-link-text">{{ item.label }}</span>
            <span class="nav-link-description">{{ item.description }}</span>
          </span>
        </RouterLink>
      </nav>

      <div
        class="sidebar-card sidebar-user-card"
        :title="sidebarCollapsed ? userDisplayName : undefined"
      >
        <div class="sidebar-user-avatar">{{ userInitial }}</div>
        <div v-if="!sidebarCollapsed" class="sidebar-user-meta">
          <div class="helper-text">当前用户</div>
          <strong>{{ userDisplayName }}</strong>
          <span class="muted">{{ sessionStore.currentUser?.email || '--' }}</span>
        </div>
      </div>
    </aside>

    <main class="shell-main">
      <header class="shell-topbar">
        <div class="shell-topbar-main">
          <div class="eyebrow shell-topbar-eyebrow">Kuboard Workspace</div>
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-description shell-topbar-description">{{ pageDescription }}</p>
        </div>
        <div class="shell-top-actions">
          <div class="user-chip shell-user-chip">
            <span class="shell-user-avatar">{{ userInitial }}</span>
            <span class="shell-user-meta-inline">
              <strong>{{ userDisplayName }}</strong>
              <span>{{ sessionStore.currentUser?.email || '--' }}</span>
            </span>
          </div>
          <button class="button button-secondary shell-topbar-button shell-collapse-button" @click="toggleSidebar">
            {{ sidebarCollapsed ? '展开菜单' : '折叠菜单' }}
          </button>
          <button class="button button-secondary shell-topbar-button" @click="handleLogout">退出登录</button>
        </div>
      </header>

      <RouterView />
    </main>
  </div>
</template>
