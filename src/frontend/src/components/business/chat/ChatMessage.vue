<template>
  <div class="chat-message" :class="`chat-message--${message.role}`">
    <div class="chat-message__avatar">
      <ElAvatar
        v-if="message.role === 'user'"
        :size="32"
        :src="userAvatar"
      >
        {{ userNick.charAt(0) }}
      </ElAvatar>
      <div v-else class="chat-message__bot-avatar">
        <ArtSvgIcon icon="ri:robot-2-fill" class="text-base" />
      </div>
    </div>
    <div class="chat-message__body">
      <div class="chat-message__name">
        {{ message.role === 'user' ? userNick : 'Art Bot' }}
        <span v-if="streaming" class="chat-message__typing">
          <span /><span /><span />
        </span>
      </div>
      <div class="chat-message__content" v-html="rendered" />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useUserStore } from '@/store/modules/user'
  import { renderMarkdown } from '@/utils/markdown'
  import type { ChatMessageItem } from '@/api/chat'

  const props = defineProps<{ message: ChatMessageItem; streaming?: boolean }>()

  const userStore = useUserStore()
  const userAvatar = computed(() => (userStore.info as any)?.avatar)
  const userNick = computed(() => (userStore.info as any)?.nickName || '我')
  const rendered = computed(() => renderMarkdown(props.message.content))
</script>

<style scoped lang="scss">
  .chat-message {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;

    &__avatar {
      flex-shrink: 0;
    }

    &__bot-avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #409eff 0%, #67c23a 100%);
      color: #fff;
    }

    &__body {
      flex: 1;
      min-width: 0;
    }

    &__name {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
      margin-bottom: 4px;
    }

    &__content {
      padding: 8px 12px;
      border-radius: 8px;
      background: var(--el-fill-color-blank);
      border: 1px solid var(--el-border-color-lighter);
      font-size: 14px;
      line-height: 1.6;
      word-break: break-word;

      :deep(p) {
        margin: 0 0 6px;

        &:last-child {
          margin-bottom: 0;
        }
      }

      :deep(pre) {
        margin: 6px 0;
        padding: 8px 12px;
        border-radius: 6px;
        background: #1e1e1e;
        color: #d4d4d4;
        overflow-x: auto;
        font-size: 12px;
        font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
      }

      :deep(code) {
        padding: 1px 4px;
        border-radius: 3px;
        background: var(--el-fill-color-light);
        font-size: 12px;
        font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
      }

      :deep(pre code) {
        padding: 0;
        background: transparent;
        color: inherit;
      }

      :deep(ul),
      :deep(ol) {
        margin: 4px 0;
        padding-left: 20px;
      }
    }

    &--user {
      flex-direction: row-reverse;

      .chat-message__content {
        background: var(--el-color-primary-light-9);
        border-color: var(--el-color-primary-light-7);
      }
    }

    &__typing {
      display: inline-flex;
      gap: 2px;
      margin-left: 4px;

      span {
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background: var(--el-color-primary);
        animation: typing 1.2s infinite;
      }

      span:nth-child(2) {
        animation-delay: 0.2s;
      }
      span:nth-child(3) {
        animation-delay: 0.4s;
      }
    }
  }

  @keyframes typing {
    0%,
    60%,
    100% {
      transform: translateY(0);
      opacity: 0.4;
    }
    30% {
      transform: translateY(-3px);
      opacity: 1;
    }
  }
</style>
