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
      <section class="auth-panel">
        <header class="auth-heading">
          <h1 class="page-title auth-title">Kuboard</h1>
          <p class="auth-subtitle">多集群管理面板</p>
        </header>
        <div class="form-grid auth-form">
          <div class="auth-field-row">
            <input id="login-user" v-model="email" type="text" autocomplete="username" placeholder="用户" />
          </div>

          <div class="auth-field-row">
            <input
              id="login-password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="密码"
              @keyup.enter="submit"
            />
          </div>

          <div v-if="errorMessage" class="error-text">{{ errorMessage }}</div>

          <div class="button-row">
            <button class="button button-primary" :disabled="sessionStore.isAuthenticating" @click="submit">
              {{ sessionStore.isAuthenticating ? '登录中...' : '登录' }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.auth-heading {
  margin-bottom: 20px;
  text-align: center;
}

.auth-title {
  margin: 0;
  font-size: clamp(24px, 3vw, 30px);
  line-height: 1.2;
}

.auth-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--kb-text-soft);
  letter-spacing: 0.04em;
}

.auth-field-row {
  display: block;
}

.auth-field-row input {
  width: 100%;
  padding: 13px 14px;
  border: 1px solid var(--kb-border);
  border-radius: var(--kb-radius-sm);
  background: rgba(255, 255, 255, 0.92);
  color: var(--kb-text);
  text-align: center;
  transition:
    border-color 120ms ease,
    box-shadow 120ms ease,
    transform 120ms ease;
}

.auth-field-row input:focus {
  outline: none;
  border-color: rgba(14, 165, 164, 0.4);
  box-shadow: 0 0 0 4px rgba(14, 165, 164, 0.12);
}

.auth-field-row input::placeholder {
  color: #9ca3af;
}

.auth-form .button-row {
  justify-content: center;
}
</style>
