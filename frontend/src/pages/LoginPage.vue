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
    <div class="auth-layout">
      <div class="auth-card">
        <section class="auth-panel">
          <header class="auth-heading">
            <span class="auth-form-badge">欢迎回来</span>
            <h2 class="page-title auth-title">登录控制台</h2>
            <p class="auth-subtitle">使用平台账户进入 Kuboard 工作台。</p>
          </header>
          <div class="form-grid auth-form">
            <label class="field-label auth-input-label" for="login-user">
              账号
              <input id="login-user" v-model="email" type="text" autocomplete="username" placeholder="请输入用户邮箱" />
            </label>

            <label class="field-label auth-input-label" for="login-password">
              密码
              <input
                id="login-password"
                v-model="password"
                type="password"
                autocomplete="current-password"
                placeholder="请输入登录密码"
                @keyup.enter="submit"
              />
            </label>

            <div class="helper-text auth-helper">默认演示账号：admin@kuboard.local / admin123456</div>

            <div v-if="errorMessage" class="error-text">{{ errorMessage }}</div>

            <div class="button-row">
              <button class="button button-primary auth-submit" :disabled="sessionStore.isAuthenticating" @click="submit">
                {{ sessionStore.isAuthenticating ? '登录中...' : '进入工作台' }}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-layout {
  width: min(420px, 100%);
}

.auth-heading {
  margin-bottom: 22px;
}

.auth-form-badge {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(22, 119, 255, 0.1);
  color: var(--kb-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.auth-title {
  margin: 18px 0 0;
  font-size: clamp(1.8rem, 3vw, 2.35rem);
  line-height: 1.1;
}

.auth-subtitle {
  margin: 10px 0 0;
  font-size: 14px;
  color: var(--kb-text-soft);
  line-height: 1.7;
}

.auth-input-label {
  gap: 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.auth-helper {
  margin-top: -4px;
}

.auth-submit {
  width: 100%;
  justify-content: center;
}
</style>
