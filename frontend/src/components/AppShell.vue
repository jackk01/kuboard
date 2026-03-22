<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()
const accountMenuOpen = ref(false)
const accountMenuRef = ref<HTMLElement | null>(null)

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

function toggleAccountMenu() {
  accountMenuOpen.value = !accountMenuOpen.value
}

function goUserSettings() {
  accountMenuOpen.value = false
  router.push({ name: 'settings' })
}

async function handleLogout() {
  accountMenuOpen.value = false
  await sessionStore.logout()
  await router.push({ name: 'login' })
}

function handleClickOutside(event: MouseEvent) {
  const root = accountMenuRef.value
  if (!root) {
    return
  }
  if (event.target instanceof Node && !root.contains(event.target)) {
    accountMenuOpen.value = false
  }
}

watch(
  () => route.fullPath,
  () => {
    accountMenuOpen.value = false
  },
)

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
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
    </aside>

    <main class="shell-main">
      <header class="shell-topbar">
        <div>
          <div class="helper-text">Kuboard / {{ pageTitle }}</div>
          <h1 class="page-title">{{ pageTitle }}</h1>
        </div>

        <div ref="accountMenuRef" class="account-menu">
          <button
            class="account-trigger"
            type="button"
            aria-label="用户菜单"
            :aria-expanded="accountMenuOpen ? 'true' : 'false'"
            @click="toggleAccountMenu"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-4.97 0-9 2.69-9 6v2h18v-2c0-3.31-4.03-6-9-6Z"
              />
            </svg>
          </button>
          <div v-if="accountMenuOpen" class="account-dropdown">
            <div class="account-meta">
              <strong>{{ sessionStore.displayName }}</strong>
              <span class="muted">{{ sessionStore.currentUser?.email }}</span>
            </div>
            <button type="button" class="account-action" @click="goUserSettings">用户设置</button>
            <button type="button" class="account-action account-action-danger" @click="handleLogout">
              退出登录
            </button>
          </div>
        </div>
      </header>

      <RouterView />
    </main>
  </div>
</template>
