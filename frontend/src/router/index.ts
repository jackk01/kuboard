import {
  createRouter,
  createWebHistory,
  type Router,
} from 'vue-router'

import AppShell from '../components/AppShell.vue'
import AuditPage from '../pages/AuditPage.vue'
import ClustersPage from '../pages/ClustersPage.vue'
import DashboardPage from '../pages/DashboardPage.vue'
import ExplorerPage from '../pages/ExplorerPage.vue'
import LoginPage from '../pages/LoginPage.vue'
import PodLogsPage from '../pages/PodLogsPage.vue'
import PodTerminalPage from '../pages/PodTerminalPage.vue'
import SettingsPage from '../pages/SettingsPage.vue'
import { useSessionStore } from '../stores/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginPage,
      meta: { requiresAuth: false },
    },
    {
      path: '/pod-terminal',
      name: 'pod-terminal',
      component: PodTerminalPage,
      meta: { title: '容器终端' },
    },
    {
      path: '/',
      component: AppShell,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: DashboardPage,
        },
        {
          path: 'clusters',
          name: 'clusters',
          component: ClustersPage,
        },
        {
          path: 'explorer',
          name: 'explorer',
          component: ExplorerPage,
        },
        {
          path: 'pod-logs',
          name: 'pod-logs',
          component: PodLogsPage,
          meta: {
            title: 'Pod 日志',
            description: '查看实时日志并导出当前内容',
            shellTopbarVariant: 'compact',
            shellTopbarEyebrow: false,
            shellViewportLock: true,
          },
        },
        {
          path: 'audit',
          name: 'audit',
          component: AuditPage,
        },
        {
          path: 'settings',
          name: 'settings',
          component: SettingsPage,
        },
      ],
    },
  ],
})

export function setupRouterGuards(targetRouter: Router) {
  targetRouter.beforeEach(async (to) => {
    const sessionStore = useSessionStore()
    if (!sessionStore.isReady) {
      await sessionStore.bootstrap()
    }

    const requiresAuth = to.meta.requiresAuth !== false
    if (requiresAuth && !sessionStore.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    if (to.name === 'login' && sessionStore.isAuthenticated) {
      return { name: 'dashboard' }
    }

    return true
  })
}

export default router
