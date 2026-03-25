<script setup lang="ts">
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { TerminalOutputResponse, TerminalSessionResponse } from '../types'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()

const terminalSession = ref<TerminalSessionResponse | null>(null)
const terminalError = ref('')
const terminalConnecting = ref(false)
const terminalSending = ref(false)
const terminalCursor = ref(0)
const terminalShell = ref<'/bin/sh' | '/bin/bash'>('/bin/sh')
const terminalRows = ref(32)
const terminalCols = ref(120)
const terminalViewport = ref<HTMLElement | null>(null)
const terminalHost = ref<HTMLElement | null>(null)

const clusterId = computed(() => String(route.query.cluster || ''))
const podName = computed(() => String(route.query.pod || ''))
const namespace = computed(() => String(route.query.namespace || 'default'))
const containerName = computed(() => String(route.query.container || ''))
const selectedCluster = computed(() => clusterStore.items.find((cluster) => cluster.id === clusterId.value) ?? null)
const pageReady = computed(() => Boolean(clusterId.value && podName.value))
const terminalStatusText = computed(() => {
  if (terminalConnecting.value) {
    return '连接中'
  }
  if (terminalError.value) {
    return '连接异常'
  }
  if (terminalSession.value) {
    return terminalSession.value.session.status === 'running' ? '已连接' : '已断开'
  }
  return '未连接'
})

let terminalLoopToken = 0
let terminalPollTimer: number | null = null
let writeQueue = ''
let flushingInput = false
let resizeTimer: number | null = null
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

function clearTerminalPollTimer() {
  if (terminalPollTimer !== null) {
    window.clearTimeout(terminalPollTimer)
    terminalPollTimer = null
  }
}

function clearResizeTimer() {
  if (resizeTimer !== null) {
    window.clearTimeout(resizeTimer)
    resizeTimer = null
  }
}

function focusTerminal() {
  terminal?.focus()
}

function createTerminal() {
  if (!terminalHost.value) {
    return
  }

  terminal = new Terminal({
    cursorBlink: true,
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace',
    fontSize: 15,
    lineHeight: 1.2,
    convertEol: true,
    scrollback: 3000,
    theme: {
      background: '#1e1d47',
      foreground: '#fff1e2',
      cursor: '#8aff80',
      cursorAccent: '#1e1d47',
      selectionBackground: 'rgba(140, 182, 255, 0.28)',
      black: '#171531',
      red: '#ff8e8e',
      green: '#85ff76',
      yellow: '#ffd37b',
      blue: '#7eb6ff',
      magenta: '#f2a7ff',
      cyan: '#8ef2ff',
      white: '#f7f3e9',
      brightBlack: '#58527a',
      brightRed: '#ffb1b1',
      brightGreen: '#b4ffad',
      brightYellow: '#ffe6a8',
      brightBlue: '#aacfff',
      brightMagenta: '#ffc5ff',
      brightCyan: '#b6f8ff',
      brightWhite: '#ffffff',
    },
  })

  fitAddon = new FitAddon()
  terminal.loadAddon(fitAddon)
  terminal.open(terminalHost.value)
  terminal.onData((data) => {
    queueTerminalInput(data)
  })
  terminal.onResize(({ rows, cols }) => {
    terminalRows.value = rows
    terminalCols.value = cols
    if (terminalSession.value) {
      void resizeTerminal()
    }
  })
  terminal.focus()
}

function disposeTerminal() {
  resizeObserver?.disconnect()
  resizeObserver = null
  terminal?.dispose()
  terminal = null
  fitAddon = null
}

function writeTerminal(text: string) {
  if (!terminal || !text) {
    return
  }
  terminal.write(text)
}

function clearTerminalScreen() {
  terminal?.clear()
  terminal?.reset()
}

function fitTerminal() {
  if (!terminal || !fitAddon) {
    return
  }
  fitAddon.fit()
  terminalRows.value = terminal.rows
  terminalCols.value = terminal.cols
}

function scheduleResize() {
  clearResizeTimer()
  resizeTimer = window.setTimeout(() => {
    fitTerminal()
    if (terminalSession.value) {
      void resizeTerminal()
    }
  }, 120)
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
  terminalError.value = ''
  terminalConnecting.value = false
  terminalSending.value = false
  terminalCursor.value = 0
  writeQueue = ''
  flushingInput = false
  clearTerminalScreen()
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
      writeTerminal(payload.text)
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
      if (payload.exit_code !== null) {
        writeTerminal(`\r\n[session closed: exit ${payload.exit_code}]\r\n`)
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
    }, 300)
  }
}

