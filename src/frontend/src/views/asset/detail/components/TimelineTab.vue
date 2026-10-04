<!--
  资产统一事件时间线（OH-P0.T4 · 底座 P0）
  消费 GET /api/v1/assets/{id}/timeline（PG/OpenSearch/Loki 联邦查询）
  展示：源状态条 + 类型筛选 + 竖向时间线（按类型图标/严重度染色）+ cursor 加载更多
-->
<template>
  <div class="timeline-tab">
    <!-- 工具条：类型筛选 + 刷新 -->
    <div class="timeline-tab__toolbar">
      <ElCheckboxGroup
        :model-value="activeTypes"
        size="small"
        @change="onTypeChange"
      >
        <ElCheckbox
          v-for="t in TYPE_OPTIONS"
          :key="t.value"
          :value="t.value"
        >
          {{ t.label }}
        </ElCheckbox>
      </ElCheckboxGroup>
      <ElButton text size="small" :loading="loading" @click="reload">
        <ElIcon><Refresh /></ElIcon>&nbsp;刷新
      </ElButton>
    </div>

    <!-- 数据源状态 -->
    <div v-if="sourceEntries.length" class="timeline-tab__sources">
      <ElTag
        v-for="entry in sourceEntries"
        :key="entry.key"
        :type="sourceTagType(entry.state)"
        size="small"
        effect="plain"
      >
        {{ sourceLabel(entry.key) }} · {{ sourceStateLabel(entry.state) }}
      </ElTag>
      <span v-if="coverageNote" class="timeline-tab__coverage">{{ coverageNote }}</span>
    </div>

    <!-- 时间线主体 -->
    <ElTimeline v-loading="loading" class="timeline-tab__list">
      <ElTimelineItem
        v-for="ev in events"
        :key="ev.event_id"
        :timestamp="formatTs(ev.ts)"
        placement="top"
        :type="dotType(ev)"
        :hollow="!ev.severity"
      >
        <template #dot>
          <span class="tl-dot" :class="`tl-dot--${ev.event_type}`">
            <ElIcon><component :is="typeIcon(ev.event_type)" /></ElIcon>
          </span>
        </template>

        <div class="tl-item">
          <div class="tl-item__head">
            <ElTag size="small" :type="severityTagType(ev.severity)" effect="light">
              {{ typeLabel(ev.event_type) }}
            </ElTag>
            <span class="tl-item__source">{{ sourceLabel(ev.source) }}</span>
            <span v-if="ev.severity != null" class="tl-item__sev">
              分级 {{ ev.severity }}
            </span>
          </div>
          <p v-if="ev.summary" class="tl-item__summary">{{ ev.summary }}</p>
          <pre v-if="hasPayload(ev)" class="tl-item__payload">{{ formatPayload(ev.payload) }}</pre>
          <a v-if="ev.raw_ref" class="tl-item__ref" :title="ev.raw_ref">
            {{ truncate(ev.raw_ref) }}
          </a>
        </div>
      </ElTimelineItem>
    </ElTimeline>

    <!-- 空态 -->
    <div v-if="!loading && !events.length" class="timeline-tab__empty">
      <ElIcon class="empty-icon"><Timer /></ElIcon>
      <p>所选时间范围内暂无事件</p>
    </div>

    <!-- 加载更多 -->
    <div v-if="nextCursor" class="timeline-tab__more">
      <ElButton size="small" :loading="loadingMore" @click="loadMore">
        加载更多
      </ElButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Aim,
  Document,
  EditPen,
  Key,
  MagicStick,
  Refresh,
  Timer,
  User,
  Warning
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getAssetTimeline,
  type AssetTimelineEvent,
  type AssetTimelineEventType
} from '@/api/asset'

const props = defineProps<{ assetId: string }>()

const PAGE_LIMIT = 100

const TYPE_OPTIONS: { value: AssetTimelineEventType; label: string }[] = [
  { value: 'alert', label: '告警' },
  { value: 'log', label: '日志' },
  { value: 'change', label: '变更' },
  { value: 'vuln', label: '漏洞' },
  { value: 'identity', label: '身份' },
  { value: 'behavior', label: '行为' }
]

const events = ref<AssetTimelineEvent[]>([])
const nextCursor = ref<string | null>(null)
const sourceStatus = ref<Record<string, string>>({})
const coverageNote = ref('')
const activeTypes = ref<AssetTimelineEventType[]>([])
const loading = ref(false)
const loadingMore = ref(false)

