<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, apiRequest } from '../lib/api'
import { useClusterStore } from '../stores/clusters'
import type { PodLogsResponse, StreamSessionSummary } from '../types'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()

const logsResponse = ref<PodLogsResponse | null>(null)
const logsError = ref('')
const loadingLogs = ref(false)
const logsFollowing = ref(true)
const logFollowCursor = ref('')
const logFollowSession = ref<StreamSessionSummary | null>(null)
const selectedLogContainer = ref('')
const logTailLines = ref(200)
const logBlockRef = ref<HTMLElement | null>(null)

let logFollowLoopToken = 0
let logFollowTimer: number | null = null

const clusterId = computed(() => String(route.query.cluster || ''))
const podName = computed(() => String(route.query.pod || ''))
const namespace = computed(() => String(route.query.namespace || 'default'))
const initialContainer = computed(() => String(route.query.container || ''))
const selectedCluster = computed(() => clusterStore.items.find((cluster) => cluster.id === clusterId.value) ?? null)
const pageReady = computed(() => Boolean(clusterId.value && podName.value))
const canExportLogs = computed(() => Boolean(pageReady.value && logsResponse.value))
const podContextSummary = computed(
  () => `${selectedCluster.value?.name || clusterId.value || '--'} / ${namespace.value || '--'} / ${podName.value || '--'}`,
)

function clearLogFollowTimer() {
  if (logFollowTimer !== null) {
    window.clearTimeout(logFollowTimer)
    logFollowTimer = null
  }
}

function sanitizeFilenamePart(value: string) {
  const sanitized = value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '_')
    .replace(/\.+$/g, '')

  return sanitized || 'unknown'
}

function buildLogExportFilename() {
  const pad = (value: number) => String(value).padStart(2, '0')
  const now = new Date()
  const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  const containerName = logsResponse.value?.container || selectedLogContainer.value || 'auto'

  return [
    selectedCluster.value?.name || clusterId.value || 'cluster',
    namespace.value || 'default',
    podName.value || 'pod',
    containerName,
    timestamp,
  ]
    .map(sanitizeFilenamePart)
    .join('__')
}

function exportLogs() {
  if (!logsResponse.value) {
    return
  }

  const blob = new Blob([logsResponse.value.text || ''], { type: 'text/plain;charset=utf-8' })
  const downloadUrl = window.URL.createObjectURL(blob)
  const anchor = window.document.createElement('a')

  anchor.href = downloadUrl
  anchor.download = `${buildLogExportFilename()}.log`
  anchor.style.display = 'none'

  window.document.body.appendChild(anchor)
  anchor.click()

  window.setTimeout(() => {
    anchor.remove()
    window.URL.revokeObjectURL(downloadUrl)
  }, 0)
}

async function closeStreamSession(sessionId: number, statusValue = 'stopped') {
  try {
    await apiRequest(`/api/v1/streams/sessions/${sessionId}/close`, {
      method: 'POST',
      body: JSON.stringify({ status: statusValue }),
    })
  } catch {
    // ignore close failures for log viewer
  }
}

function mergeLogText(existingText: string, incomingText: string) {
  if (!incomingText.trim()) {
    return existingText
  }
  if (!existingText.trim()) {
    return incomingText
  }

  const existingLines = existingText.split('\n')
  const incomingLines = incomingText.split('\n')
  if (existingLines[existingLines.length - 1] === incomingLines[0]) {
    incomingLines.shift()
  }
  const suffix = incomingLines.join('\n')
  if (!suffix.trim()) {
    return existingText
  }
  return `${existingText.replace(/\n+$/, '')}\n${suffix}`
}

async function scrollLogsToBottom() {
  await nextTick()
  if (logBlockRef.value) {
    logBlockRef.value.scrollTop = logBlockRef.value.scrollHeight
  }
}

async function loadPodLogs(options: { follow?: boolean; append?: boolean } = {}) {
  if (!pageReady.value) {
    return
  }

  if (!options.append) {
    loadingLogs.value = true
  }
  if (!options.follow || !options.append) {
    logsError.value = ''
  }

  const query = new URLSearchParams({
    namespace: namespace.value,
    tail_lines: String(logTailLines.value),
    timestamps: 'true',
  })

  if (selectedLogContainer.value) {
    query.set('container', selectedLogContainer.value)
  }
  if (options.follow) {
    query.set('follow', 'true')
    const sinceTime = logFollowCursor.value || logsResponse.value?.cursor.since_time || ''
    if (sinceTime) {
      query.set('since_time', sinceTime)
    }
    if (logFollowSession.value) {
      query.set('session_id', String(logFollowSession.value.id))
    }
  }

  try {
    const payload = await apiRequest<PodLogsResponse>(
      `/api/v1/clusters/${clusterId.value}/resources/core/v1/pods/${encodeURIComponent(podName.value)}/logs?${query.toString()}`,
    )
    logsResponse.value =
      options.append && logsResponse.value
        ? {
            ...payload,
            text: mergeLogText(logsResponse.value.text, payload.text),
          }
        : payload
    logFollowCursor.value = payload.cursor.since_time || logFollowCursor.value
    logFollowSession.value = payload.session
    await scrollLogsToBottom()
  } catch (error) {
    if (!options.append) {
      logsResponse.value = null
    }
    if (error instanceof ApiError) {
      logsError.value = error.message
    } else {
      logsError.value = '日志读取失败。'
    }
    if (options.follow) {
      logsFollowing.value = false
      logFollowLoopToken += 1
      clearLogFollowTimer()
    }
  } finally {
    if (!options.append) {
      loadingLogs.value = false
    }
  }
}

