/**
 * Art Bot 聊天状态
 *
 * - 多会话切换
 * - 流式增量累积（streamingContent 在 onDelta 中拼接）
 * - 流式状态：idle | streaming | done | error
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { postStream } from '@/utils/http/stream'
import {
  fetchChatSessions,
  fetchChatSessionDetail,
  deleteChatSession,
  type ChatSessionItem,
  type ChatMessageItem
} from '@/api/chat'

export type StreamStatus = 'idle' | 'streaming' | 'error'

export const useChatStore = defineStore('chatStore', () => {
  // ============== state ==============
  const sessions = ref<ChatSessionItem[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<ChatMessageItem[]>([])
  const streamingContent = ref('')
  const streamStatus = ref<StreamStatus>('idle')
  const streamError = ref<string | null>(null)
  let abortFn: (() => void) | null = null

  // ============== getter ==============
  const currentSession = computed<ChatSessionItem | null>(() => {
    if (!currentSessionId.value) return null
    return sessions.value.find((s) => s.id === currentSessionId.value) ?? null
  })

  const isStreaming = computed(() => streamStatus.value === 'streaming')

  // ============== action ==============

  /** 加载会话列表 */
  async function loadSessions(): Promise<void> {
    try {
      const res = await fetchChatSessions({ page: 1, page_size: 50 })
      sessions.value = res.data.items
    } catch (e) {
      console.error('[chat] load sessions failed:', e)
    }
  }

  /** 选中会话并加载消息 */
  async function selectSession(sessionId: string | null): Promise<void> {
    currentSessionId.value = sessionId
    if (!sessionId) {
      messages.value = []
      return
    }
    try {
      const res = await fetchChatSessionDetail(sessionId)
      messages.value = res.data.messages
    } catch (e) {
      console.error('[chat] load session detail failed:', e)
      messages.value = []
    }
  }

  /** 发送一条消息：自动新建或继续会话 */
  async function sendMessage(text: string): Promise<void> {
    if (isStreaming.value) return
    if (!text.trim()) return

    streamError.value = null
    streamingContent.value = ''
    streamStatus.value = 'streaming'

    // 立即在 UI 上显示 user 消息（乐观更新）
    const userMsg: ChatMessageItem = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: text,
      tokens_used: 0,
      is_truncated: false,
      created_at: new Date().toISOString()
    }
    messages.value.push(userMsg)

    const isNew = !currentSessionId.value
    const path = isNew ? '/ai/chat' : `/ai/chat/${currentSessionId.value}`

    abortFn = postStream(
      path,
      { message: { role: 'user', content: text } },
      {
        onHeaders: (headers) => {
          // 首条消息后端会在 X-Session-Id 返回 sessionId
          if (isNew) {
            const sid = headers.get('X-Session-Id')
            if (sid) {
              currentSessionId.value = sid
              // 异步刷新会话列表
              void loadSessions()
            }
          }
        },
        onDelta: (piece) => {
          streamingContent.value += piece
        },
        onDone: () => {
          // 把累积的 streamingContent 落成一条 assistant 消息
          if (streamingContent.value) {
            const asst: ChatMessageItem = {
              id: `tmp-asst-${Date.now()}`,
              role: 'assistant',
              content: streamingContent.value,
              tokens_used: 0,
              is_truncated: false,
              created_at: new Date().toISOString()
            }
            messages.value.push(asst)
          }
          streamingContent.value = ''
          streamStatus.value = 'idle'
          abortFn = null
        },
        onError: (err) => {
          streamError.value = err.message
          streamStatus.value = 'error'
          abortFn = null
        }
      }
    )
  }

  /** 中断当前流 */
  function stopStream(): void {
    abortFn?.()
    abortFn = null
    if (streamingContent.value) {
      messages.value.push({
        id: `tmp-trunc-${Date.now()}`,
        role: 'assistant',
        content: streamingContent.value,
        tokens_used: 0,
        is_truncated: true,
        created_at: new Date().toISOString()
      })
      streamingContent.value = ''
    }
    streamStatus.value = 'idle'
  }

  /** 删除会话 */
  async function removeSession(sessionId: string): Promise<void> {
    try {
      await deleteChatSession(sessionId)
      sessions.value = sessions.value.filter((s) => s.id !== sessionId)
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
        messages.value = []
      }
    } catch (e) {
      console.error('[chat] delete session failed:', e)
    }
  }

  /** 清空当前（开始新会话） */
  function newSession(): void {
    currentSessionId.value = null
    messages.value = []
    streamingContent.value = ''
    streamStatus.value = 'idle'
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    messages,
    streamingContent,
    streamStatus,
    streamError,
    isStreaming,
    loadSessions,
    selectSession,
    sendMessage,
    stopStream,
    removeSession,
    newSession
  }
})