const sourceEntries = computed(() =>
  Object.entries(sourceStatus.value).map(([key, state]) => ({ key, state }))
)

async function fetchTimeline(cursor?: string) {
  const types = activeTypes.value.length ? activeTypes.value : undefined
  return getAssetTimeline(props.assetId, {
    types,
    limit: PAGE_LIMIT,
    cursor
  })
}

async function reload() {
  loading.value = true
  try {
    const res = await fetchTimeline()
    applyResponse(res, false)
  } catch (e: any) {
    ElMessage.error(e?.message || '时间线加载失败')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!nextCursor.value) return
  loadingMore.value = true
  try {
    const res = await fetchTimeline(nextCursor.value)
    applyResponse(res, true)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载更多失败')
  } finally {
    loadingMore.value = false
  }
}

function applyResponse(
  res: any,
  append: boolean
) {
  // axios 拦截器返回 envelope.data；兼容两种形态
  const data = res?.data ?? res
  const incoming: AssetTimelineEvent[] = data?.events ?? []
  events.value = append ? [...events.value, ...incoming] : incoming
  nextCursor.value = data?.next_cursor ?? null
  sourceStatus.value = data?.source_status ?? {}
  coverageNote.value = data?.coverage_note ?? ''
}

function onTypeChange(val: AssetTimelineEventType[] | unknown) {
  activeTypes.value = (val as AssetTimelineEventType[]) ?? []
  reload()
}

/* ---------- 展示辅助 ---------- */

function typeIcon(t: AssetTimelineEventType) {
  switch (t) {
    case 'alert':
      return Warning
    case 'log':
      return Document
    case 'change':
      return EditPen
    case 'vuln':
      return Aim
    case 'identity':
      return Key
    case 'behavior':
      return User
    default:
      return MagicStick
  }
}

function typeLabel(t: AssetTimelineEventType) {
  return TYPE_OPTIONS.find((x) => x.value === t)?.label ?? t
}

const SOURCE_LABELS: Record<string, string> = {
  postgres: 'PG',
  opensearch: 'OpenSearch',
  loki: 'Loki'
}

function sourceLabel(key: string) {
  return SOURCE_LABELS[key] ?? key
}

function sourceStateLabel(state: string) {
  if (state === 'ok') return '正常'
  if (state === 'degraded') return '降级'
  if (state === 'unavailable') return '不可达'
  return state
}

function sourceTagType(state: string): 'success' | 'warning' | 'info' {
  if (state === 'ok') return 'success'
  if (state === 'degraded') return 'warning'
  return 'info'
}

// 严重度 → 标签色（对齐 alert_levels：critical/high 高危）
function severityTagType(sev?: number | null): 'danger' | 'warning' | 'info' {
  if (sev == null) return 'info'
  if (sev >= 10) return 'danger'
  if (sev >= 7) return 'warning'
  return 'info'
}

function dotType(ev: AssetTimelineEvent): 'primary' | 'danger' | 'warning' | 'info' {
  if (ev.severity != null) {
    if (ev.severity >= 10) return 'danger'
    if (ev.severity >= 7) return 'warning'
  }
  return 'primary'
}

function formatTs(ts: string) {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function hasPayload(ev: AssetTimelineEvent) {
  return ev.payload && Object.keys(ev.payload).length > 0
}

function formatPayload(payload: Record<string, any>) {
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return ''
  }
}

function truncate(s: string, n = 60) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

onMounted(reload)
</script>

<style scoped>
.timeline-tab__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.timeline-tab__sources {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}

.timeline-tab__coverage {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.timeline-tab__list {
  padding-left: 4px;
}

.tl-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
}

.tl-dot--alert {
  background: var(--el-color-danger);
}
.tl-dot--vuln {
  background: var(--el-color-danger);
}
.tl-dot--change {
  background: var(--el-color-warning);
}
.tl-dot--log {
  background: var(--el-color-primary);
}
.tl-dot--identity {
  background: var(--el-color-success);
}
.tl-dot--behavior {
  background: var(--el-color-info);
}

.tl-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tl-item__source {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tl-item__sev {
  font-size: 12px;
  color: var(--el-color-danger);
}

.tl-item__summary {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
}

.tl-item__payload {
  margin: 6px 0 0;
  padding: 8px;
  max-height: 180px;
  overflow: auto;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

.tl-item__ref {
  display: inline-block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.timeline-tab__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.timeline-tab__empty .empty-icon {
  font-size: 40px;
  margin-bottom: 8px;
}

.timeline-tab__more {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}
</style>
