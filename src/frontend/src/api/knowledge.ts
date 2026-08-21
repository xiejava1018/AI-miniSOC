import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/knowledge'

export interface KnowledgeItem {
  id: string
  title: string
  content: string
  category?: string
  source_type?: string
  source_id?: string
  tags: string[]
  confidence_score: number
  review_status: 'active' | 'pending_review'
  last_validated_at?: string | null
  created_by?: string
  created_at?: string
  updated_at?: string
}

export interface KnowledgeSearchResult {
  question: string
  results: KnowledgeItem[]
  rerank_source: 'glm' | 'recall' | null
  message?: string
}

/** 自然语言搜索（召回 + GLM rerank） */
export const searchKnowledge = (question: string): Promise<Http.BaseResponse<KnowledgeSearchResult>> => {
  return httpClient.post({ url: `${API_PREFIX}/search`, data: { question }, keepFullResponse: true, timeout: 30000 })
}

/** 列表（含懒老化：超 12 个月未验证自动 pending_review） */
export const getKnowledgeList = (params?: Record<string, any>): Promise<any> => {
  return httpClient.get({ url: API_PREFIX, params, keepFullResponse: true })
}

export const createKnowledge = (data: {
  title: string
  content: string
  category?: string
  tags?: string[]
}): Promise<any> => {
  return httpClient.post({ url: API_PREFIX, data, keepFullResponse: true })
}

export const updateKnowledge = (
  id: string,
  data: { title?: string; content?: string; category?: string; tags?: string[] }
): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/${id}`, data, keepFullResponse: true })
}

export const deleteKnowledge = (id: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/${id}`, keepFullResponse: true })
}

/** 人工验证：刷新验证时间 + confidence 90 + 回 active */
export const validateKnowledge = (id: string): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/${id}/validate`, keepFullResponse: true })
}

/** 从已解决事件批量提取（admin；GLM 失败降级模板整理） */
export const autoExtractKnowledge = (days = 90, force = false): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/auto-extract`,
    params: { days, force },
    keepFullResponse: true,
    timeout: 60000
  })
}
