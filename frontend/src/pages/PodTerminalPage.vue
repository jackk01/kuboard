<script setup lang="ts">
import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { TerminalOutputResponse, TerminalSessionResponse } from '../types'

type TerminalThemeColors = {
  background: string
  foreground: string
  cursor: string
  cursorAccent: string
  selectionBackground: string
  black: string
  red: string
  green: string
  yellow: string
  blue: string
  magenta: string
  cyan: string
  white: string
  brightBlack: string
  brightRed: string
  brightGreen: string
  brightYellow: string
  brightBlue: string
  brightMagenta: string
  brightCyan: string
  brightWhite: string
}

type TerminalThemePreset = {
  id: string
  label: string
  description: string
  page: {
    pageBackground: string
    pageForeground: string
    panelBackground: string
    panelBorder: string
    titleColor: string
    subtitleColor: string
    footerColor: string
    statusColor: string
    statusErrorColor: string
    viewportBackground: string
    overlayBackground: string
    overlayBorder: string
    overlayForeground: string
    overlayErrorBackground: string
    overlayErrorForeground: string
    controlBackground: string
    controlForeground: string
    controlBorder: string
    controlFocus: string
  }
  terminal: TerminalThemeColors
}

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const TERMINAL_OUTPUT_WAIT_MS = 1000
const TERMINAL_INPUT_BATCH_DELAY_MS = 16
const TERMINAL_THEME_STORAGE_KEY = 'kuboard-terminal-theme'
type TerminalShell = 'auto' | '/bin/sh' | '/bin/bash'
const terminalThemePresets: TerminalThemePreset[] = [
  {
    id: 'graphite',
    label: 'Graphite',
    description: '冷静深海蓝，适合长时间排障。',
    page: {
      pageBackground: 'radial-gradient(circle at top right, rgba(56, 189, 248, 0.08), transparent 24%), linear-gradient(180deg, #08111f 0%, #0b1524 100%)',
      pageForeground: '#dce7f5',
      panelBackground: 'rgba(8, 17, 31, 0.88)',
      panelBorder: 'rgba(148, 163, 184, 0.12)',
      titleColor: '#f8fafc',
      subtitleColor: 'rgba(215, 227, 244, 0.72)',
      footerColor: 'rgba(215, 227, 244, 0.72)',
      statusColor: '#4ade80',
      statusErrorColor: '#fca5a5',
      viewportBackground: 'transparent',
      overlayBackground: 'rgba(8, 17, 31, 0.82)',
      overlayBorder: 'rgba(148, 163, 184, 0.14)',
      overlayForeground: '#f8fafc',
      overlayErrorBackground: 'rgba(74, 14, 20, 0.88)',
      overlayErrorForeground: '#ffd3d3',
      controlBackground: 'rgba(15, 23, 42, 0.78)',
      controlForeground: '#e2e8f0',
      controlBorder: 'rgba(148, 163, 184, 0.22)',
      controlFocus: 'rgba(103, 232, 249, 0.36)',
    },
    terminal: {
      background: '#08111f',
      foreground: '#d7e3f4',
      cursor: '#67e8f9',
      cursorAccent: '#08111f',
      selectionBackground: 'rgba(56, 189, 248, 0.24)',
      black: '#0b1220',
      red: '#f87171',
      green: '#4ade80',
      yellow: '#fbbf24',
      blue: '#60a5fa',
      magenta: '#f472b6',
      cyan: '#67e8f9',
      white: '#d7e3f4',
      brightBlack: '#475569',
      brightRed: '#fca5a5',
      brightGreen: '#86efac',
      brightYellow: '#fde68a',
      brightBlue: '#93c5fd',
      brightMagenta: '#f9a8d4',
      brightCyan: '#a5f3fc',
      brightWhite: '#f8fafc',
    },
  },
  {
    id: 'aurora',
    label: 'Aurora',
    description: '偏绿的极光风格，回显对比更鲜明。',
    page: {
      pageBackground: 'radial-gradient(circle at top left, rgba(16, 185, 129, 0.18), transparent 30%), radial-gradient(circle at top right, rgba(34, 211, 238, 0.16), transparent 26%), linear-gradient(180deg, #041714 0%, #07211c 100%)',
      pageForeground: '#dcfce7',
      panelBackground: 'rgba(4, 23, 20, 0.84)',
      panelBorder: 'rgba(110, 231, 183, 0.18)',
      titleColor: '#f0fdf4',
      subtitleColor: 'rgba(209, 250, 229, 0.74)',
      footerColor: 'rgba(209, 250, 229, 0.74)',
      statusColor: '#34d399',
      statusErrorColor: '#fca5a5',
      viewportBackground: 'transparent',
      overlayBackground: 'rgba(4, 23, 20, 0.84)',
      overlayBorder: 'rgba(110, 231, 183, 0.18)',
      overlayForeground: '#f0fdf4',
      overlayErrorBackground: 'rgba(87, 24, 29, 0.9)',
      overlayErrorForeground: '#ffe4e6',
      controlBackground: 'rgba(6, 30, 26, 0.76)',
      controlForeground: '#dcfce7',
      controlBorder: 'rgba(110, 231, 183, 0.24)',
      controlFocus: 'rgba(52, 211, 153, 0.34)',
    },
    terminal: {
      background: '#061917',
      foreground: '#d1fae5',
      cursor: '#6ee7b7',
      cursorAccent: '#061917',
      selectionBackground: 'rgba(45, 212, 191, 0.24)',
      black: '#03100f',
      red: '#fb7185',
      green: '#34d399',
      yellow: '#fbbf24',
      blue: '#38bdf8',
      magenta: '#fb7185',
      cyan: '#2dd4bf',
      white: '#d1fae5',
      brightBlack: '#3f5f5a',
      brightRed: '#fda4af',
      brightGreen: '#86efac',
      brightYellow: '#fde68a',
      brightBlue: '#7dd3fc',
      brightMagenta: '#fbcfe8',
      brightCyan: '#99f6e4',
      brightWhite: '#f0fdf4',
    },
  },
  {
    id: 'ember',
    label: 'Ember',
    description: '炉火琥珀色，适合夜间值守。',
    page: {
      pageBackground: 'radial-gradient(circle at top right, rgba(251, 191, 36, 0.16), transparent 26%), radial-gradient(circle at top left, rgba(249, 115, 22, 0.14), transparent 32%), linear-gradient(180deg, #1a1209 0%, #24160c 100%)',
      pageForeground: '#fff1da',
      panelBackground: 'rgba(28, 18, 9, 0.84)',
      panelBorder: 'rgba(251, 191, 36, 0.2)',
      titleColor: '#fff7ed',
      subtitleColor: 'rgba(254, 243, 199, 0.74)',
      footerColor: 'rgba(254, 243, 199, 0.74)',
      statusColor: '#fbbf24',
      statusErrorColor: '#fecaca',
      viewportBackground: 'transparent',
      overlayBackground: 'rgba(28, 18, 9, 0.84)',
      overlayBorder: 'rgba(251, 191, 36, 0.2)',
      overlayForeground: '#fff7ed',
      overlayErrorBackground: 'rgba(92, 28, 17, 0.9)',
      overlayErrorForeground: '#ffe4e6',
      controlBackground: 'rgba(41, 24, 11, 0.76)',
      controlForeground: '#ffedd5',
      controlBorder: 'rgba(251, 191, 36, 0.26)',
      controlFocus: 'rgba(251, 191, 36, 0.34)',
    },
    terminal: {
      background: '#1b1208',
      foreground: '#ffe7c2',
      cursor: '#fbbf24',
      cursorAccent: '#1b1208',
      selectionBackground: 'rgba(251, 191, 36, 0.2)',
      black: '#120b05',
      red: '#fb7185',
      green: '#a3e635',
      yellow: '#fbbf24',
      blue: '#f59e0b',
      magenta: '#fb923c',
      cyan: '#f97316',
      white: '#ffe7c2',
      brightBlack: '#6b4d2f',
      brightRed: '#fecaca',
      brightGreen: '#d9f99d',
      brightYellow: '#fde68a',
      brightBlue: '#fdba74',
      brightMagenta: '#fed7aa',
      brightCyan: '#fdba74',
      brightWhite: '#fff7ed',
    },
  },
  {
    id: 'paper',
    label: 'Paper',
    description: '浅色纸面风格，白天查看更轻松。',
    page: {
      pageBackground: 'radial-gradient(circle at top left, rgba(45, 212, 191, 0.1), transparent 28%), linear-gradient(180deg, #f8faf7 0%, #eef6f1 100%)',
      pageForeground: '#24323e',
      panelBackground: 'rgba(255, 255, 255, 0.84)',
      panelBorder: 'rgba(148, 163, 184, 0.24)',
      titleColor: '#0f172a',
      subtitleColor: 'rgba(51, 65, 85, 0.76)',
      footerColor: 'rgba(51, 65, 85, 0.76)',
      statusColor: '#0f766e',
      statusErrorColor: '#b91c1c',
      viewportBackground: 'transparent',
      overlayBackground: 'rgba(255, 255, 255, 0.88)',
      overlayBorder: 'rgba(148, 163, 184, 0.24)',
      overlayForeground: '#0f172a',
      overlayErrorBackground: 'rgba(254, 226, 226, 0.94)',
      overlayErrorForeground: '#991b1b',
      controlBackground: 'rgba(248, 250, 252, 0.94)',
      controlForeground: '#1e293b',
      controlBorder: 'rgba(148, 163, 184, 0.3)',
      controlFocus: 'rgba(20, 184, 166, 0.24)',
    },
    terminal: {
      background: '#fffdf7',
      foreground: '#24323e',
      cursor: '#0f766e',
      cursorAccent: '#fffdf7',
      selectionBackground: 'rgba(20, 184, 166, 0.18)',
      black: '#334155',
      red: '#dc2626',
      green: '#15803d',
      yellow: '#b45309',
      blue: '#0369a1',
      magenta: '#be185d',
      cyan: '#0f766e',
      white: '#64748b',
      brightBlack: '#94a3b8',
      brightRed: '#ef4444',
      brightGreen: '#22c55e',
      brightYellow: '#f59e0b',
      brightBlue: '#0ea5e9',
      brightMagenta: '#ec4899',
      brightCyan: '#14b8a6',
      brightWhite: '#0f172a',
    },
  },
]

