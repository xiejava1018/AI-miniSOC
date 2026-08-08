/**
 * 上网行为异常检测 API
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient
const API_PREFIX = '/api/v1'

/** 将 useTable 的 current/size 转为后端的 page/page_size */
const normalizePaginationParams = (params?: Record<string, any>) => {
  if (!params) return undefined
  const { current, size, page, pageSize, page_size, ...rest } = params
  return {
    ...rest,
    page: page ?? current ?? 1,
    page_size: page_size ?? pageSize ?? size ?? 10
  }
}

// ── 事件 ──────────────────────────────────────────

export const getBrowsingEvents = (params: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/events`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const getBrowsingEvent = (id: string): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/events/${id}`,
    keepFullResponse: true
  })
}

export const updateBrowsingEvent = (id: string, data: any): Promise<any> => {
  return httpClient.put({
    url: `${API_PREFIX}/browsing/events/${id}`,
    data,
    keepFullResponse: true
  })
}

export const whitelistBrowsingEvent = (id: string): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/browsing/events/${id}/whitelist`,
    keepFullResponse: true
  })
}

export const analyzeBrowsingEvent = (id: string): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/browsing/events/${id}/analyze`,
    keepFullResponse: true,
    timeout: 120000
  })
}

export const getBrowsingEventLogs = (id: string, limit: number = 100): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/events/${id}/logs`,
    params: { limit },
    keepFullResponse: true
  })
}

/** 查询原始行为日志（多条件） */
export const queryBrowsingLogs = (params: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/logs`,
    params,
    keepFullResponse: true
  })
}

// ── 黑名单 ────────────────────────────────────────

export const getBrowsingBlacklist = (params: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/blacklist`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

export const addBrowsingBlacklist = (data: any): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/browsing/blacklist`,
    data,
    keepFullResponse: true
  })
}

export const deleteBrowsingBlacklist = (id: number): Promise<any> => {
  return httpClient.del({
    url: `${API_PREFIX}/browsing/blacklist/${id}`,
    keepFullResponse: true
  })
}

// ── 基线 ──────────────────────────────────────────

export const getBrowsingBaseline = (params: Record<string, any>): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/baseline`,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

// ── 统计 / 配置 ───────────────────────────────────

export const getBrowsingStats = (): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/stats`,
    keepFullResponse: true
  })
}

/** 行为统计概览（多维度聚合） */
export const getBrowsingStatistics = (hours: number = 24): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/statistics`,
    params: { hours },
    keepFullResponse: true
  })
}

export const getBrowsingRulesConfig = (): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/browsing/rules/config`,
    keepFullResponse: true
  })
}

export const updateBrowsingRulesConfig = (configs: Record<string, any>): Promise<any> => {
  return httpClient.put({
    url: `${API_PREFIX}/browsing/rules/config`,
    data: configs,
    keepFullResponse: true
  })
}

export const testBrowsingRules = (minutes: number): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/browsing/rules/test`,
    data: { minutes },
    keepFullResponse: true
  })
}
