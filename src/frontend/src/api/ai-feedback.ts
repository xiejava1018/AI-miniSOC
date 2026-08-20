import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/ai'

export type FeedbackTargetType = 'risk_summary' | 'security_summary' | 'query' | 'report' | 'knowledge'

/**
 * 提交 AI 产物反馈（👍/👎 + 可选修正文本）
 * P3/F4.1 反馈闭环：所有 AI 生成内容通用
 */
export const submitAiFeedback = (data: {
  target_type: FeedbackTargetType
  target_id: string
  rating: 'up' | 'down'
  comment?: string
}): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/feedback`, data, keepFullResponse: true })
}

export interface FeedbackSummaryRow {
  target_type: string
  up: number
  down: number
  total: number
  up_rate_percent: number | null
  needs_prompt_review: boolean
}

export const getFeedbackSummary = (days = 30): Promise<Http.BaseResponse<{ days: number; summary: FeedbackSummaryRow[] }>> => {
  return httpClient.get({ url: `${API_PREFIX}/feedback/summary`, params: { days } })
}
