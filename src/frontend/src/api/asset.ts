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

export const getAssetPorts = (
  assetId: string,
  params?: Record<string, any>
): Promise<any> => {
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

export const getAssetTags = (
  assetId: string,
  params?: Record<string, any>
): Promise<any> => {
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

export const getAssetIncidents = (
  assetId: string,
  params?: Record<string, any>
): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/incidents`,
    params,
    keepFullResponse: true
  })
}
