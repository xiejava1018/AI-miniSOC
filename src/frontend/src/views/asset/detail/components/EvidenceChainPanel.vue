<!--
  证据链面板（OH-UI.5 §3.3）
  消费 OH-2.4 build_evidence_chain.summary + summary.timeline（去重后展示）
  展示：顶部 summary bar（来源/维度/置信/时间跨）+ 按 source 分组的时间线
-->
<template>
  <div class="evidence-panel" v-loading="loading">
    <!-- 空态 -->
    <div v-if="!hasSummary" class="evidence-panel__empty">
      <ElIcon class="empty-icon"><DocumentRemove /></ElIcon>
      <p>{{ emptyText }}</p>
    </div>

    <template v-else>
      <!-- 摘要条 -->
      <div class="evidence-panel__summary">
        <div class="summary-item">
          <div class="summary-item__num">{{ summary?.total_evidence ?? 0 }}</div>
          <div class="summary-item__label">总证据</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__num">{{ summary?.sources?.length ?? 0 }}</div>
          <div class="summary-item__label">数据来源</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__num">{{ summary?.dimensions?.length ?? 0 }}/8</div>
          <div class="summary-item__label">覆盖维度</div>
        </div>
        <div class="summary-item">
          <div class="summary-item__num">{{ confidencePct }}%</div>
          <div class="summary-item__label">平均置信</div>
        </div>
        <div class="summary-item summary-item--wide">
          <div class="summary-item__num summary-item__num--sm">
            {{ formatTimeRange(summary?.earliest_observed_at, summary?.latest_observed_at) }}
          </div>
          <div class="summary-item__label">
            观测时间跨
            <span v-if="summary?.timespan_hours != null">
              ({{ formatTimespan(summary?.timespan_hours!) }})
            </span>
          </div>
        </div>
      </div>

      <!-- 来源/维度徽章墙 -->
      <div class="evidence-panel__tags">
        <div class="tag-row">
          <span class="tag-row__title">来源：</span>
          <ElTag
            v-for="s in (summary?.sources || [])"
            :key="s"
            size="small"
            type="info"
            effect="plain"
          >
            {{ sourceLabel(s) }}
          </ElTag>
        </div>
        <div class="tag-row">
          <span class="tag-row__title">维度：</span>
          <ElTag
            v-for="d in (summary?.dimensions || [])"
            :key="d"
            size="small"
            :type="dimTagType(d)"
            effect="plain"
          >
            {{ dimensionLabel(d) }}
          </ElTag>
        </div>
      </div>

      <!-- 时间线 -->
      <div class="evidence-panel__timeline" v-if="groupedBySource.length">
        <ElCollapse v-model="openSources">
          <ElCollapseItem
            v-for="g in groupedBySource"
            :key="g.source"
            :name="g.source"
            :title="`${sourceLabel(g.source)} · ${g.entries.length} 条`"
          >
            <div
              v-for="entry in g.entries"
              :key="entry.evidence_id"
              class="evidence-row"
            >
              <div class="evidence-row__head">
                <ElTag size="small" :type="dimTagType(entry.dimension)" effect="dark">
                  {{ dimensionLabel(entry.dimension) }}
                </ElTag>
                <span class="evidence-row__time">
                  {{ formatTime(entry.observed_at) }}
                </span>
                <ElTag
                  size="small"
                  :type="confidenceTagType(entry.confidence)"
                  effect="plain"
                  class="evidence-row__conf"
                >
                  置信 {{ Math.round((entry.confidence ?? 0) * 100) }}%
                </ElTag>
              </div>
              <div class="evidence-row__ref" v-if="entry.reference">
                <span class="evidence-row__ref-label">引用：</span>
                <code>{{ entry.reference }}</code>
              </div>
              <div class="evidence-row__note" v-if="entry.note">
                {{ entry.note }}
              </div>
            </div>
          </ElCollapseItem>
        </ElCollapse>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export interface EvidenceEntryView {
  evidence_id: string
  dimension: string
  source: string
  observed_at: string
  confidence: number
  reference?: string | null
  note?: string | null
}

export interface EvidenceSummaryView {
  total_evidence: number
  sources: string[]
  dimensions: string[]
  avg_confidence: number
  earliest_observed_at: string | null
  latest_observed_at: string | null
  timespan_hours: number | null
}

interface EvidenceChainPanelProps {
  loading?: boolean
  /** 时间线（来自 OH-UI.4 completeness.evidence_summary；为简化本组件展示 timeline 字段；
   *  此处实际接收 summary.timeline — 由父组件决定是否展开） */
  timeline?: EvidenceEntryView[]
  /** 摘要（来自 OH-UI.4 completeness.evidence_summary） */
  summary?: EvidenceSummaryView | null
}

const props = withDefaults(defineProps<EvidenceChainPanelProps>(), {
  loading: false,
  timeline: () => [],
  summary: null
})

const openSources = ref<string[]>([])

const hasSummary = computed(() => {
  return (props.summary?.total_evidence ?? 0) > 0 || props.timeline.length > 0
})

const emptyText = computed(() => {
  if (props.loading) return '加载中…'
  if (!hasSummary.value) return '尚无证据，请检查数据采集与画像计算任务'
  return ''
})

