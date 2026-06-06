/**
 * 站内通知 API
 */

import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const PREFIX = '/api/v1/notifications'

export interface NotificationItem {
  id: string
  user_id: number
  type: 'alert' | 'ai_done' | 'system' | 'test'
  title: string
  content: string | null
  link: string | null
  is_read: boolean
  created_at: string
}

export interface NotificationListResp {
  total: number
  items: NotificationItem[]
  page: number
  page_size: number
}

/** 通知列表（可筛选 is_read） */
export const fetchNotifications = (params?: { page?: number; page_size?: number; is_read?: boolean }) => {
  return httpClient.get<Http.BaseResponse<NotificationListResp>>({
    url: `${PREFIX}`,
    params: { page: 1, page_size: 20, ...params },
    keepFullResponse: true
  })
}

/** 未读数 */
export const fetchUnreadCount = () => {
  return httpClient.get<Http.BaseResponse<{ count: number }>>({
    url: `${PREFIX}/unread-count`,
    keepFullResponse: true
  })
}

/** 标记单条已读 */
export const markNotificationRead = (id: string) => {
  return httpClient.post<Http.BaseResponse<NotificationItem>>({
    url: `${PREFIX}/${id}/read`,
    keepFullResponse: true
  })
}

/** 全标已读 */
export const markAllNotificationsRead = () => {
  return httpClient.post<Http.BaseResponse<{ updated: number }>>({
    url: `${PREFIX}/mark-all-read`,
    keepFullResponse: true
  })
}