function getTerminalTheme(themeId: string) {
  return terminalThemePresets.find((theme) => theme.id === themeId) ?? terminalThemePresets[0]
}

function readStoredTerminalTheme() {
  if (typeof window === 'undefined') {
    return terminalThemePresets[0].id
  }
  const storedThemeId = window.localStorage.getItem(TERMINAL_THEME_STORAGE_KEY) || ''
  return getTerminalTheme(storedThemeId).id
}

const terminalSession = ref<TerminalSessionResponse | null>(null)
const terminalError = ref('')
const terminalConnecting = ref(false)
const terminalSending = ref(false)
const terminalCursor = ref(0)
const terminalShell = ref<TerminalShell>('auto')
const terminalRows = ref(32)
const terminalCols = ref(120)
const terminalViewport = ref<HTMLElement | null>(null)
const terminalHost = ref<HTMLElement | null>(null)
const terminalThemeId = ref(readStoredTerminalTheme())

const clusterId = computed(() => String(route.query.cluster || ''))
const podName = computed(() => String(route.query.pod || ''))
const namespace = computed(() => String(route.query.namespace || 'default'))
const containerName = computed(() => String(route.query.container || ''))
const selectedCluster = computed(() => clusterStore.items.find((cluster) => cluster.id === clusterId.value) ?? null)
const currentTerminalTheme = computed(() => getTerminalTheme(terminalThemeId.value))
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
const terminalPageStyle = computed(() => ({
  '--terminal-page-background': currentTerminalTheme.value.page.pageBackground,
  '--terminal-page-foreground': currentTerminalTheme.value.page.pageForeground,
  '--terminal-panel-background': currentTerminalTheme.value.page.panelBackground,
  '--terminal-panel-border': currentTerminalTheme.value.page.panelBorder,
  '--terminal-title-color': currentTerminalTheme.value.page.titleColor,
  '--terminal-subtitle-color': currentTerminalTheme.value.page.subtitleColor,
  '--terminal-footer-color': currentTerminalTheme.value.page.footerColor,
  '--terminal-status-color': currentTerminalTheme.value.page.statusColor,
  '--terminal-status-error-color': currentTerminalTheme.value.page.statusErrorColor,
  '--terminal-viewport-background': currentTerminalTheme.value.page.viewportBackground,
  '--terminal-overlay-background': currentTerminalTheme.value.page.overlayBackground,
  '--terminal-overlay-border': currentTerminalTheme.value.page.overlayBorder,
  '--terminal-overlay-foreground': currentTerminalTheme.value.page.overlayForeground,
  '--terminal-overlay-error-background': currentTerminalTheme.value.page.overlayErrorBackground,
  '--terminal-overlay-error-foreground': currentTerminalTheme.value.page.overlayErrorForeground,
  '--terminal-control-background': currentTerminalTheme.value.page.controlBackground,
  '--terminal-control-foreground': currentTerminalTheme.value.page.controlForeground,
  '--terminal-control-border': currentTerminalTheme.value.page.controlBorder,
  '--terminal-control-focus': currentTerminalTheme.value.page.controlFocus,
}))