async function runLogFollowLoop(loopToken: number, append = false) {
  if (!logsFollowing.value || loopToken !== logFollowLoopToken || !pageReady.value) {
    return
  }

  await loadPodLogs({ follow: true, append })

  if (logsFollowing.value && loopToken === logFollowLoopToken) {
    logFollowTimer = window.setTimeout(() => {
      void runLogFollowLoop(loopToken, true)
    }, 2200)
  }
}

function startLogFollowing() {
  if (!pageReady.value) {
    return
  }

  logsFollowing.value = true
  logsError.value = ''
  logFollowLoopToken += 1
  clearLogFollowTimer()
  logFollowCursor.value = logsResponse.value?.cursor.since_time || ''
  void runLogFollowLoop(logFollowLoopToken, Boolean(logsResponse.value))
}

function stopLogFollowing() {
  const sessionId = logFollowSession.value?.id ?? null
  logsFollowing.value = false
  logFollowLoopToken += 1
  clearLogFollowTimer()
  logFollowCursor.value = ''
  logFollowSession.value = null
  if (sessionId) {
    void closeStreamSession(sessionId)
  }
}

async function refreshLogs() {
  const shouldResumeFollowing = logsFollowing.value
  stopLogFollowing()
  logFollowCursor.value = ''
  await loadPodLogs()
  if (shouldResumeFollowing) {
    startLogFollowing()
  }
}

function toggleFollowing() {
  if (logsFollowing.value) {
    stopLogFollowing()
    return
  }
  startLogFollowing()
}

watch(
  [selectedLogContainer, logTailLines, logsFollowing],
  ([container, tailLines, follow]) => {
    if (!pageReady.value) {
      return
    }
    void router.replace({
      name: 'pod-logs',
      query: {
        cluster: clusterId.value,
        pod: podName.value,
        namespace: namespace.value,
        container: container || undefined,
        tail_lines: String(tailLines),
        follow: follow ? 'true' : 'false',
      },
    })
  },
)

onMounted(async () => {
  selectedLogContainer.value = initialContainer.value
  const tailLinesQuery = Number.parseInt(String(route.query.tail_lines || '200'), 10)
  logTailLines.value = Number.isFinite(tailLinesQuery) ? tailLinesQuery : 200
  logsFollowing.value = String(route.query.follow || 'true') !== 'false'

  if (!clusterStore.items.length) {
    await clusterStore.fetchClusters()
  }

  await loadPodLogs()
  if (logsFollowing.value) {
    startLogFollowing()
  }
})

onBeforeUnmount(() => {
  stopLogFollowing()
})
</script>

<template>
  <div class="page-grid page-grid-fill log-page-grid">
    <section class="surface-card log-panel">
      <div class="section-head log-panel-head">
        <div>
          <p class="helper-text">{{ podContextSummary }}</p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" :disabled="loadingLogs" @click="refreshLogs">
            {{ loadingLogs ? '读取中...' : '刷新日志' }}
          </button>
          <button class="button button-secondary" :disabled="!canExportLogs" @click="exportLogs">导出日志</button>
          <button class="button button-primary" :disabled="!pageReady" @click="toggleFollowing">
            {{ logsFollowing ? '停止追踪' : '开始追踪' }}
          </button>
        </div>
      </div>
      <div v-if="!pageReady" class="empty-state">缺少 Pod 日志所需的参数，无法加载日志。</div>
      <div v-else-if="logsError" class="error-text">{{ logsError }}</div>
      <div v-else-if="loadingLogs && !logsResponse" class="empty-state">正在读取日志...</div>
      <div v-else-if="logsFollowing" class="helper-text log-follow-hint">
        正在持续追踪最新日志输出，你可以随时停止追踪并手动刷新。
      </div>
      <div v-if="logsResponse" class="log-block-shell">
        <pre ref="logBlockRef" class="json-block log-block">{{ logsResponse.text || '// 当前没有日志输出' }}</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.log-page-grid {
  height: 100%;
  max-height: 100%;
  min-height: 0;
  grid-template-rows: minmax(0, 1fr);
  overflow: hidden;
}

.log-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  margin-top: 0;
  padding: 18px 18px 0;
  overflow: hidden;
}

.log-panel-head {
  align-items: center;
  margin-bottom: 2px;
}

.log-panel-head .helper-text,
.log-follow-hint {
  margin: 0;
}

.log-block-shell {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  border-radius: 0;
  margin-bottom: -12px;
}

.log-block {
  flex: 1 1 auto;
  height: auto;
  min-height: 0;
  max-height: none;
  border-radius: 0;
}
</style>
