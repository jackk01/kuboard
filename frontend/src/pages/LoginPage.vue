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

const authMetrics = [
  { label: 'Clusters', value: 'Multi', description: '统一接入多套 Kubernetes 环境' },
  { label: 'Audit', value: 'Trace', description: '变更轨迹与审计事件集中查看' },
  { label: 'Access', value: 'RBAC', description: '账号、映射与权限策略一体化' },
]

const authHighlights = [
  '集群导入、资源浏览、日志与终端操作保持原有能力不变',
  '统一的卡片层级、状态标签和表格视觉，降低认知负担',
  '更清晰的导航与页面组织方式，适合长期运维使用',
]

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
      <section class="auth-showcase">
        <div class="auth-showcase-panel">
          <div class="eyebrow auth-eyebrow">Kuboard Console</div>
          <h1 class="auth-showcase-title">让多集群管理更清晰，也更稳定。</h1>
          <p class="auth-showcase-description">
            在不改变现有功能的前提下，用更现代的工作台视觉重新组织高频操作路径，让资源浏览、审计追踪和控制面设置更易读、更统一。
          </p>

          <div class="auth-metric-grid">
            <article v-for="item in authMetrics" :key="item.label" class="auth-metric-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <p>{{ item.description }}</p>
            </article>
          </div>

          <div class="auth-highlight-list">
            <article v-for="item in authHighlights" :key="item" class="auth-highlight-card">
              <span class="auth-highlight-dot" />
              <p>{{ item }}</p>
            </article>
          </div>
        </div>
      </section>

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
  display: grid;
  gap: 24px;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 420px);
  align-items: stretch;
  width: min(1120px, 100%);
}

.auth-showcase {
  position: relative;
  overflow: hidden;
  padding: 18px;
  border-radius: 30px;
  border: 1px solid rgba(164, 180, 200, 0.28);
  background:
    radial-gradient(circle at top right, rgba(22, 119, 255, 0.2), transparent 32%),
    radial-gradient(circle at bottom left, rgba(14, 165, 164, 0.18), transparent 34%),
    linear-gradient(160deg, rgba(9, 19, 35, 0.96), rgba(15, 32, 58, 0.94));
  box-shadow: 0 28px 80px rgba(15, 32, 58, 0.2);
}

.auth-showcase-panel {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 22px;
  min-height: 100%;
  padding: 26px;
}

.auth-eyebrow {
  margin-bottom: 0;
}

.auth-showcase-title {
  max-width: 640px;
  margin: 0;
  color: #f6f9ff;
  font-size: clamp(2.1rem, 4vw, 3.5rem);
  line-height: 1.04;
  letter-spacing: -0.05em;
}

.auth-showcase-description {
  max-width: 640px;
  margin: 0;
  color: rgba(226, 235, 247, 0.82);
  font-size: 15px;
  line-height: 1.8;
}

.auth-metric-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.auth-metric-card {
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
}

.auth-metric-card span {
  display: block;
  color: rgba(226, 235, 247, 0.68);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.auth-metric-card strong {
  display: block;
  margin-top: 12px;
  color: #ffffff;
  font-size: 28px;
  letter-spacing: -0.05em;
}

.auth-metric-card p {
  margin: 10px 0 0;
  color: rgba(226, 235, 247, 0.8);
  font-size: 13px;
  line-height: 1.65;
}

.auth-highlight-list {
  display: grid;
  gap: 12px;
}

.auth-highlight-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.auth-highlight-dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, #33c7ff, #7ef3d3);
  box-shadow: 0 0 0 6px rgba(51, 199, 255, 0.12);
  flex: 0 0 auto;
}

.auth-highlight-card p {
  margin: 0;
  color: rgba(236, 243, 252, 0.84);
  line-height: 1.7;
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

@media (max-width: 1080px) {
  .auth-layout {
    grid-template-columns: 1fr;
  }

  .auth-showcase {
    min-height: 0;
  }
}

@media (max-width: 720px) {
  .auth-showcase-panel {
    padding: 8px;
  }

  .auth-metric-grid {
    grid-template-columns: 1fr;
  }

  .auth-card {
    width: 100%;
  }
}
</style>
