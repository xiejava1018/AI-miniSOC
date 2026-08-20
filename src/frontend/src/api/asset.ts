import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/assets'

type BackendListResponse<T> = Http.BaseResponse<T[]> & {
  total?: number
  current?: number
  page?: number
  pageSize?: number
  size?: number
}

/**
 * 将前端分页参数 (page/pageSize) 转换为后端 skip/limit 格式
 */
const normalizePaginationParams = (params?: Record<string, any>) => {
  if (!params) return undefined
  const { current, size, page, pageSize, ...rest } = params

  const p = page ?? current ?? 1
  const ps = pageSize ?? size ?? 10

  return {
    ...rest,
    skip: (p - 1) * ps,
    limit: ps
  }
}

// ========== 资产管理 ==========

export const getAssetList = (
  params?: Record<string, any>
): Promise<BackendListResponse<Api.Asset.AssetListItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const getAssetDetail = (id: string): Promise<Http.BaseResponse<Api.Asset.AssetListItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}/${id}`,
    keepFullResponse: true
  })
}

/**
 * 获取资产安全摘要(详情页 v2)
 *
 * 后端:`GET /api/v1/assets/{id}/summary`
 * 字段定义见 `Api.Asset.AssetSummary` 与 docs/design/2026-06-03-asset-detail-v2-design.md §7.1
 */
export const getAssetSummary = (id: string): Promise<Http.BaseResponse<Api.Asset.AssetSummary>> => {
  return httpClient.get({
    url: `${API_PREFIX}/${id}/summary`,
    keepFullResponse: true
  })
}

/**
 * 获取资产概览聚合数据
 *
 * 后端:`GET /api/v1/assets/overview`
 * 字段定义见 `Api.Asset.AssetOverview` 与 docs/design/2026-06-03-asset-overview-design.md §5.1
 * 1 次调用产出 KPI + 3 张分布 + 24h 趋势 + 2 张 Top 表
 * 任意子步骤失败字段降级为 0/空,不影响整体响应
 */
export const getAssetOverview = (): Promise<Http.BaseResponse<Api.Asset.AssetOverview>> => {
  return httpClient.get({
    url: `${API_PREFIX}/overview`,
    keepFullResponse: true
  })
}

/**
 * 获取资产的所有数据来源
 *
 * 后端: `GET /api/v1/assets/{id}/sources`
 */
export const getAssetSources = (id: string): Promise<Http.BaseResponse<any[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}/${id}/sources`,
    keepFullResponse: true
  })
}

export const addAsset = (data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}`, data, keepFullResponse: true })
}

export const updateAsset = (id: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/${id}`, data, keepFullResponse: true })
}

export const deleteAsset = (id: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/${id}`, keepFullResponse: true })
}

export const syncFromWazuh = (): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/sync/from-wazuh`, keepFullResponse: true })
}

// ========== 端口管理 ==========

export const getAssetPorts = (assetId: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/ports`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

// M3：应用清单（OpenSearch states-inventory-packages 直查）
export interface AssetApplication {
  name: string
  version: string | null
  type: string | null
  size: number
  path: string | null
}

export const getAssetApplications = (
  assetId: string,
  params?: { search?: string; skip?: number; limit?: number }
): Promise<{
  items: AssetApplication[]
  total: number
  not_applicable?: boolean
  reason?: string
}> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/applications`,
    params,
    keepFullResponse: true
  }) as Promise<any>
}

// M4：Wazuh 实时监听端口（带进程信息，与本地端口双源合并）
export interface WazuhPort {
  port: number
  protocol: string | null
  state: string | null
  local_ip: string | null
  process: string | null
  pid: number | null
}

export const getAssetWazuhPorts = (assetId: string): Promise<{ items: WazuhPort[]; not_applicable?: boolean; reason?: string }> => {
  return httpClient.get({ url: `${API_PREFIX}/${assetId}/wazuh-ports`, keepFullResponse: true }) as Promise<any>
}

export const addAssetPort = (assetId: string, data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/${assetId}/ports`, data, keepFullResponse: true })
}

export const updateAssetPort = (portId: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/ports/${portId}`, data, keepFullResponse: true })
}

export const deleteAssetPort = (portId: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/ports/${portId}`, keepFullResponse: true })
}

// ========== 标签管理 ==========

export const getAssetTags = (assetId: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/tags`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const addAssetTag = (assetId: string, data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/${assetId}/tags`, data, keepFullResponse: true })
}

export const updateAssetTag = (tagId: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/tags/${tagId}`, data, keepFullResponse: true })
}

export const deleteAssetTag = (tagId: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/tags/${tagId}`, keepFullResponse: true })
}

export const getCommonTagKeys = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/tags/common-keys` })
}

// ========== 资产-事件关联 ==========

export const getAssetIncidents = (assetId: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/incidents`,
    params,
    keepFullResponse: true
  })
}

// ========== P3/F1.1 资产风险评分 ==========

export interface AssetRiskDetail {
  asset_id: string
  asset_name?: string
  asset_ip?: string
  risk_score: number | null
  risk_summary?: string | null
  risk_scored_at?: string | null
  score_breakdown?: {
    total: number
    delta_7d?: number
    dimensions: Record<string, {
      score: number
      weight: number
      effective_weight: number
      data_gap: boolean
      reasons: string[]
      inputs?: Record<string, any>
    }>
  } | null
  summary_source?: 'glm' | 'rule' | null
}

export interface RiskOverview {
  distribution: { low: number; medium: number; high: number; critical: number; na: number }
  total_assets: number
  top10: Array<{ asset_id: string; name?: string; ip: string; risk_score: number; risk_summary?: string }>
  rising: Array<{ asset_id: string; name?: string; ip: string; risk_score: number; delta_7d: number }>
  budget: Record<string, any>
}

export const getAssetRisk = (id: string): Promise<Http.BaseResponse<AssetRiskDetail>> => {
  return httpClient.get({ url: `${API_PREFIX}/${id}/risk` })
}

export const getAssetRiskHistory = (id: string, days = 90): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/${id}/risk/history`, params: { days } })
}

export const batchScoreRisk = (): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/risk/batch-score`, keepFullResponse: true })
}

export const getRiskOverview = (): Promise<Http.BaseResponse<RiskOverview>> => {
  return httpClient.get({ url: `${API_PREFIX}/risk/overview` })
}

export const getRiskRules = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/risk/rules` })
}

export const updateRiskRules = (override: Record<string, any>): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/risk/rules`, data: { override }, keepFullResponse: true })
}

// ========== P3/F2.1 L1 自然语言查询 ==========

export interface AskResult {
  level: 'L1'
  intent: string
  params?: Record<string, any>
  total?: number
  assets?: Array<Record<string, any>>
  stats?: Record<string, number>
  stats_dimension?: string
  summary?: string
  message?: string
  session_id?: string
}

export const askAssetQuery = (question: string, sessionId?: string): Promise<Http.BaseResponse<AskResult>> => {
  return httpClient.post({ url: `${API_PREFIX}/ask`, data: { question, session_id: sessionId || null } })
}

export const getAskHistory = (limit = 20): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/ask/history`, params: { limit } })
}
