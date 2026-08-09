/**
 * 告警 API
 *
 * 后端已接入真实 Wazuh OpenSearch 数据,支持列表/统计/趋势/资产排名等完整功能。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/alerts'

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
    url: `${API_PREFIX}/`,
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
    url: `${API_PREFIX}/`,
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
    url: `${API_PREFIX}/`,
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

// ── 告警治理(簇聚合 + 摘要) ──────────────────────────

/** 单条告警样本(与 _normalize_alerts 对齐) */
export interface AlertSample {
  id: string
  timestamp?: string
  rule: AlertRule
  agent: AlertAgent
  location?: string
  full_log?: string
  data?: Record<string, any>
}

/** 告警簇(按 rule.id|agent.id 聚合) */
export interface AlertGroup {
  fingerprint: string
  rule_id: number
  rule_description: string | null
  agent_id: string
  agent_name: string | null
  agent_ip: string | null
  count: number
  level_min: number | null
  level_max: number | null
  first_seen: string | null
  last_seen: string | null
  top_srcips: string[] | null
  sample: AlertSample | null
  // —— Phase 1: AI 研判结论（来自 /groups/triage-top 或 digest.top_groups）——
  ai_priority?: string | null
  ai_is_noise?: boolean | null
  ai_confidence?: number | null
  ai_rationale?: string | null
  ai_action?: string | null
  ai_suggest_incident?: boolean | null
  ai_source?: string | null
  ai_model?: string | null
  ai_verdict_at?: string | null
}

/** 告警簇 AI 研判 verdict（来自 /groups/{fp}/triage 或 /groups/triage-top） */
export interface AlertGroupTriage {
  fingerprint: string
  rule_id?: string | null
  agent_id?: string | null
  priority: string
  is_noise: boolean
  confidence: number
  rationale?: string | null
  recommended_action?: string | null
  suggest_incident: boolean
  source: string
  model_name?: string | null
  window_hours?: number | null
  linked_asset_id?: string | null
  created_at?: string | null
  expires_at?: string | null
}

/** 告警簇明细(单簇下钻) */
export interface AlertGroupDetail {
  fingerprint: string
  rule_id: number
  rule_description: string | null
  agent_id: string
  agent_name: string | null
  agent_ip: string | null
  count: number
  level_min: number | null
  level_max: number | null
  first_seen: string | null
  last_seen: string | null
  top_srcips: string[]
  distinct_srcips: number
  linked_asset: Record<string, any> | null
  samples: AlertSample[]
}

/** 告警治理摘要(落库快照) */
export interface AlertDigest {
  id: string
  period_type: string
  period_start: string | null
  period_end: string | null
  total_alerts: number
  by_level: { level: number; count: number }[]
  top_groups: AlertGroup[]
  top_assets: {
    ip: string
    alert_count: number
    critical_count: number
    asset_id?: string
    asset_name?: string
    criticality?: string
  }[]
  trend: { hour: string; total: number; critical: number }[]
  summary_text: string
  ai_model: string
  created_at: string
}

/** 告警簇聚合(去重为有限个"簇") */
export const getAlertGroups = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<{ total_groups: number; groups: AlertGroup[] }>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups`,
    params,
    keepFullResponse: true
  })
}

/** 单簇明细：样本 + 等级/时间分布 + 源 IP + 关联资产 */
export const getAlertGroupDetail = (
  fingerprint: string,
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertGroupDetail>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups/${fingerprint}`,
    params,
    keepFullResponse: true
  })
}

/** 获取最新(或按日期)告警摘要 */
export const getAlertDigest = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertDigest>> => {
  return httpClient.get({
    url: `${API_PREFIX}/digest`,
    params,
    keepFullResponse: true
  })
}

/** 生成(并落库)一份告警摘要。hours 走查询串(后端用 Query 读取) */
export const generateAlertDigest = (
  hours = 24
): Promise<Http.BaseResponse<AlertDigest>> => {
  return httpClient.post({
    url: `${API_PREFIX}/digest/generate?hours=${hours}`,
    keepFullResponse: true
  })
}

// ── 告警簇历史快照(方案 B) ──────────────────────────

/** 告警簇历史快照记录 */
export interface AlertGroupHistory {
  id: string
  snapshot_at: string
  window_hours: number
  fingerprint: string
  rule_id: string | null
  rule_description: string | null
  agent_id: string | null
  agent_name: string | null
  agent_ip: string | null
  count: number
  level_min: number | null
  level_max: number | null
  first_seen: string | null
  last_seen: string | null
  distinct_srcips: number | null
  top_srcips: Array<{ ip: string; count?: number }> | null
  linked_asset_id: string | null
  // —— Phase 1: 历史快照回填的 AI verdict ——
  ai_priority?: string | null
  ai_is_noise?: boolean | null
  ai_suggest_incident?: boolean | null
  ai_verdict_at?: string | null
}

/** 趋势点 */
export interface AlertGroupTrendPoint {
  date: string
  clusters: number
  alerts: number
  linked_assets: number
}

/** 历史快照列表（来自 soc_alert_groups） */
export const getAlertGroupHistory = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertGroupHistory[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups/history`,
    params,
    keepFullResponse: true
  })
}

/** 趋势数据（按快照日聚合） */
export const getAlertGroupTrend = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<{ days: AlertGroupTrendPoint[]; span_days: number }>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups/trend`,
    params,
    keepFullResponse: true
  })
}

// ── 告警簇 AI 研判(Phase 1) ─────────────────────────

/** 今日必处理清单：对 TopN 告警簇做 AI 研判，按 P0>P1>P2>P3 排序返回 */
export const getAlertTriageTop = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertGroup[]>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups/triage-top`,
    params,
    keepFullResponse: true,
    timeout: 120000
  })
}

/** 对单簇触发/刷新 AI 研判，返回结构化 verdict */
export const triageAlertGroup = (
  fingerprint: string,
  params?: Record<string, any>
): Promise<Http.BaseResponse<AlertGroupTriage>> => {
  return httpClient.post({
    url: `${API_PREFIX}/groups/${fingerprint}/triage`,
    params,
    keepFullResponse: true,
    timeout: 60000
  })
}

/** 取某告警簇缓存的 AI verdict（无则 404） */
export const getAlertGroupTriage = (
  fingerprint: string
): Promise<Http.BaseResponse<AlertGroupTriage>> => {
  return httpClient.get({
    url: `${API_PREFIX}/groups/${fingerprint}/triage`,
    keepFullResponse: true
  })
}
