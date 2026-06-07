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
  return httpClient.post({ url: `${API_PREFIX}`, data })
}

export const updateAsset = (id: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/${id}`, data })
}

export const deleteAsset = (id: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/${id}` })
}

export const syncFromWazuh = (): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/sync/from-wazuh` })
}

// ========== 端口管理 ==========

export const getAssetPorts = (assetId: string, params?: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/ports`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const addAssetPort = (assetId: string, data: any): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/${assetId}/ports`, data })
}

export const updateAssetPort = (portId: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/ports/${portId}`, data })
}

export const deleteAssetPort = (portId: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/ports/${portId}` })
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
  return httpClient.post({ url: `${API_PREFIX}/${assetId}/tags`, data })
}

export const updateAssetTag = (tagId: string, data: any): Promise<any> => {
  return httpClient.put({ url: `${API_PREFIX}/tags/${tagId}`, data })
}

export const deleteAssetTag = (tagId: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/tags/${tagId}` })
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
