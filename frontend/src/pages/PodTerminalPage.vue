<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { TerminalOutputResponse, TerminalSessionResponse } from '../types'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()

const terminalSession = ref<TerminalSessionResponse | null>(null)
const terminalOutput = ref('')
const terminalError = ref('')
const terminalConnecting = ref(false)
const terminalSending = ref(false)
const terminalCursor = ref(0)
const terminalShell = ref<'/bin/sh' | '/bin/bash'>('/bin/sh')
const terminalInput = ref('')
const terminalRows = ref(32)
const terminalCols = ref(120)

let terminalLoopToken = 0
let terminalPollTimer: number | null = null

const clusterId = computed(() => String(route.query.cluster || ''))
const podName = computed(() => String(route.query.pod || ''))
const namespace = computed(() => String(route.query.namespace || 'default'))
const containerName = computed(() => String(route.query.container || ''))
const selectedCluster = computed(() => clusterStore.items.find((cluster) => cluster.id === clusterId.value) ?? null)
const pageReady = computed(() => Boolean(clusterId.value && podName.value))

function clearTerminalPollTimer() {
  if (terminalPollTimer !== null) {
    window.clearTimeout(terminalPollTimer)
    terminalPollTimer = null
  }
}

async function closeStreamSession(sessionId: number, statusValue = 'stopped') {
  try {
    await apiRequest(`/api/v1/streams/sessions/${sessionId}/close`, {
      method: 'POST',
      body: JSON.stringify({ status: statusValue }),
    })
  } catch {
    // ignore close failures in terminal page
  }
}

function resetTerminalState(options: { closeRemote?: boolean } = {}) {
  const sessionId = terminalSession.value?.session.id ?? null
  terminalLoopToken += 1
  clearTerminalPollTimer()
  terminalSession.value = null
  terminalOutput.value = ''
  terminalError.value = ''
  terminalConnecting.value = false
  terminalSending.value = false
  terminalCursor.value = 0
  terminalInput.value = ''
  if (options.closeRemote !== false && sessionId) {
    void closeStreamSession(sessionId)
  }
}

async function pollTerminalOutput(loopToken: number) {
  if (!terminalSession.value || loopToken !== terminalLoopToken) {
    return
  }

  try {
    const payload = await apiRequest<TerminalOutputResponse>(
      `/api/v1/streams/sessions/${terminalSession.value.session.id}/output?cursor=${terminalCursor.value}`,
    )
    if (loopToken !== terminalLoopToken) {
      return
    }
    if (payload.text) {
      terminalOutput.value = `${terminalOutput.value}${payload.text}`.slice(-60000)
    }
    terminalCursor.value = payload.cursor
    if (payload.closed) {
      terminalSession.value = {
        ...terminalSession.value,
        session: {
          ...terminalSession.value.session,
          status: payload.status,
          closed_at: payload.closed_at,
        },
      }
      return
    }
  } catch (error) {
    if (loopToken !== terminalLoopToken) {
      return
    }
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端输出读取失败。'
    }
    return
  }

  if (terminalSession.value && loopToken === terminalLoopToken) {
    terminalPollTimer = window.setTimeout(() => {
      void pollTerminalOutput(loopToken)
    }, 900)
  }
}

async function openTerminalSession() {
  if (!pageReady.value) {
    return
  }

  resetTerminalState()
  terminalConnecting.value = true
  terminalError.value = ''

  try {
    terminalSession.value = await apiRequest<TerminalSessionResponse>(
      `/api/v1/clusters/${clusterId.value}/resources/core/v1/pods/${encodeURIComponent(podName.value)}/terminal`,
      {
        method: 'POST',
        body: JSON.stringify({
          namespace: namespace.value,
          container: containerName.value || undefined,
          shell: terminalShell.value,
          rows: terminalRows.value,
          cols: terminalCols.value,
        }),
      },
    )
    terminalOutput.value = terminalSession.value.text || ''
    terminalCursor.value = terminalSession.value.cursor || 0
    terminalLoopToken += 1
    void pollTerminalOutput(terminalLoopToken)
  } catch (error) {
    terminalSession.value = null
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端建立失败。'
    }
  } finally {
    terminalConnecting.value = false
  }
}

async function sendTerminalInput(data: string) {
  if (!terminalSession.value || !data) {
    return
  }

  terminalSending.value = true
  terminalError.value = ''
  try {
    await apiRequest(`/api/v1/streams/sessions/${terminalSession.value.session.id}/input`, {
      method: 'POST',
      body: JSON.stringify({ input: data }),
    })
  } catch (error) {
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端输入发送失败。'
    }
  } finally {
    terminalSending.value = false
  }
}

async function submitTerminalInput() {
  const value = terminalInput.value
  if (!value.trim()) {
    return
  }
  terminalInput.value = ''
  await sendTerminalInput(`${value}\n`)
}

async function sendTerminalShortcut(shortcut: 'enter' | 'ctrlc') {
  await sendTerminalInput(shortcut === 'enter' ? '\n' : '\u0003')
}

