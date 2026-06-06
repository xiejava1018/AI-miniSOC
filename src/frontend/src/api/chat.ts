/**
 * Art Bot 聊天 API
 *
 * 流式接口走 utils/http/stream；列表/详情走 utils/http (axios)
 */

import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const PREFIX = '/api/v1/ai/chat'

export interface ChatMessageItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  tokens_used: number
  is_truncated: boolean
  created_at: string
}

export interface ChatSessionItem {
  id: string
  user_id: number
  title: string
  model_name: string
  created_at: string
  updated_at: string
}

export interface ChatSessionDetail extends ChatSessionItem {
  messages: ChatMessageItem[]
}

export interface ChatSessionListResp {
  total: number
  items: ChatSessionItem[]
  page: number
  page_size: number
}

/** 会话列表 */
export const fetchChatSessions = (params?: { page?: number; page_size?: number }) => {
  return httpClient.get<Http.BaseResponse<ChatSessionListResp>>({
    url: `${PREFIX}/sessions`,
    params: { page: 1, page_size: 20, ...params },
    keepFullResponse: true
  })
}

/** 会话详情（消息历史） */
export const fetchChatSessionDetail = (sessionId: string) => {
  return httpClient.get<Http.BaseResponse<ChatSessionDetail>>({
    url: `${PREFIX}/sessions/${sessionId}`,
    keepFullResponse: true
  })
}

/** 删除会话 */
export const deleteChatSession = (sessionId: string) => {
  return httpClient.del<Http.BaseResponse<{ deleted: boolean; id: string }>>({
    url: `${PREFIX}/sessions/${sessionId}`,
    keepFullResponse: true
  })
}
