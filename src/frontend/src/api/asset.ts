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

export const getAssetWazuhPorts = (
  assetId: string
): Promise<{ items: WazuhPort[]; not_applicable?: boolean; reason?: string }> => {
  return httpClient.get({
    url: `${API_PREFIX}/${assetId}/wazuh-ports`,
    keepFullResponse: true
  }) as Promise<any>
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
    dimensions: Record<
      string,
      {
        score: number
        weight: number
        effective_weight: number
        data_gap: boolean
        reasons: string[]
        inputs?: Record<string, any>
      }
    >
  } | null
  summary_source?: 'glm' | 'rule' | null
}

export interface RiskOverview {
  distribution: { low: number; medium: number; high: number; critical: number; na: number }
  total_assets: number
  top10: Array<{
    asset_id: string
    name?: string
    ip: string
    risk_score: number
    risk_summary?: string
  }>
  rising: Array<{
    asset_id: string
    name?: string
    ip: string
    risk_score: number
    delta: number
  }>
  budget: Record<string, any>
}

export const getAssetRisk = (id: string): Promise<Http.BaseResponse<AssetRiskDetail>> => {
  return httpClient.get({ url: `${API_PREFIX}/${id}/risk`, keepFullResponse: true })
}

export const getAssetRiskHistory = (id: string, days = 90): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/${id}/risk/history`,
    params: { days },
    keepFullResponse: true
  })
}

/** 单资产按需生成风险摘要（详情页「刷新」；N/A 资产返回 message） */
export const refreshAssetRiskSummary = (
  id: string
): Promise<Http.BaseResponse<AssetRiskDetail & { message?: string }>> => {
  return httpClient.post({
    url: `${API_PREFIX}/${id}/risk/refresh-summary`,
    keepFullResponse: true,
    timeout: 30000
  })
}

// ========== P3/F1.2 资产安全态势摘要（告警簇+事件+风险聚合 → GLM 摘要） ==========

export interface SecuritySummaryStats {
  asset: { name?: string; ip: string; os?: string; criticality?: string }
  window: { days: number; start: string; end: string }
  alert_groups: {
    total: number
    by_priority: Record<string, number>
    top_rules: Array<{ description: string; count: number }>
  }
  incidents: {
    total: number
    open: number
    recent: Array<{ title: string; status?: string; severity?: string }>
  }
  risk: { risk_score: number | null; risk_summary?: string | null }
  latest_group_at?: string | null
}

export interface SecuritySummaryResult {
  asset_id: string
  summary: string
  summary_source: 'glm' | 'rule'
  stats: SecuritySummaryStats
  generated_at: string
}

export const getAssetSecuritySummary = (
  id: string,
  days = 30,
  force = false
): Promise<Http.BaseResponse<SecuritySummaryResult>> => {
  return httpClient.get({
    url: `${API_PREFIX}/${id}/security-summary`,
    params: { days, force },
    keepFullResponse: true,
    timeout: 30000
  })
}

export const batchScoreRisk = (): Promise<any> => {
  // 批量评分含 GLM 摘要时可达数十秒（per_run_cap=20 × 摘要耗时），
  // 单独放宽到 120s（全局默认 15s 会超时报"网络错误"）
  return httpClient.post({
    url: `${API_PREFIX}/risk/batch-score`,
    keepFullResponse: true,
    timeout: 120000
  })
}

export const getRiskOverview = (): Promise<Http.BaseResponse<RiskOverview>> => {
  return httpClient.get({ url: `${API_PREFIX}/risk/overview`, keepFullResponse: true })
}

export const getRiskRules = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/risk/rules`, keepFullResponse: true })
}

export const updateRiskRules = (override: Record<string, any>): Promise<any> => {
  return httpClient.put({
    url: `${API_PREFIX}/risk/rules`,
    data: { override },
    keepFullResponse: true
  })
}

// ========== P3/F2.1 L1 + L2 自然语言查询 ==========

/** L2 告警分级计数（服务端聚合，exact=true 表示无截断） */
export interface AskAlertBuckets {
  critical: number
  high: number
  medium: number
  low: number
  total: number
  window_days?: number
  exact?: boolean
}

