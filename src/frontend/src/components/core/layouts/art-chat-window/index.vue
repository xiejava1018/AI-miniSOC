<!--
  Art Bot 聊天窗口

  来源：art-design-pro 上游 layouts/art-chat-window（MIT）
  本地化：
    1) 去掉 i18n（项目已移除 vue-i18n）+ 中文静态文本
    2) 接入真实后端 SSE 流式 + Markdown 渲染
    3) 接入 chat store 持久化多轮会话
    4) mittBus 事件 'openChat' 触发显示
-->
<template>
  <div>
    <ElDrawer
      v-model="isDrawerVisible"
      :size="isMobile ? '100%' : '480px'"
      :with-header="false"
    >
      <!-- 顶栏 -->
      <div class="mb-5 flex-cb">
        <div>
          <span class="text-base font-medium">Art Bot</span>
          <div class="mt-1.5 flex-c gap-1">
            <div
              class="h-2 w-2 rounded-full"
              :class="isOnline ? 'bg-success/100' : 'bg-danger/100'"
            ></div>
            <span class="text-xs text-g-600">
              {{ isOnline ? '在线' : '离线' }}
              <template v-if="chatStore.currentSession">
                · 会话：{{ chatStore.currentSession.title }}
              </template>
            </span>
          </div>
        </div>
        <div class="flex-c gap-2">
          <ElIcon class="c-p" :size="18" title="新会话" @click="onNewChat">
            <Plus />
          </ElIcon>
          <ElIcon class="c-p" :size="20" @click="closeChat">
            <Close />
          </ElIcon>
        </div>
      </div>

      <div class="flex h-[calc(100%-70px)] flex-col">
        <!-- 消息区域 -->
        <div
          class="flex-1 overflow-y-auto border-t-d px-4 py-7.5 [&::-webkit-scrollbar]:!w-1"
          ref="messageContainer"
        >
          <template v-if="!chatStore.messages.length">
            <div class="flex-c justify-center mt-10 text-g-500 text-sm">
              <ArtSvgIcon icon="ri:robot-2-line" class="text-3xl mr-2" />
              您好，我是 Art Bot，向我提问吧
            </div>
          </template>
          <template v-for="(message, index) in chatStore.messages" :key="index">
            <div
              :class="[
                'mb-7.5 flex w-full items-start gap-2',
                message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
              ]"
            >
              <ElAvatar
                :size="32"
                :src="message.role === 'user' ? userAvatar : botAvatar"
                class="shrink-0"
              />
              <div
                :class="[
                  'flex max-w-[70%] flex-col',
                  message.role === 'user' ? 'items-end' : 'items-start'
                ]"
              >
                <div
                  :class="[
                    'mb-1 flex gap-2 text-xs',
                    message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                  ]"
                >
                  <span class="font-medium">
                    {{ message.role === 'user' ? userNick : 'Art Bot' }}
                  </span>
                  <span v-if="message.is_truncated" class="text-warning">[已截断]</span>
                </div>
                <div
                  :class="[
                    'rounded-md px-3.5 py-2.5 text-sm leading-[1.4] text-g-900 chat-bubble',
                    message.role === 'user' ? 'message-right bg-theme/15' : 'message-left bg-g-300/50'
                  ]"
                  v-html="renderMarkdown(message.content)"
                />
              </div>
            </div>
          </template>

          <!-- 流式中累积的临时内容 -->
          <template v-if="chatStore.isStreaming && chatStore.streamingContent">
            <div class="mb-7.5 flex w-full items-start gap-2 flex-row">
              <ElAvatar :size="32" :src="botAvatar" class="shrink-0" />
              <div class="flex max-w-[70%] flex-col items-start">
                <div class="mb-1 flex gap-2 text-xs flex-row">
                  <span class="font-medium">Art Bot</span>
                  <span class="chat-message__typing">
                    <span /><span /><span />
                  </span>
                </div>
                <div
                  class="rounded-md px-3.5 py-2.5 text-sm leading-[1.4] text-g-900 message-left bg-g-300/50 chat-bubble"
                  v-html="renderMarkdown(chatStore.streamingContent)"
                />
              </div>
            </div>
          </template>

          <!-- 错误提示 -->
          <div v-if="chatStore.streamError" class="px-3.5 py-2 mb-4 rounded text-xs text-danger bg-danger/10">
            {{ chatStore.streamError }}
          </div>
        </div>

        <!-- 输入区 -->
        <div class="px-4 pt-4 border-t">
          <ElInput
            v-model="messageText"
            type="textarea"
            :rows="2"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="向 Art Bot 提问（Enter 发送，Shift+Enter 换行）"
            resize="none"
            :disabled="chatStore.isStreaming"
            @keydown="onKeydown"
          />
          <div class="mt-3 flex-cb">
            <div class="flex-c text-xs text-g-500">
              <ArtSvgIcon icon="ri:information-line" class="mr-1" />
              Art Bot 回答由 GLM-4-Flash 生成，结果仅供参考
            </div>
            <ElButton
              v-if="chatStore.isStreaming"
              type="danger"
              :icon="CircleClose"
              @click="chatStore.stopStream()"
              v-ripple
            >
              停止
            </ElButton>
            <ElButton
              v-else
              type="primary"
              @click="sendMessage"
              :disabled="!messageText.trim()"
              v-ripple
              class="min-w-20"
            >
              发送
            </ElButton>
          </div>
        </div>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
  import { useWindowSize } from '@vueuse/core'
  import { Close, Plus, CircleClose } from '@element-plus/icons-vue'
  import { mittBus } from '@/utils/sys'
  import { useUserStore } from '@/store/modules/user'
  import { useChatStore } from '@/store/modules/chat'
  import { renderMarkdown } from '@/utils/markdown'
  // 沿用上游默认头像
  import meAvatar from '@/assets/images/avatar/avatar5.webp'
  import aiAvatar from '@/assets/images/avatar/avatar10.webp'

  defineOptions({ name: 'ArtChatWindow' })

  const MOBILE_BREAKPOINT = 640
  const SCROLL_DELAY = 80

  const { width } = useWindowSize()
  const isMobile = computed(() => width.value < MOBILE_BREAKPOINT)

  // 用户信息（用于 user 气泡头像 / 名称）
  const userStore = useUserStore()
  const userAvatar = computed(() => (userStore.info as any)?.avatar || meAvatar)
  const userNick = computed(() => (userStore.info as any)?.nickName || '我')
  const botAvatar = aiAvatar

  // 聊天 store
  const chatStore = useChatStore()
  const isOnline = ref(true)

  const isDrawerVisible = ref(false)
  const messageText = ref('')
  const messageContainer = ref<HTMLElement | null>(null)

  const scrollToBottom = (): void => {
    nextTick(() => {
      setTimeout(() => {
        if (messageContainer.value) {
          messageContainer.value.scrollTop = messageContainer.value.scrollHeight
        }
      }, SCROLL_DELAY)
    })
  }

  // 监听流式内容变化自动滚到底
  watch(
    () => [chatStore.streamingContent, chatStore.messages.length],
    () => scrollToBottom()
  )

  async function sendMessage(): Promise<void> {
    const text = messageText.value.trim()
    if (!text) return
    messageText.value = ''
    await chatStore.sendMessage(text)
  }

  function onKeydown(e: Event): void {
    const ke = e as KeyboardEvent
    if (ke.key === 'Enter' && !ke.shiftKey && !ke.isComposing) {
      e.preventDefault()
      void sendMessage()
    }
  }

  function onNewChat(): void {
    chatStore.newSession()
    scrollToBottom()
  }

  function openChat(): void {
    isDrawerVisible.value = true
    if (!chatStore.sessions.length) {
      void chatStore.loadSessions()
    }
    scrollToBottom()
  }

  function closeChat(): void {
    isDrawerVisible.value = false
  }

  onMounted(() => {
    scrollToBottom()
    mittBus.on('openChat', openChat)
  })

  onUnmounted(() => {
    mittBus.off('openChat', openChat)
  })