async function resizeTerminal() {
  if (!terminalSession.value) {
    return
  }
  try {
    await apiRequest(`/api/v1/streams/sessions/${terminalSession.value.session.id}/resize`, {
      method: 'POST',
      body: JSON.stringify({
        rows: terminalRows.value,
        cols: terminalCols.value,
      }),
    })
  } catch (error) {
    if (error instanceof ApiError) {
      terminalError.value = error.message
    } else {
      terminalError.value = '终端尺寸调整失败。'
    }
  }
}

async function switchShell(shell: '/bin/sh' | '/bin/bash') {
  terminalShell.value = shell
  await router.replace({
    name: 'pod-terminal',
    query: {
      cluster: clusterId.value,
      pod: podName.value,
      namespace: namespace.value,
      container: containerName.value || undefined,
      shell,
      rows: String(terminalRows.value),
      cols: String(terminalCols.value),
    },
  })
  await openTerminalSession()
}

watch([terminalRows, terminalCols], async () => {
  if (terminalSession.value) {
    await resizeTerminal()
  }
})

onMounted(async () => {
  const shell = String(route.query.shell || '/bin/sh')
  terminalShell.value = shell === '/bin/bash' ? '/bin/bash' : '/bin/sh'
  const rows = Number.parseInt(String(route.query.rows || '32'), 10)
  const cols = Number.parseInt(String(route.query.cols || '120'), 10)
  terminalRows.value = Number.isFinite(rows) ? rows : 32
  terminalCols.value = Number.isFinite(cols) ? cols : 120

  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }

  await openTerminalSession()
})

onBeforeUnmount(() => {
  resetTerminalState()
})
</script>

<template>
  <div class="page-grid">
    <section class="hero-panel">
      <div class="section-head">
        <div>
          <div class="eyebrow" style="color: var(--kb-primary-deep)">Terminal</div>
          <h2 class="page-title">容器终端</h2>
          <p class="page-description">独立页终端模式，支持直接进入容器并切换 `/bin/sh` 或 `/bin/bash`。</p>
        </div>
        <div class="button-row">
          <button class="button button-primary" :disabled="terminalConnecting" @click="switchShell('/bin/sh')">进入 /bin/sh</button>
          <button class="button button-secondary" :disabled="terminalConnecting" @click="switchShell('/bin/bash')">进入 /bin/bash</button>
          <button class="button button-secondary" :disabled="!terminalSession" @click="resetTerminalState()">断开终端</button>
        </div>
      </div>

      <div class="pill-row" style="margin-bottom: 12px">
        <span class="pill">集群: {{ selectedCluster?.name || clusterId || '--' }}</span>
        <span class="pill">Pod: {{ podName || '--' }}</span>
        <span class="pill">名称空间: {{ namespace || '--' }}</span>
        <span class="pill">Container: {{ containerName || 'auto' }}</span>
      </div>

      <div class="toolbar-grid terminal-toolbar">
        <label class="field-label">
          Shell
          <input :value="terminalShell" type="text" readonly />
        </label>
        <label class="field-label">
          Rows
          <input v-model.number="terminalRows" type="number" min="12" max="120" />
        </label>
        <label class="field-label">
          Cols
          <input v-model.number="terminalCols" type="number" min="40" max="240" />
        </label>
        <label class="field-label">
          Action
          <button class="button button-secondary" :disabled="!terminalSession" @click="resizeTerminal">应用尺寸</button>
        </label>
      </div>

      <div v-if="terminalSession" class="pill-row" style="margin-top: 12px">
        <span class="pill">Session: #{{ terminalSession.session.id }}</span>
        <span class="pill">Cursor: {{ terminalCursor }}</span>
        <span class="pill">状态: {{ terminalSession.session.status }}</span>
      </div>
    </section>

    <section class="surface-card log-panel">
      <div v-if="!pageReady" class="empty-state">缺少终端连接参数，无法建立终端会话。</div>
      <div v-else-if="terminalError" class="error-text">{{ terminalError }}</div>
      <div v-else-if="terminalConnecting && !terminalSession" class="empty-state">正在连接终端...</div>
      <pre class="json-block terminal-block">{{ terminalOutput || '$ terminal idle' }}</pre>

      <div class="toolbar-grid terminal-toolbar" style="margin-top: 14px">
        <label class="field-label" style="grid-column: span 2">
          Send Input
          <textarea
            v-model="terminalInput"
            placeholder="输入命令后点发送，例如：ls -la"
            :disabled="!terminalSession"
          />
        </label>

        <label class="field-label">
          Send
          <button
            class="button button-primary"
            :disabled="!terminalSession || terminalSending || !terminalInput.trim()"
            @click="submitTerminalInput"
          >
            {{ terminalSending ? '发送中...' : '发送命令' }}
          </button>
        </label>

        <label class="field-label">
          Shortcuts
          <div class="button-row">
            <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('enter')">
              Enter
            </button>
            <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('ctrlc')">
              Ctrl+C
            </button>
          </div>
        </label>
      </div>
    </section>
  </div>
</template>
