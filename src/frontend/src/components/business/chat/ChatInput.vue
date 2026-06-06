<template>
  <div class="chat-input">
    <ElInput
      v-model="text"
      type="textarea"
      :rows="2"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="disabled"
      :placeholder="placeholder"
      resize="none"
      @keydown="onKeydown"
    />
    <div class="chat-input__actions">
      <span class="chat-input__hint">Enter 发送 · Shift+Enter 换行</span>
      <ElButton v-if="loading" type="danger" plain :icon="CircleClose" @click="emit('stop')">
        停止
      </ElButton>
      <ElButton
        v-else
        type="primary"
        :icon="Promotion"
        :disabled="disabled || !text.trim()"
        @click="onSend"
      >
        发送
      </ElButton>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, watch } from 'vue'
  import { Promotion, CircleClose } from '@element-plus/icons-vue'

  const props = defineProps<{
    disabled?: boolean
    loading?: boolean
    placeholder?: string
  }>()

  const emit = defineEmits<{
    (e: 'send', text: string): void
    (e: 'stop'): void
  }>()

  const text = ref('')
  const placeholder = props.placeholder || '向 Art Bot 提问...'

  // 父组件 loading 结束后清空输入
  watch(
    () => props.loading,
    (v, old) => {
      if (old && !v) text.value = ''
    }
  )

  function onSend(): void {
    const value = text.value.trim()
    if (!value) return
    emit('send', value)
  }

  function onKeydown(e: Event): void {
    const ke = e as KeyboardEvent
    if (ke.key === 'Enter' && !ke.shiftKey && !ke.isComposing) {
      e.preventDefault()
      onSend()
    }
  }
</script>

<style scoped lang="scss">
  .chat-input {
    display: flex;
    flex-direction: column;
    gap: 6px;

    &__actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    &__hint {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }
  }
</style>
