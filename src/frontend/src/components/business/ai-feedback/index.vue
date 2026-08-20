<template>
  <div class="ai-feedback" v-if="visible">
    <span class="ai-feedback__badge" title="AI 生成内容">AI</span>
    <span v-if="!submitted" class="ai-feedback__actions">
      <ElTooltip content="回答有帮助" placement="top">
        <ElIcon class="ai-feedback__btn" @click="submit('up')"><CaretTop /></ElIcon>
      </ElTooltip>
      <ElTooltip content="回答不准确（可补充说明）" placement="top">
        <ElIcon class="ai-feedback__btn" @click="openDown"><CaretBottom /></ElIcon>
      </ElTooltip>
    </span>
    <span v-else class="ai-feedback__done" :class="{ 'is-up': lastRating === 'up' }">
      {{ lastRating === 'up' ? '已记录 👍' : '已记录 👎' }}
    </span>
  </div>
</template>

<script setup lang="ts">
/**
 * P3/F4.1 通用 AI 反馈组件（PRD §八-C：所有 AI 产物带反馈入口）
 *
 * 用法：
 *   <AiFeedback target-type="risk_summary" :target-id="assetId" />
 */
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretTop, CaretBottom } from '@element-plus/icons-vue'
import { submitAiFeedback, type FeedbackTargetType } from '@/api/ai-feedback'

const props = withDefaults(
  defineProps<{
    targetType: FeedbackTargetType
    targetId: string
    /** 是否显示（例如无 AI 摘要时隐藏） */
    visible?: boolean
  }>(),
  { visible: true }
)

const submitted = ref(false)
const lastRating = ref<'up' | 'down'>('up')

const openDown = () => {
  ElMessageBox.prompt('哪里不准确？（可选，不超过 200 字）', '反馈 · 回答不准确', {
    confirmButtonText: '提交',
    cancelButtonText: '跳过，直接提交',
    inputPlaceholder: '例如：端口数量不对 / 建议不适用',
    inputType: 'textarea',
    inputValidator: (v: string) => !v || v.length <= 200 || '不超过 200 字'
  })
    .then(({ value }) => submit('down', value || undefined))
    .catch(() => submit('down'))
}

const submit = async (rating: 'up' | 'down', comment?: string) => {
  try {
    await submitAiFeedback({
      target_type: props.targetType,
      target_id: props.targetId,
      rating,
      comment: rating === 'down' ? comment : undefined
    })
    submitted.value = true
    lastRating.value = rating
  } catch {
    ElMessage.error('反馈提交失败，请稍后重试')
  }
}
</script>

<style scoped lang="scss">
.ai-feedback {
  display: inline-flex;
  align-items: center;
  gap: 6px;

  &__badge {
    font-size: 10px;
    font-weight: 700;
    color: var(--el-color-primary);
    border: 1px solid var(--el-color-primary-light-5);
    border-radius: 4px;
    padding: 0 4px;
    line-height: 16px;
  }

  &__actions {
    display: inline-flex;
    gap: 4px;
  }

  &__btn {
    cursor: pointer;
    color: var(--el-text-color-secondary);
    font-size: 14px;

    &:hover {
      color: var(--el-color-primary);
    }
  }

  &__done {
    font-size: 12px;
    color: var(--el-text-color-secondary);

    &.is-up {
      color: var(--el-color-success);
    }
  }
}
</style>