/** 统计类查询的数据覆盖率——missing 不为 0 时必须向用户披露 */
export interface AskCoverage {
  total?: number
  counted?: number
  missing?: number
  offline_total?: number
  judged?: number
  unknown?: number
}

export interface AskResult {
  level: 'L1' | 'L2'
  /** L1: filter/stats/detail/unsupported/unavailable；L2: template/invalid_params/error */
  intent: string
  params?: Record<string, any>
  total?: number
  assets?: Array<Record<string, any>>
  stats?: Record<string, number>
  stats_dimension?: string
  summary?: string
  message?: string
  session_id?: string
  // ── L2 特有 ──
  template_id?: string
  template_name?: string
  templates_version?: number
  notes?: string[]
  coverage?: AskCoverage
  alerts?: {
    days?: number
    buckets?: AskAlertBuckets
    high_samples?: Array<{ level: number; description: string; timestamp: string | null }>
  }
  data_degraded?: boolean
}

export const askAssetQuery = (
  question: string,
  sessionId?: string
): Promise<Http.BaseResponse<AskResult>> => {
  return httpClient.post({
    url: `${API_PREFIX}/ask`,
    data: { question, session_id: sessionId || null },
    keepFullResponse: true,
    // L2 走 OpenSearch 聚合 + 两次 GLM（路由 + 摘要），实测可达 30s+
    timeout: 120000
  })
}

export const getAskHistory = (limit = 20): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/ask/history`,
    params: { limit },
    keepFullResponse: true
  })
}

// ========== P3/F3.2 资产生命周期（EOL / 保修） ==========

export interface LifecycleItem {
  asset_id: string
  name: string
  ip: string
  os: string
  eol_date?: string
  days_left?: number
  source?: string // preset=参考表匹配 / manual=人工指定
  eol_ref?: string // 命中的参考条目名（如 "Ubuntu 24.04 LTS"）
  eol_unverified?: boolean // true=该参考条目为预估口径，待人工核实
  eol_note?: string
  warranty_end?: string
  warranty_days_left?: number
}

export interface LifecycleOverview {
  eol_expired: LifecycleItem[]
  eol_within_30d: LifecycleItem[]
  eol_within_90d: LifecycleItem[]
  warranty_expired: LifecycleItem[]
  warranty_within_30d: LifecycleItem[]
  unmatched_count: number
}

export const getLifecycleOverview = (): Promise<Http.BaseResponse<LifecycleOverview>> => {
  return httpClient.get({ url: `${API_PREFIX}/lifecycle/overview`, keepFullResponse: true })
}

export const refreshLifecycleEol = (): Promise<any> => {
  return httpClient.post({ url: `${API_PREFIX}/lifecycle/refresh-eol`, keepFullResponse: true })
}

export const getEolReference = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/lifecycle/eol-reference`, keepFullResponse: true })
}

/** 手动覆盖 EOL（优先于参考表，落审计） */
export const overrideAssetEol = (id: string, eolDate: string): Promise<any> => {
  return httpClient.put({
    url: `${API_PREFIX}/${id}/eol`,
    data: { eol_date: eolDate },
    keepFullResponse: true
  })
}

/** 恢复自动匹配（清除人工覆盖，立即按参考表重算） */
export const clearAssetEol = (id: string): Promise<any> => {
  return httpClient.del({ url: `${API_PREFIX}/${id}/eol`, keepFullResponse: true })
}

// ============================================================================
// P3/F3.3 合规基线（判定层零 LLM，解读层仅对 fail 生成）
// ============================================================================

export interface ComplianceRule {
  id: string
  version: number
  title: string
  category: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  baseline?: string
  rationale?: string
  remediation_hint?: string
  scope?: Record<string, string[]>
  requires?: string[]
  check?: Record<string, any>
}

export interface ComplianceRunStats {
  per_rule: Record<
    string,
    {
      title: string
      severity: string
      category: string
      version: number
      pass: number
      fail: number
      unknown: number
      skipped: number
    }
  >
  fail_by_severity: Record<string, number>
  skipped_total: number
  notes?: Record<string, string>
}

