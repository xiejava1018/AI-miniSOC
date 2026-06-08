/**
 * 告警 API
 *
 * 后端已接入真实 Wazuh OpenSearch 数据,支持列表/统计/趋势/资产排名等完整功能。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/alerts/'

// ── 类型定义 ────────────────────────────────────────

export interface AlertRule {
  level: number
  description: string
  id: number
  groups?: string[]
}

export interface AlertAgent {
  id: string
  name: string
  ip: string
}

export interface AlertItem {
  id: string
  timestamp: string
  rule: AlertRule
  agent: AlertAgent
  location: string
  full_log?: string
}

export interface AlertListResponse {
  items: AlertItem[]
  total: number
  skip: number
  limit: number
}

export interface AlertLevelBucket {
  level: string
  count: number
}

export interface AgentBucket {
  agent: string
  count: number
}

export interface RuleBucket {
  description: string
  count: number
}

export interface AlertStatisticsResponse {
  period: string
  by_level: AlertLevelBucket[]
  top_agents: AgentBucket[]
  top_rules: RuleBucket[]
}

export interface AlertTrendPoint {
  hour: string
  total: number
  critical: number
}

export interface TopAlertAsset {
  ip: string
  alert_count: number
  critical_count: number
  last_alert_at: string
}

// ── 工具 ────────────────────────────────────────────

/** 将前端分页参数(current/size)转为后端skip/limit，保留排序参数 */
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

// ── API 函数 ─────────────────────────────────────────

/** 告警列表（分页+筛选） */
export const getAlertList = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertListResponse>> => {
  return httpClient.get({
    url: API_PREFIX,
    params: normalizePaginationParams(params),
    keepFullResponse: true
  })
}

/** 按资产 IP 查询告警 */
export const getAlertsByIp = (
  ip: string,
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertListResponse>> => {
  return httpClient.get({
    url: API_PREFIX,
    params: { ...normalizePaginationParams(params), ip },
    keepFullResponse: true
  })
}

/** 按 Wazuh Agent ID 查询告警（更准确） */
export const getAlertsByAgentId = (
  agentId: string,
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertListResponse>> => {
  return httpClient.get({
    url: API_PREFIX,
    params: { ...normalizePaginationParams(params), agent_id: agentId },
    keepFullResponse: true
  })
}

/** 告警详情 */
export const getAlertDetail = (alertId: string): Promise<Http.BaseResponse<AlertItem>> => {
  return httpClient.get({
    url: `${API_PREFIX}/${alertId}`,
    keepFullResponse: true
  })
}

/** 告警统计(按等级/agent/规则分布) */
export const getAlertStatistics = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertStatisticsResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/statistics`,
    params,
    keepFullResponse: true
  })
}

/** 告警趋势(小时级聚合) */
export const getAlertTrend = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertTrendPoint[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}/trend`,
    params,
    keepFullResponse: true
  })
}

/** 告警最多的资产 Top N */
export const getTopAlertAssets = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<TopAlertAsset[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}/top-assets`,
    params,
    keepFullResponse: true
  })
}