let terminalLoopToken = 0
let terminalPollTimer: number | null = null
let writeQueue = ''
let flushingInput = false
let resizeTimer: number | null = null
let inputFlushTimer: number | null = null
let terminal: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

function applyTerminalTheme() {
  if (!terminal) {
    return
  }
  terminal.options.theme = { ...currentTerminalTheme.value.terminal }
  if (terminal.rows > 0) {
    terminal.refresh(0, terminal.rows - 1)
  }
}

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

function clearInputFlushTimer() {
  if (inputFlushTimer !== null) {
    window.clearTimeout(inputFlushTimer)
    inputFlushTimer = null
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
    theme: { ...currentTerminalTheme.value.terminal },
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
  clearInputFlushTimer()
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
      `/api/v1/streams/sessions/${terminalSession.value.session.id}/output?cursor=${terminalCursor.value}&wait_ms=${TERMINAL_OUTPUT_WAIT_MS}`,
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
    }, 0)
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

  clearInputFlushTimer()
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

function scheduleTerminalInputFlush() {
  if (inputFlushTimer !== null) {
    return
  }
  inputFlushTimer = window.setTimeout(() => {
    inputFlushTimer = null
    void flushTerminalInputQueue()
  }, TERMINAL_INPUT_BATCH_DELAY_MS)
}