export interface ComplianceRun {
  id: string
  ruleset_version: string
  ruleset_name: string
  rules_total: number
  assets_total: number
  assets_in_scope: number
  pass_count: number
  fail_count: number
  unknown_count: number
  /** 达标率 = pass/(pass+fail)；无可判定项时 null */
  compliance_rate: number | null
  /** 覆盖率 = (pass+fail)/(pass+fail+unknown)，必须与达标率同时展示 */
  coverage_rate: number | null
  stats: ComplianceRunStats
  triggered_by: string
  created_at: string
}

export interface ComplianceFinding {
  id: string
  asset_id: string
  asset_name?: string | null
  asset_ip?: string | null
  rule_id: string
  rule_version: number
  rule_title: string
  category: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  status: 'fail' | 'unknown'
  reason: string
  evidence: Record<string, any>
  ai_remediation?: string | null
  ai_model?: string | null
  ai_prompt_version?: string | null
  ai_generated_at?: string | null
}

/** 规则库（含版本，审计对照） */
export const getComplianceRules = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/compliance/rules`, keepFullResponse: true })
}

/** 最近一次巡检 */
export const getLatestComplianceRun = (): Promise<any> => {
  return httpClient.get({ url: `${API_PREFIX}/compliance/latest`, keepFullResponse: true })
}

/** 执行巡检（纯规则判定，不调 AI） */
export const runComplianceCheck = (): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/compliance/run-check`,
    keepFullResponse: true,
    timeout: 120000
  })
}

/** 问题项列表 */
export const getComplianceFindings = (params: {
  run_id?: string
  status?: 'fail' | 'unknown'
  severity?: string
  rule_id?: string
  page?: number
  page_size?: number
}): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/compliance/findings`,
    params,
    keepFullResponse: true
  })
}

/** AI 生成整改建议（仅 fail 项） */
export const interpretCompliance = (limit = 10, force = false): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/compliance/interpret`,
    params: { limit, force },
    keepFullResponse: true,
    timeout: 180000
  })
}

/** 单资产逐规则判定（即时重算） */
export const getAssetCompliance = (assetId: string): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/compliance/assets/${assetId}`,
    keepFullResponse: true
  })
}

// ==================== P3/F1.3 资产稽核 + 数据健康 ====================

export type ReconciliationType = 'shadow' | 'offline' | 'mismatch'
export type ReconciliationStatus = 'pending' | 'confirmed' | 'ignored' | 'resolved'

/** 数据新鲜度快照。degraded 为 true 时页面必须显示告警横幅 */
export interface ReconFreshness {
  checked_at: string
  wazuh_reachable: boolean
  wazuh_error?: string | null
  last_sync_at?: string | null
  last_sync_status?: string | null
  sync_stale: boolean
  unhealthy_sources: Array<{
    source_key: string
    source_type?: string
    reason: string
    last_success_at?: string | null
    last_failure_message?: string | null
  }>
  dead_letter_pending: number
  degraded: boolean
}

export interface ReconciliationItem {
  id: string
  run_id: string
  task_id?: string | null
  asset_id?: string | null
  reconciliation_type: ReconciliationType
  details: {
    freshness?: ReconFreshness
    agent?: Record<string, any>
    ledger?: Record<string, any>
    diffs?: Array<{
      field: string
      label: string
      ledger_value: any
      actual_value: any
    }>
    reason?: string
    disconnected_days?: number | null
    last_keep_alive?: string | null
    suggestion?: string
    linked_by?: string
  }
  status: ReconciliationStatus
  resolved_by?: string | null
  resolved_at?: string | null
  resolve_note?: string | null
  created_at: string
}

/** 触发稽核。Wazuh 不可达时后端返回 503，不会伪装成「无差异」 */
export const runReconcile = (): Promise<any> => {
  return httpClient.post({
    url: `${API_PREFIX}/reconcile`,
    keepFullResponse: true,
    timeout: 120000
  })
}

/** 最近一次稽核摘要（差异分布 + 数据新鲜度） */
export const getReconcileSummary = (runId?: string): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/reconcile/summary`,
    params: runId ? { run_id: runId } : undefined,
    keepFullResponse: true
  })
}

