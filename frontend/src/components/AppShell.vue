<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()

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
      </header>

      <RouterView />
    </main>
  </div>
</template>