async function openTerminalSession() {
  if (!pageReady.value) {
    return
  }

  resetTerminalState()
  clearTerminalScreen()
  fitTerminal()
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
    terminalRows.value = terminalSession.value.terminal.rows
    terminalCols.value = terminalSession.value.terminal.cols
    terminalCursor.value = terminalSession.value.cursor || 0
    if (terminalSession.value.text) {
      writeTerminal(terminalSession.value.text)
    }
    terminalLoopToken += 1
    void nextTick(() => {
      fitTerminal()
      focusTerminal()
    })
    void pollTerminalOutput(terminalLoopToken)
  } catch (error) {
    terminalSession.value = null
    if (error instanceof ApiError) {
      terminalError.value = error.message
      writeTerminal(`\r\n[error] ${error.message}\r\n`)
    } else {
      terminalError.value = '终端建立失败。'
      writeTerminal('\r\n[error] 终端建立失败。\r\n')
    }
  } finally {
    terminalConnecting.value = false
  }
}

async function flushTerminalInputQueue() {
  if (!terminalSession.value || !writeQueue || flushingInput) {
    return
  }

  flushingInput = true
  while (terminalSession.value && writeQueue) {
    const payload = writeQueue
    writeQueue = ''
    terminalSending.value = true
    terminalError.value = ''
    try {
      await apiRequest(`/api/v1/streams/sessions/${terminalSession.value.session.id}/input`, {
        method: 'POST',
        body: JSON.stringify({ input: payload }),
      })
    } catch (error) {
      if (error instanceof ApiError) {
        terminalError.value = error.message
        writeTerminal(`\r\n[input error] ${error.message}\r\n`)
      } else {
        terminalError.value = '终端输入发送失败。'
        writeTerminal('\r\n[input error] 终端输入发送失败。\r\n')
      }
      writeQueue = ''
      break
    } finally {
      terminalSending.value = false
    }
  }
  flushingInput = false
}

function queueTerminalInput(data: string) {
  if (!terminalSession.value || !data) {
    return
  }
  writeQueue += data
  void flushTerminalInputQueue()
}

async function sendTerminalShortcut(shortcut: 'ctrlc') {
  queueTerminalInput(shortcut === 'ctrlc' ? '\u0003' : '')
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

onMounted(async () => {
  const shell = String(route.query.shell || '/bin/sh')
  terminalShell.value = shell === '/bin/bash' ? '/bin/bash' : '/bin/sh'

  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }

  await nextTick()
  createTerminal()
  fitTerminal()
  resizeObserver = new ResizeObserver(() => {
    scheduleResize()
  })
  if (terminalViewport.value) {
    resizeObserver.observe(terminalViewport.value)
  }
  window.addEventListener('resize', scheduleResize)
  await openTerminalSession()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', scheduleResize)
  clearResizeTimer()
  resetTerminalState()
  disposeTerminal()
})
</script>

<template>
  <div class="terminal-page">
    <header class="terminal-topbar">
      <div class="terminal-title-block">
        <div class="terminal-title">{{ namespace || 'default' }} / {{ podName || '--' }} {{ containerName || 'auto' }} 控制台</div>
        <div class="terminal-subtitle">
          集群 {{ selectedCluster?.name || clusterId || '--' }} · Shell {{ terminalShell }} · {{ terminalRows }} x {{ terminalCols }}
        </div>
      </div>
      <div class="terminal-actions">
        <button class="button button-secondary" :disabled="terminalConnecting" @click="switchShell('/bin/sh')">切换到 sh</button>
        <button class="button button-secondary" :disabled="terminalConnecting" @click="switchShell('/bin/bash')">切换到 bash</button>
        <button class="button button-secondary" :disabled="!terminalSession" @click="resetTerminalState()">断开</button>
      </div>
      <div class="terminal-status" :class="{ 'terminal-status-error': !!terminalError }">{{ terminalStatusText }}</div>
    </header>

    <main ref="terminalViewport" class="terminal-viewport" @click="focusTerminal">
      <div v-if="!pageReady" class="terminal-overlay">缺少终端连接参数，无法建立终端会话。</div>
      <div v-else-if="terminalError" class="terminal-overlay terminal-overlay-error">{{ terminalError }}</div>
      <div v-else-if="terminalConnecting && !terminalSession" class="terminal-overlay">正在连接容器终端...</div>
      <div ref="terminalHost" class="terminal-host" />
    </main>

    <footer class="terminal-footer">
      <span>标准 Web Terminal 已启用</span>
      <span>支持 ANSI、光标、键盘输入、粘贴和自适应尺寸</span>
      <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('ctrlc')">
        发送 Ctrl+C
      </button>
    </footer>
  </div>
</template>
