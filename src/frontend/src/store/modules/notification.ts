/**
 * 站内通知状态
 *
 * - 未读数（铃铛 Badge）
 * - 通知列表（抽屉用）
 * - WebSocket 实时推送（依赖 utils/socket）
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElNotification } from 'element-plus'
import WebSocketClient from '@/utils/socket'
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem
} from '@/api/notification'

export type WsStatus = 'idle' | 'connecting' | 'open' | 'closed'

export const useNotificationStore = defineStore('notificationStore', () => {
  // ============== state ==============
  const unreadCount = ref(0)
  const list = ref<NotificationItem[]>([])
  const wsStatus = ref<WsStatus>('idle')
  let wsClient: WebSocketClient | null = null

  // ============== action ==============

  async function loadUnread(): Promise<void> {
    try {
      const res = await fetchUnreadCount()
      unreadCount.value = res.data.count
    } catch (e) {
      console.error('[notify] load unread failed:', e)
    }
  }

  async function loadList(page = 1, pageSize = 50): Promise<void> {
    try {
      const res = await fetchNotifications({ page, page_size: pageSize })
      list.value = res.data.items
    } catch (e) {
      console.error('[notify] load list failed:', e)
    }
  }

  async function markRead(id: string): Promise<void> {
    try {
      await markNotificationRead(id)
      // 本地乐观更新
      const item = list.value.find((n) => n.id === id)
      if (item && !item.is_read) {
        item.is_read = true
        unreadCount.value = Math.max(0, unreadCount.value - 1)
      }
    } catch (e) {
      console.error('[notify] mark read failed:', e)
    }
  }

  async function markAllRead(): Promise<void> {
    try {
      await markAllNotificationsRead()
      list.value.forEach((n) => (n.is_read = true))
      unreadCount.value = 0
    } catch (e) {
      console.error('[notify] mark all read failed:', e)
    }
  }

  /** 处理 WebSocket 推来的消息 */
  function handleIncoming(payload: unknown): void {
    // payload 结构：{ type: "notification", data: { id, title, content, ... } }
    if (
      payload &&
      typeof payload === 'object' &&
      (payload as { type?: string }).type === 'notification'
    ) {
      const data = (payload as { data: NotificationItem }).data
      // 顶部 toast 提示
      ElNotification({
        title: data.title,
        message: data.content || '',
        type: data.type === 'alert' ? 'warning' : 'info',
        duration: 5000,
        position: 'top-right'
      })
      // 更新未读数 + 列表
      unreadCount.value += 1
      list.value.unshift(data)
    }
  }

  /** 启动 WebSocket 连接 */
  function connect(): void {
    if (wsClient) return // 单例
    wsStatus.value = 'connecting'

    const baseWs = import.meta.env.VITE_APP_WS_URL as string
    if (!baseWs) {
      console.warn('[notify] VITE_APP_WS_URL not set, skip WS connect')
      wsStatus.value = 'closed'
      return
    }

    const token = localStorage.getItem('accessToken') || ''
    if (!token) {
      console.warn('[notify] no access token, skip WS connect')
      wsStatus.value = 'closed'
      return
    }

    wsClient = WebSocketClient.getInstance({
      url: `${baseWs}/notifications?token=${encodeURIComponent(token)}`,
      messageHandler: (ev: MessageEvent) => {
        try {
          const payload = JSON.parse(ev.data)
          handleIncoming(payload)
        } catch (e) {
          console.warn('[notify] parse ws message failed:', e)
        }
      }
    })
    wsClient.init()
    wsStatus.value = 'open'

    // 顺手拉一次未读数
    void loadUnread()
  }

  function disconnect(): void {
    // WebSocketClient 单例不主动 close，但状态标记
    wsStatus.value = 'closed'
  }

  return {
    unreadCount,
    list,
    wsStatus,
    loadUnread,
    loadList,
    markRead,
    markAllRead,
    connect,
    disconnect,
    handleIncoming
  }
})
