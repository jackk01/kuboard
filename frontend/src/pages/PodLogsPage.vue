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

function clearLogFollowTimer() {
  if (logFollowTimer !== null) {
    window.clearTimeout(logFollowTimer)
    logFollowTimer = null
  }
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
  <div class="page-grid">
    <section class="hero-panel">
      <div class="section-head">
        <div>
          <div class="eyebrow" style="color: var(--kb-primary-deep)">Pod Logs</div>
          <h2 class="page-title">Pod 日志</h2>
          <p class="page-description">
            新页签日志视图默认开启追踪模式，你可以随时暂停追踪或调整单次输出行数。
          </p>
        </div>
        <div class="button-row">
          <button class="button button-secondary" :disabled="loadingLogs" @click="refreshLogs">
            {{ loadingLogs ? '读取中...' : '刷新日志' }}
          </button>
          <button class="button button-primary" :disabled="!pageReady" @click="toggleFollowing">
            {{ logsFollowing ? '停止追踪' : '开始追踪' }}
          </button>
        </div>
      </div>

      <div class="pill-row" style="margin-bottom: 12px">
        <span class="pill">集群: {{ selectedCluster?.name || clusterId || '--' }}</span>
        <span class="pill">Pod: {{ podName || '--' }}</span>
        <span class="pill">名称空间: {{ namespace || '--' }}</span>
        <span class="pill">状态: {{ logsFollowing ? 'following' : 'idle' }}</span>
      </div>

      <div class="toolbar-grid logs-toolbar">
        <label class="field-label">
          Container
          <input v-model="selectedLogContainer" type="text" placeholder="留空则自动选择" />
        </label>

        <label class="field-label">
          Tail Lines
          <input v-model.number="logTailLines" type="number" min="10" max="2000" />
        </label>
      </div>

      <div v-if="logsResponse || logFollowSession" class="pill-row" style="margin-top: 12px">
        <span class="pill">Cursor: {{ logFollowCursor || logsResponse?.cursor.since_time || '--' }}</span>
        <span class="pill">Lines: {{ logTailLines }}</span>
        <span class="pill" v-if="logFollowSession">Session: #{{ logFollowSession.id }}</span>
      </div>
    </section>

    <section class="surface-card log-panel">
      <div v-if="!pageReady" class="empty-state">缺少 Pod 日志所需的参数，无法加载日志。</div>
      <div v-else-if="logsError" class="error-text">{{ logsError }}</div>
      <div v-else-if="loadingLogs && !logsResponse" class="empty-state">正在读取日志...</div>
      <div v-else-if="logsFollowing" class="helper-text" style="margin-bottom: 12px">
        正在持续追踪最新日志输出，你可以随时停止追踪并手动刷新。
      </div>
      <pre v-if="logsResponse" ref="logBlockRef" class="json-block log-block">{{ logsResponse.text || '// 当前没有日志输出' }}</pre>
    </section>
  </div>
</template>
