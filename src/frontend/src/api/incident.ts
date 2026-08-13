/**
 * 事件管理 API
 *
 * 对接后端 /api/v1/incidents（事件 CRUD + 状态流转）。
 * 事件来源：告警/告警簇一键建事件（Phase 3）、手动创建、MCP。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient
const API_PREFIX = '/api/v1/incidents'

// ── 类型 ────────────────────────────────────────────

export type IncidentStatus = 'open' | 'in_progress' | 'resolved' | 'closed'
export type IncidentSeverity = 'critical' | 'high' | 'medium' | 'low'
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

export interface IncidentItem {
  id: string
  title: string
  description?: string | null
  severity: IncidentSeverity | string
  status: IncidentStatus | string
  wazuh_alert_id?: string | null
  assigned_to?: string | null
  created_by: string
  created_at: string
  updated_at?: string
  resolved_at?: string | null
  resolution_notes?: string | null
  ai_analysis_id?: string | null
}

export interface IncidentListResponse {
  items: IncidentItem[]
  total: number
  skip: number
  limit: number
}

export interface IncidentUpdateData {
  title?: string
  description?: string
  status?: IncidentStatus
  severity?: IncidentSeverity
  assigned_to?: string
  resolution_notes?: string
}

// ── 状态/严重度 选项与配色 ──────────────────────────

export const STATUS_OPTIONS: { label: string; value: IncidentStatus; type: TagType }[] = [
  { label: '待处理', value: 'open', type: 'danger' },
  { label: '处理中', value: 'in_progress', type: 'warning' },
  { label: '已解决', value: 'resolved', type: 'success' },
  { label: '已关闭', value: 'closed', type: 'info' }
]

export const SEVERITY_OPTIONS: { label: string; value: IncidentSeverity; type: TagType }[] = [
  { label: '严重', value: 'critical', type: 'danger' },
  { label: '高', value: 'high', type: 'danger' },
  { label: '中', value: 'medium', type: 'warning' },
  { label: '低', value: 'low', type: 'info' }
]

const statusMap = Object.fromEntries(STATUS_OPTIONS.map((s) => [s.value, s]))
const severityMap = Object.fromEntries(SEVERITY_OPTIONS.map((s) => [s.value, s]))
export const statusMeta = (v: string): { label: string; type: TagType } =>
  (statusMap as Record<string, any>)[v] || { label: v, type: 'info' }
export const severityMeta = (v: string): { label: string; type: TagType } =>
  (severityMap as Record<string, any>)[v] || { label: v, type: 'info' }

// ── API 函数 ─────────────────────────────────────────

/** 事件列表（分页 + status/severity 筛选） */
export const getIncidentList = (
  params?: Record<string, any>
): Promise<Http.BaseResponse<IncidentListResponse>> => {
  return httpClient.get({ url: `${API_PREFIX}/`, params, keepFullResponse: true })
}

/** 事件详情 */
export const getIncidentDetail = (id: string): Promise<Http.BaseResponse<IncidentItem>> => {
  return httpClient.get({ url: `${API_PREFIX}/${id}`, keepFullResponse: true })
}

/** 更新事件（状态流转 / 编辑） */
export const updateIncident = (
  id: string,
  data: IncidentUpdateData
): Promise<Http.BaseResponse<IncidentItem>> => {
  return httpClient.put({ url: `${API_PREFIX}/${id}`, data, keepFullResponse: true })
}
