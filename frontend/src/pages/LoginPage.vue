<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '../lib/api'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const sessionStore = useSessionStore()

const email = ref('admin@kuboard.local')
const password = ref('admin123456')
const errorMessage = ref('')

async function submit() {
  errorMessage.value = ''

  try {
    await sessionStore.login(email.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (error) {
    if (error instanceof ApiError) {
      errorMessage.value = error.message
      return
    }
    errorMessage.value = '登录失败，请检查后端服务是否已启动。'
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <section class="auth-hero">
        <div class="eyebrow">Cloud Native Console</div>
        <h1 class="auth-title">看清每个集群，掌控每次变更。</h1>
        <p class="auth-description">
          Kuboard 的初始化版本已经接入多集群导入、审计留痕和通用资源控制平面骨架，
          接下来可以在这个基础上继续实现 Kubernetes Gateway 与实时流式能力。
        </p>

        <div class="auth-grid">
          <div class="auth-pill">
            <strong>多集群入口</strong>
            <span>通过 kubeconfig 导入，后端统一收口访问。</span>
          </div>
          <div class="auth-pill">
            <strong>RBAC 导向</strong>
            <span>已预留身份映射与权限桥接模型，方便后续接 Kubernetes Impersonation。</span>
          </div>
          <div class="auth-pill">
            <strong>轻量元数据</strong>
            <span>当前使用 SQLite + Redis，先快速跑通控制平面。</span>
          </div>
        </div>
      </section>

      <section class="auth-panel">
        <div class="section-head">
          <div>
            <h2>登录 Kuboard</h2>
            <p>默认管理员账号可通过 `bootstrap_kuboard` 命令生成。</p>
          </div>
        </div>

        <div class="form-grid">
          <label class="field-label">
            邮箱
            <input v-model="email" type="email" autocomplete="username" />
          </label>

          <label class="field-label">
            密码
            <input v-model="password" type="password" autocomplete="current-password" />
          </label>

          <div v-if="errorMessage" class="error-text">{{ errorMessage }}</div>

          <div class="button-row">
            <button class="button button-primary" :disabled="sessionStore.isAuthenticating" @click="submit">
              {{ sessionStore.isAuthenticating ? '登录中...' : '进入控制台' }}
            </button>
          </div>

          <div class="helper-text">
            默认建议先执行：`python3 manage.py bootstrap_kuboard`
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

