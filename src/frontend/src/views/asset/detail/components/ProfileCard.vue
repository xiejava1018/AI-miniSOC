<!--
  八维画像环形网格卡（OH-UI.5 §3.1）
  消费 OH-2.1 八维 coverage + OH-UI.4 completeness.dimensions
  显示 8 个维度：每个小环 + 标签 + 证据数
-->
<template>
  <div class="profile-card" :class="{ 'is-all-covered': coverageRatio === 1 }">
    <div class="profile-card__grid">
      <div
        v-for="dim in dimensions"
        :key="dim.key"
        class="profile-dim"
        :class="['is-' + dim.status, { 'is-clickable': clickable && dim.status === 'covered' }]"
        @click="handleClick(dim)"
      >
        <svg :width="dimSize" :height="dimSize" :viewBox="`0 0 ${dimSize} ${dimSize}`" class="profile-dim__ring">
          <circle
            :cx="dimSize / 2"
            :cy="dimSize / 2"
            :r="dimRadius"
            fill="none"
            :stroke="dimBgStroke"
            :stroke-width="dimStroke"
          />
          <circle
            v-if="dim.status !== 'missing'"
            :cx="dimSize / 2"
            :cy="dimSize / 2"
            :r="dimRadius"
            fill="none"
            :stroke="dimStrokeColor(dim)"
            :stroke-width="dimStroke"
            stroke-linecap="round"
            :stroke-dasharray="dimCircumference"
            :stroke-dashoffset="dimDashOffset(dim)"
            :transform="`rotate(-90 ${dimSize / 2} ${dimSize / 2})`"
          />
          <text
            :x="dimSize / 2"
            :y="dimSize / 2"
            text-anchor="middle"
            dominant-baseline="middle"
            class="profile-dim__icon"
            :fill="dimStrokeColor(dim)"
          >
            {{ dimIcon(dim.key) }}
          </text>
        </svg>
        <div class="profile-dim__name">{{ dim.label }}</div>
        <div class="profile-dim__meta">
          <ElTag v-if="dim.status === 'covered'" size="small" type="success" effect="plain">
            {{ dim.evidence_count }} 条
          </ElTag>
          <ElTag v-else-if="dim.status === 'partial'" size="small" type="warning" effect="plain">
            {{ dim.evidence_count }} 条
          </ElTag>
          <ElTag v-else size="small" type="info" effect="plain">缺</ElTag>
        </div>
        <div v-if="dim.confidence > 0" class="profile-dim__conf">
          置信 {{ Math.round(dim.confidence * 100) }}%
        </div>
      </div>
    </div>

    <div class="profile-card__footer">
      <ElProgress
        :percentage="coverageRatio * 100"
        :stroke-width="10"
        :color="coverageRatio === 1 ? 'var(--el-color-success, #67c23a)' : coverageRatio >= 0.5 ? 'var(--el-color-warning, #e6a23c)' : 'var(--el-color-danger, #f56c6c)'"
        :format="(v: number) => `${coveredCount}/${totalCount} (${v.toFixed(0)}%)`"
      />
      <span class="profile-card__confidence">
        画像置信度 {{ profileConfidencePct }}%
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type DimensionKey =
  | 'identity'
  | 'ownership'
  | 'technology'
  | 'exposure'
  | 'vulnerability'
  | 'threat'
  | 'compliance'
  | 'behavior'

export interface DimensionInfo {
  key: DimensionKey
  label: string
  status: 'covered' | 'partial' | 'missing'
  evidence_count: number
  confidence: number
}

interface ProfileCardProps {
  /** 8 个维度明细（来自 OH-UI.4 completeness.dimensions） */
  dimensions: DimensionInfo[]
  /** 覆盖 0-1（来自 coverage.ratio） */
  coverageRatio: number
  /** 画像置信度 0-1（来自 profile_confidence） */
  profileConfidence: number
  /** 单个小环直径 */
  dimSize?: number
  /** 点击 covered 维度时回调（可跳转 Tab） */
  clickable?: boolean
}

const props = withDefaults(defineProps<ProfileCardProps>(), {
  dimSize: 72,
  clickable: false
})

const emit = defineEmits<{
  (e: 'dim-click', key: DimensionKey): void
}>()

const dimStroke = computed(() => Math.max(6, Math.round(props.dimSize * 0.08)))
const dimRadius = computed(() => (props.dimSize - dimStroke.value) / 2)
const dimCircumference = computed(() => 2 * Math.PI * dimRadius.value)
const dimBgStroke = computed(() => 'var(--el-fill-color-light, #f5f7fa)')

const totalCount = computed(() => 8)
const coveredCount = computed(() => props.dimensions.filter(d => d.status !== 'missing').length)

const profileConfidencePct = computed(() => Math.round((props.profileConfidence || 0) * 100))

function dimDashOffset(d: DimensionInfo): number {
  const ratio = d.status === 'covered' ? 1 : d.status === 'partial' ? Math.min(1, d.confidence || 0.5) : 0
  return dimCircumference.value * (1 - ratio)
}

function dimStrokeColor(d: DimensionInfo): string {
  if (d.status === 'covered') return 'var(--el-color-success, #67c23a)'
  if (d.status === 'partial') return 'var(--el-color-warning, #e6a23c)'
  return 'var(--el-color-info, #c0c4cc)'
}

const DIMENSION_ICONS: Record<DimensionKey, string> = {
  identity: '👤',
  ownership: '🏷',
  technology: '⚙',
  exposure: '🌐',
  vulnerability: '🛡',
  threat: '⚠',
  compliance: '✓',
  behavior: '📊'
}
function dimIcon(k: DimensionKey): string {
  return DIMENSION_ICONS[k] ?? '?'
}

function handleClick(d: DimensionInfo) {
  if (props.clickable && d.status === 'covered') {
    emit('dim-click', d.key)
  }
}
</script>

<style scoped lang="scss">
.profile-card {
  &__grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  &__footer {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding-top: 8px;
    border-top: 1px dashed var(--el-border-color-lighter, #ebeef5);
  }

  &__confidence {
    font-size: 12px;
    color: var(--el-text-color-secondary, #606266);
  }

  @media (max-width: 1100px) {
    &__grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  @media (max-width: 768px) {
    &__grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
}

.profile-dim {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.2s ease;

  &.is-clickable {
    cursor: pointer;
    &:hover {
      background: var(--el-fill-color-light, #f5f7fa);
    }
  }

  &.is-missing {
    opacity: 0.5;
  }

  &__ring {
    flex-shrink: 0;
  }

  &__icon {
    font-size: 22px;
    line-height: 1;
  }

  &__name {
    font-size: 12px;
    color: var(--el-text-color-regular, #303133);
    font-weight: 500;
  }

  &__meta {
    display: flex;
  }

  &__conf {
    font-size: 10px;
    color: var(--el-text-color-placeholder, #909399);
  }
}
</style>