function queueTerminalInput(data: string, options: { immediate?: boolean } = {}) {
  if (!terminalSession.value || !data) {
    return
  }
  writeQueue += data
  if (options.immediate) {
    void flushTerminalInputQueue()
    return
  }
  scheduleTerminalInputFlush()
}

async function sendTerminalShortcut(shortcut: 'ctrlc') {
  queueTerminalInput(shortcut === 'ctrlc' ? '\u0003' : '', { immediate: true })
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

async function switchShell(shell: TerminalShell) {
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

watch(terminalThemeId, (nextThemeId) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(TERMINAL_THEME_STORAGE_KEY, getTerminalTheme(nextThemeId).id)
  }
  applyTerminalTheme()
})

onMounted(async () => {
  const shell = String(route.query.shell || 'auto')
  terminalShell.value = shell === '/bin/bash' || shell === '/bin/sh' ? shell : 'auto'

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
  clearInputFlushTimer()
  resetTerminalState()
  disposeTerminal()
})
</script>

<template>
  <div class="terminal-page" :style="terminalPageStyle">
    <header class="terminal-topbar">
      <div class="terminal-title-block">
        <div class="terminal-title">{{ namespace || 'default' }} / {{ podName || '--' }} {{ containerName || 'auto' }} 控制台</div>
        <div class="terminal-subtitle">
          集群 {{ selectedCluster?.name || clusterId || '--' }} · Shell {{ terminalShell }} · {{ terminalRows }} x {{ terminalCols }} · 主题 {{ currentTerminalTheme.label }}
        </div>
      </div>
      <div class="terminal-actions">
        <label class="terminal-theme-field">
          <span>主题</span>
          <select v-model="terminalThemeId" class="terminal-theme-select">
            <option v-for="theme in terminalThemePresets" :key="theme.id" :value="theme.id">
              {{ theme.label }}
            </option>
          </select>
        </label>
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
      <span>支持 ANSI、光标、键盘输入、粘贴和自适应尺寸 · {{ currentTerminalTheme.description }}</span>
      <button class="button button-secondary" :disabled="!terminalSession || terminalSending" @click="sendTerminalShortcut('ctrlc')">
        发送 Ctrl+C
      </button>
    </footer>
  </div>
</template>
