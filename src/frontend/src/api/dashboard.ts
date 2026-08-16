/**
 * 概览仪表板 API
 *
 * 设计文档：docs/design/2026-08-16-概览仪表板设计.md（§5.2 聚合接口）
 * 后端实现：app/api/dashboard.py + app/services/dashboard_service.py
 *
 * - GET /api/v1/dashboard/summary ：一个接口驱动五区块（KPI 六数 + Δ 环比 +
 *   数据源健康 + 新鲜度 + 夜间摘要 + 待办 + AI 洞察）
 * - GET /api/v1/dashboard/trend?days=N ：告警簇趋势（distinct 指纹口径，
 *   复用已修复的 AlertGroupSnapshotService.get_trend）
 *
 * RBAC 裁剪：后端按当前用户可见菜单删除 kpi 的部分键（隐藏而非置灰），
 * 前端对缺失键直接不渲染对应卡片，因此 kpi 子键全部 optional。
 * 显信任原则：后端单模块查询失败时该模块返回 {"error": "..."}，不拖垮整体，
 * 前端同样按 error 字段降级渲染。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/dashboard'

// ── 类型定义 ────────────────────────────────────────

/** 单模块查询失败时后端的降级返回体（显信任原则，不拖垮整体） */
export interface DashboardModuleError {
  error: string
}

export interface DashboardFreshness {
  postgres: string | null
  alert_snapshot: string | null
}

export interface DashboardSourcesHealth {
  postgres: { online: boolean }
  opensearch: { online: boolean; error?: string }
  loki: { online: boolean; error?: string }
  /** RBAC 裁剪：无资产菜单权限时该键被删除 */
  collector?: { managed: number; total: number }
}

export interface ActiveAlertGroupsKpi {
  value: number
  delta_vs_yesterday: number | null
  note?: string
}

export interface OpenIncidentsKpi {
  value: number
  in_progress: number
  closed: number
  /** 0-1 小数（如 0.08 = 8%） */
  closure_rate: number
}

export interface HighVulnsKpi {
  value: number
  critical: number
  high: number
  kev_hits: number
  kev_note?: string
}

export interface BrowsingAnomaliesKpi {
  value: number
  total: number
  prev_24h: number
}

export interface AssetCoverageKpi {
  managed: number
  total: number
  /** 0-1 小数（如 0.3 = 30%） */
  rate: number
  unmanaged_by_criticality: {
    critical?: number
    high?: number
    medium?: number
    normal?: number
    [key: string]: number | undefined
  }
}

export interface IncidentsTodayKpi {
  value: number
  last_7d: number
}

/**
 * kpi 六数——RBAC 裁剪后部分键可能缺失，也可能被替换为 {"error": ...}
 */
export interface DashboardKpi {
  active_alert_groups?: ActiveAlertGroupsKpi | DashboardModuleError
  open_incidents?: OpenIncidentsKpi | DashboardModuleError
  high_vulns?: HighVulnsKpi | DashboardModuleError
  browsing_anomalies_24h?: BrowsingAnomaliesKpi | DashboardModuleError
  asset_coverage?: AssetCoverageKpi | DashboardModuleError
  incidents_today?: IncidentsTodayKpi | DashboardModuleError
}

/** 夜间摘要（昨日 18:00 → 今日 09:00 北京时间）；分项随模块权限裁剪 */
export interface DashboardNightSummary {
  new_alert_groups?: number
  new_incidents?: number
  browsing_anomalies?: number
  kev_new?: number
}

export type DashboardTodoPriority = 'p0' | 'p1' | 'p2'

export interface DashboardTodo {
  id: string
  priority: DashboardTodoPriority
  title: string
  detail: string
  action: string
}

export interface DashboardAiTopGroup {
  fingerprint?: string
  rule_description: string | null
  agent_id: string
  agent_ip?: string | null
  priority: string
  confidence: number
  recommended_action: string
}

export interface DashboardAiInsight {
  coverage: { group_analyses: number; single_analyses: number }
  top_groups: DashboardAiTopGroup[]
}

export interface DashboardSummary {
  generated_at: string
  /** 态势条时间窗（24/168 小时），后端回显 */
  window_hours?: number
  freshness: DashboardFreshness | DashboardModuleError
  sources_health: DashboardSourcesHealth | DashboardModuleError
  kpi: DashboardKpi | DashboardModuleError
  night_summary: DashboardNightSummary | DashboardModuleError
  todos: DashboardTodo[] | DashboardModuleError
  ai_insight?: DashboardAiInsight | DashboardModuleError
}

export interface DashboardTrendPoint {
  date: string
  clusters: number
  alerts: number
  linked_assets: number
}

export interface DashboardTrendResponse {
  days: DashboardTrendPoint[]
  span_days: number
}

// ── 类型守卫 ────────────────────────────────────────

/** 模块数据是否为降级错误体 */
export const isModuleError = (
  v: unknown
): v is DashboardModuleError =>
  typeof v === 'object' && v !== null && 'error' in v

// ── API 函数 ─────────────────────────────────────────

/** 态势条时间窗：24=近24h，168=近7天（仅影响窗口型 KPI） */
export type DashboardWindowHours = 24 | 168

/** 概览仪表板聚合数据（KPI + 健康 + 待办 + AI 洞察一次返回） */
export const getDashboardSummary = (
  hours: DashboardWindowHours = 24
): Promise<Http.BaseResponse<DashboardSummary>> => {
  return httpClient.get({
    url: `${API_PREFIX}/summary`,
    params: { hours },
    keepFullResponse: true,
    showErrorMessage: false
  })
}

/** 告警簇趋势（distinct 指纹口径，1-90 天） */
export const getDashboardTrend = (
  days = 14
): Promise<Http.BaseResponse<DashboardTrendResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/trend`,
    params: { days },
    keepFullResponse: true,
    showErrorMessage: false
  })
}