const confidencePct = computed(() => Math.round((props.summary?.avg_confidence ?? 0) * 100))

const groupedBySource = computed(() => {
  const map = new Map<string, EvidenceEntryView[]>()
  for (const e of props.timeline) {
    const list = map.get(e.source) ?? []
    list.push(e)
    map.set(e.source, list)
  }
  return Array.from(map.entries())
    .map(([source, entries]) => ({
      source,
      entries: [...entries].sort((a, b) => {
        const ta = Date.parse(a.observed_at || '') || 0
        const tb = Date.parse(b.observed_at || '') || 0
        return tb - ta
      })
    }))
    .sort((a, b) => b.entries.length - a.entries.length)
})

// --------- 标签转换 ----------
const DIMENSION_LABELS: Record<string, string> = {
  identity: '身份',
  ownership: '归属',
  technology: '技术',
  exposure: '暴露',
  vulnerability: '脆弱',
  threat: '威胁',
  compliance: '合规',
  behavior: '行为',
  ahs: 'AHS'
}
function dimensionLabel(k: string): string {
  return DIMENSION_LABELS[k] ?? k
}

const DIMENSION_TAG_TYPE: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
  identity: 'info',
  ownership: 'info',
  technology: 'info',
  exposure: 'warning',
  vulnerability: 'danger',
  threat: 'danger',
  compliance: 'success',
  behavior: 'primary',
  ahs: 'primary'
}
function dimTagType(k: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  return DIMENSION_TAG_TYPE[k] ?? 'info'
}

function confidenceTagType(c: number): 'success' | 'warning' | 'danger' {
  if (c >= 0.8) return 'success'
  if (c >= 0.5) return 'warning'
  return 'danger'
}

// ORM 表名 → 中文（业务侧常见别名）
const SOURCE_LABELS: Record<string, string> = {
  soc_assets: '资产主表',
  soc_asset_vulnerabilities: '漏洞',
  soc_asset_ports: '端口',
  soc_asset_tags: '资产标签',
  soc_applications: '应用',
  soc_alerts: '告警',
  soc_incidents: '事件',
  soc_baseline_results: '基线',
  soc_owners: '责任人',
  soc_ahs_results: 'AHS',
  soc_business_systems: '业务系统',
  soc_evidence_links: '外部审计',
  soc_asset_tags_x: '资产标签关联'
}
function sourceLabel(s: string): string {
  return SOURCE_LABELS[s] ?? s
}

// --------- 时间格式 ----------
function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

function formatTimeRange(from?: string | null, to?: string | null): string {
  if (!from && !to) return '—'
  const fmt = (s?: string | null) => (s ? formatTime(s).slice(0, 10) : '—')
  return `${fmt(from)} → ${fmt(to)}`
}

function formatTimespan(h: number): string {
  if (h < 24) return `${h.toFixed(1)} 小时`
  if (h < 24 * 30) return `${(h / 24).toFixed(1)} 天`
  if (h < 24 * 365) return `${(h / 24 / 30).toFixed(1)} 月`
  return `${(h / 24 / 365).toFixed(1)} 年`
}
</script>

<style scoped lang="scss">
.evidence-panel {
  &__empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    color: var(--el-text-color-secondary, #606266);

    .empty-icon {
      font-size: 36px;
      margin-bottom: 8px;
      color: var(--el-text-color-placeholder, #909399);
    }
  }

  &__summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr)) 2fr;
    gap: 12px;
    padding: 16px;
    background: var(--el-fill-color-light, #f5f7fa);
    border-radius: 4px;
    margin-bottom: 12px;
  }

  &__tags {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 16px;
    border: 1px dashed var(--el-border-color-lighter, #ebeef5);
    border-radius: 4px;
    margin-bottom: 16px;
  }

  &__timeline {
    border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
    padding-top: 12px;
  }
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;

  &__num {
    font-size: 22px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--el-text-color-primary, #303133);
    line-height: 1.2;

    &--sm {
      font-size: 14px;
    }
  }

  &__label {
    font-size: 12px;
    color: var(--el-text-color-secondary, #606266);
    margin-top: 4px;
  }

  &--wide {
    grid-column: span 1;
  }
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  font-size: 12px;

  &__title {
    font-weight: 500;
    color: var(--el-text-color-secondary, #606266);
    flex-shrink: 0;
  }
}

.evidence-row {
  padding: 10px 12px;
  border-bottom: 1px dashed var(--el-border-color-lighter, #ebeef5);

  &:last-child {
    border-bottom: none;
  }

  &__head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  &__time {
    font-size: 12px;
    color: var(--el-text-color-secondary, #606266);
  }

  &__conf {
    margin-left: auto;
  }

  &__ref {
    margin-top: 4px;
    font-size: 12px;
    color: var(--el-text-color-secondary, #606266);

    code {
      background: var(--el-fill-color-light, #f5f7fa);
      padding: 1px 4px;
      border-radius: 2px;
      font-size: 11px;
    }
  }

  &__ref-label {
    font-weight: 500;
  }

  &__note {
    margin-top: 4px;
    font-size: 13px;
    color: var(--el-text-color-regular, #303133);
    line-height: 1.5;
  }
}

@media (max-width: 1100px) {
  .evidence-panel__summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>