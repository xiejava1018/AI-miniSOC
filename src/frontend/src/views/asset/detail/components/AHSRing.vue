<!--
  AHS 健康分环形 + 5 维构成条（OH-UI.5 §3.1）
  消费 OH-2.2 compute_ahs / OH-UI.4 completeness.ahs_score
  显示 0-100 健康分 + 5 个扣分维的占比（条形）
-->
<template>
  <div class="ahs-ring" :class="stateClass">
    <!-- 左侧大环 -->
    <div class="ahs-ring__main">
      <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`">
        <!-- 背景环 -->
        <circle
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          fill="none"
          stroke="var(--el-fill-color-light, #f5f7fa)"
          :stroke-width="strokeWidth"
        />
        <!-- 进度弧 -->
        <circle
          :cx="size / 2"
          :cy="size / 2"
          :r="radius"
          fill="none"
          :stroke="color"
          :stroke-width="strokeWidth"
          stroke-linecap="round"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="dashOffset"
          :transform="`rotate(-90 ${size / 2} ${size / 2})`"
        />
        <!-- 中心数字 -->
        <text
          :x="size / 2"
          :y="size / 2 - 4"
          text-anchor="middle"
          dominant-baseline="middle"
          class="ahs-ring__number"
          :fill="color"
        >
          {{ displayScore }}
        </text>
        <text
          :x="size / 2"
          :y="size / 2 + 18"
          text-anchor="middle"
          dominant-baseline="middle"
          class="ahs-ring__suffix"
          fill="var(--el-text-color-secondary, #606266)"
        >
          / 100
        </text>
      </svg>
      <div class="ahs-ring__label">{{ stateLabel }}</div>
    </div>

    <!-- 右侧 5 维构成条 -->
    <div class="ahs-ring__breakdown" v-if="breakdown.length">
      <div
        v-for="d in breakdown"
        :key="d.key"
        class="ahs-dim-row"
        :title="`${d.label}：${d.rawScore}/100 · 权重 ${(d.weight * 100).toFixed(0)}%${d.dataGap ? '（数据缺失·半权）' : ''}`"
      >
        <span class="ahs-dim-row__label">
          {{ d.label }}
          <ElTag v-if="d.dataGap" size="small" type="warning" effect="plain" class="ahs-dim-row__gap">数据缺失</ElTag>
        </span>
        <span class="ahs-dim-row__score" :style="{ color: dimColor(d.rawScore) }">
          {{ d.dataGap ? '—' : d.rawScore }}
        </span>
        <ElProgress
          :percentage="d.weight * 100"
          :show-text="false"
          :stroke-width="6"
          :color="dimColor(d.rawScore)"
        />
      </div>
      <div class="ahs-dim-formula">
        AHS = 100 − Σ(扣分 × 权重) × 关键性系数 ∈ [0,100]
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface AHSBreakdownItem {
  /** 维度键：exposure / vulnerability / threat / compliance / behavior */
  key: string
  /** 显示名 */
  label: string
  /** 0-100 扣分（越高越糟） */
  rawScore: number
  /** 权重 0-1 */
  weight: number
  /** 数据缺失（半权 / 兜底） */
  dataGap?: boolean
}

interface AHSRingProps {
  /** 0-100 健康分（来自 OH-2.2 compute_ahs） */
  score: number | null | undefined
  /** 状态：valid / insufficient_data / ahs_not_computed */
  state: string | null | undefined
  /** 5 维扣分明细 */
  breakdown?: AHSBreakdownItem[]
  /** 圆环直径（px） */
  size?: number
  /** 关键性系数（用于 hover 提示，可选） */
  criticalityFactor?: number
}

const props = withDefaults(defineProps<AHSRingProps>(), {
  breakdown: () => [],
  size: 160,
  criticalityFactor: 1.0
})

const strokeWidth = computed(() => Math.max(10, Math.round(props.size * 0.08)))
const radius = computed(() => (props.size - strokeWidth.value) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)

const dashOffset = computed(() => {
  const ratio = props.score == null ? 0 : Math.max(0, Math.min(100, props.score)) / 100
  return circumference.value * (1 - ratio)
})

const displayScore = computed(() => {
  if (props.score == null) return '—'
  return Math.round(props.score)
})

const color = computed(() => {
  if (props.state === 'insufficient_data' || props.state === 'ahs_not_computed' || props.score == null) {
    return 'var(--el-color-info, #909399)'
  }
  return dimColor(props.score)
})

const stateClass = computed(() => {
  if (props.state === 'insufficient_data') return 'is-insufficient'
  if (props.state === 'ahs_not_computed' || props.score == null) return 'is-na'
  if (props.score >= 70) return 'is-good'
  if (props.score >= 40) return 'is-warn'
  return 'is-bad'
})

const stateLabel = computed(() => {
  if (props.state === 'insufficient_data') return '数据不足'
  if (props.state === 'ahs_not_computed' || props.score == null) return '尚未计算'
  if (props.score >= 70) return '健康'
  if (props.score >= 40) return '需关注'
  return '高风险'
})

function dimColor(score: number): string {
  if (score >= 70) return 'var(--el-color-danger, #f56c6c)'
  if (score >= 40) return 'var(--el-color-warning, #e6a23c)'
  return 'var(--el-color-success, #67c23a)'
}
</script>

<style scoped lang="scss">
.ahs-ring {
  display: flex;
  gap: 24px;
  align-items: center;

  &__main {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
  }

  &__number {
    font-size: 36px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  &__suffix {
    font-size: 13px;
  }

  &__label {
    font-size: 13px;
    color: var(--el-text-color-regular, #303133);
    font-weight: 500;
  }

  &__breakdown {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  &.is-na &__main,
  &.is-insufficient &__main {
    opacity: 0.6;
  }
}

.ahs-dim-row {
  display: grid;
  grid-template-columns: 100px 36px 1fr;
  gap: 12px;
  align-items: center;
  font-size: 13px;

  &__label {
    color: var(--el-text-color-regular, #303133);
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  &__score {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }

  &__gap {
    font-size: 10px;
    padding: 0 4px;
  }
}

.ahs-dim-formula {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder, #909399);
  font-family: var(--el-font-family-monospace, monospace);
  text-align: center;
  letter-spacing: 0.3px;
}

@media (max-width: 768px) {
  .ahs-ring {
    flex-direction: column;
  }
}
</style>