</script>

<style scoped>
  /* 消息气泡中的 Markdown 内容样式 */
  .chat-bubble :deep(p) {
    margin: 0 0 4px;
  }
  .chat-bubble :deep(p:last-child) {
    margin-bottom: 0;
  }
  .chat-bubble :deep(pre) {
    margin: 4px 0;
    padding: 6px 8px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.6);
    color: #d4d4d4;
    overflow-x: auto;
    font-size: 12px;
  }
  .chat-bubble :deep(code) {
    padding: 1px 4px;
    border-radius: 3px;
    background: rgba(0, 0, 0, 0.1);
    font-size: 12px;
  }
  .chat-bubble :deep(pre code) {
    padding: 0;
    background: transparent;
    color: inherit;
  }
  .chat-bubble :deep(ul),
  .chat-bubble :deep(ol) {
    margin: 4px 0;
    padding-left: 18px;
  }
  .chat-bubble :deep(strong) {
    font-weight: 600;
  }
  .chat-bubble :deep(a) {
    color: var(--el-color-primary);
    text-decoration: underline;
  }

  /* 流式打字光标 */
  .chat-message__typing {
    display: inline-flex;
    gap: 2px;
    margin-left: 4px;
  }
  .chat-message__typing span {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--el-color-primary);
    animation: typing 1.2s infinite;
  }
  .chat-message__typing span:nth-child(2) {
    animation-delay: 0.2s;
  }
  .chat-message__typing span:nth-child(3) {
    animation-delay: 0.4s;
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