/** AI 稽核报告（带数据窗口标注；失败自动降级模板） */
export const getReconcileReport = (runId?: string, force = false): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/reconcile/report`,
    params: { ...(runId ? { run_id: runId } : {}), force },
    keepFullResponse: true,
    timeout: 180000
  })
}

/** 稽核差异列表 */
export const getReconciliations = (params: {
  run_id?: string
  all_runs?: boolean
  reconciliation_type?: ReconciliationType
  status?: ReconciliationStatus
  page?: number
  page_size?: number
}): Promise<any> => {
  return httpClient.get({
    url: `${API_PREFIX}/reconciliations`,
    params,
    keepFullResponse: true
  })
}

/** 处理差异。重复处理后端返回 409 */
export const resolveReconciliation = (
  id: string,
  status: 'confirmed' | 'ignored' | 'resolved',
  note?: string
): Promise<any> => {
  return httpClient.put({
    url: `${API_PREFIX}/reconciliations/${id}/resolve`,
    data: { status, note },
    keepFullResponse: true
  })
}

/** 数据健康总览：源健康 / 同步死信 / 稽核差异 三层聚合 */
export const getDataHealth = (deadLetterLimit = 5): Promise<any> => {
  return httpClient.get({
    url: '/api/v1/data-health',
    params: { dead_letter_limit: deadLetterLimit },
    keepFullResponse: true
  })
}

// ==================== P3/F2.2 AI 安全报告 ====================

export type ReportType = 'weekly' | 'monthly' | 'on_demand' | 'incident_driven'

export interface ReportDataCoverage {
  window_start: string
  window_end: string
  window_hours: number
  opensearch_available: boolean
  opensearch_error?: string | null
  source_health: Array<{
    source_key: string
    source_type?: string
    last_success_at?: string | null
    overdue: boolean
    reason?: string | null
  }>
  gaps: Array<{
    scope: string
    reason: string
    impact: string
  }>
  data_degraded: boolean
  generated_at: string
}

export interface SecurityReport {
  id: string
  report_type: ReportType
  period_start: string
  period_end: string
  title: string
  summary: string
  content: {
    overview: string
    trends: string
    risks: string
    data_notes: string
  }
  risk_highlights: string
  recommendations: string
  data_coverage: ReportDataCoverage
  prompt_version?: string | null
  triggered_by?: string | null
  trigger_meta?: Record<string, any> | null
  created_at: string
}

/** 触发报告生成（weekly/monthly/on_demand） */
export const generateReport = (body: {
  report_type: ReportType
  period_start?: string
  period_end?: string
  force_glm?: boolean
}): Promise<any> => {
  return httpClient.post({
    url: '/api/v1/reports/generate',
    data: body,
    keepFullResponse: true,
    timeout: 180000
  })
}

/** 报告列表 */
export const listReports = (params: {
  report_type?: ReportType
  page?: number
  page_size?: number
}): Promise<any> => {
  return httpClient.get({
    url: '/api/v1/reports',
    params,
    keepFullResponse: true
  })
}

/** 最新一份报告 */
export const getLatestReport = (reportType: ReportType): Promise<any> => {
  return httpClient.get({
    url: '/api/v1/reports/latest',
    params: { report_type: reportType },
    keepFullResponse: true
  })
}

/** 报告详情 */
export const getReport = (id: string): Promise<any> => {
  return httpClient.get({
    url: `/api/v1/reports/${id}`,
    keepFullResponse: true
  })
}

/** 事件驱动触发检查 */
export const checkIncidentTrigger = (): Promise<any> => {
  return httpClient.post({
    url: '/api/v1/reports/check-incident-trigger',
    keepFullResponse: true,
    timeout: 60000
  })
}

// ─────────────────────────────────────────────
// P3 / F3.1 变更影响分析
// ─────────────────────────────────────────────

export interface ImpactAnalysisPayload {
  change_description: string
  change_window_hours?: number
}

/** 智能变更影响分析（GLM 调用可能 20-60s，timeout 放宽到 180s） */
export const analyzeChangeImpact = (payload: ImpactAnalysisPayload): Promise<any> => {
  return httpClient.post({
    url: '/api/v1/assets/impact-analysis',
    data: payload,
    keepFullResponse: true,
    timeout: 180000
  })
}
