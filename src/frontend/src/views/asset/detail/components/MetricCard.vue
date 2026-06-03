<template>
  <div
    class="metric-card"
    :class="[
      `metric-card--${type}`,
      { 'metric-card--clickable': clickable }
    ]"
    @click="handleClick"
  >
    <div class="metric-card__label">{{ label }}</div>
    <div class="metric-card__value">
      <span class="metric-card__number">{{ displayValue }}</span>
      <span v-if="suffix" class="metric-card__suffix">{{ suffix }}</span>
    </div>
    <div v-if="subLabel" class="metric-card__sub">
      {{ subLabel }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type MetricCardType = 'danger' | 'warning' | 'success' | 'info' | 'neutral'

interface MetricCardProps {
  /** 卡片标签,例如 "24h 告警" */
  label: string
  /** 卡片主数值 */
  value: number | string | null | undefined
  /** 视觉类型,默认 info */
  type?: MetricCardType
  /** 后缀,例如 "%" / "个" */
  suffix?: string
  /** 副标签(显示在数值下方) */
  subLabel?: string
  /** 是否可点击(影响 hover 效果) */
  clickable?: boolean
  /** 数值为 0 或 null 时是否灰显(用于"暂无风险"场景) */
  mutedWhenZero?: boolean
}

const props = withDefaults(defineProps<MetricCardProps>(), {
  type: 'info',
  clickable: false,
  mutedWhenZero: false
})

const emit = defineEmits<{
  (e: 'click'): void
}>()

const displayValue = computed(() => {
  if (props.value === null || props.value === undefined || props.value === '') {
    return '-'
  }
  return String(props.value)
})

const handleClick = () => {
  if (props.clickable) {
    emit('click')
  }
}
</script>

<style scoped lang="scss">
.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  background: var(--el-fill-color-blank, #fff);
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-left-width: 3px;
  border-radius: 4px;
  transition: all 0.2s ease;
  min-height: 92px;
  cursor: default;

  &--clickable {
    cursor: pointer;
    user-select: none;

    &:hover {
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
      transform: translateY(-1px);
    }

    &:active {
      transform: translateY(0);
    }
  }

  &--danger {
    border-left-color: var(--el-color-danger, #f56c6c);

    .metric-card__number {
      color: var(--el-color-danger, #f56c6c);
    }
  }

  &--warning {
    border-left-color: var(--el-color-warning, #e6a23c);

    .metric-card__number {
      color: var(--el-color-warning, #e6a23c);
    }
  }

  &--success {
    border-left-color: var(--el-color-success, #67c23a);

    .metric-card__number {
      color: var(--el-color-success, #67c23a);
    }
  }

  &--info {
    border-left-color: var(--el-color-primary, #409eff);

    .metric-card__number {
      color: var(--el-color-primary, #409eff);
    }
  }

  &--neutral {
    border-left-color: var(--el-color-info, #909399);

    .metric-card__number {
      color: var(--el-text-color-primary, #303133);
    }
  }

  &__label {
    font-size: 13px;
    color: var(--el-text-color-secondary, #606266);
    line-height: 1.4;
  }

  &__value {
    display: flex;
    align-items: baseline;
    gap: 4px;
  }

  &__number {
    font-size: 26px;
    font-weight: 600;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
  }

  &__suffix {
    font-size: 13px;
    color: var(--el-text-color-secondary, #606266);
  }

  &__sub {
    font-size: 12px;
    color: var(--el-text-color-placeholder, #909399);
    line-height: 1.3;
  }
}
</style>
