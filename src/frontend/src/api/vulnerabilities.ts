/**
 * 脆弱性管理 API
 *
 * T13（2026-08-15 评审修订 §14.1-P2/§14.3）：
 * - 补 `/api/v1` 前缀（原裸 `/vulnerabilities/...` 过不了 vite dev proxy，全 404）；
 * - 状态更新 PUT → PATCH（对齐后端 @router.patch）；
 * - 同步参数 body → Query params（对齐后端 Query 收参）。
 */

import request from '@/utils/http'

const API_PREFIX = '/api/v1/vulnerabilities'

export interface VulnerabilityStats {
  critical: number
  high: number
  medium: number
  low: number
  total: number
}

export interface AIVulnerabilitySuggestion {
  rank: number
  vulnerability_id: string
  cve_id: string
  title: string
  cvss_score: number
  severity: string
  affected_asset_count: number
  risk_score: number
  has_exploit: boolean
  risk_reason: string
  fix_suggestion: string
}

export interface Vulnerability {
  id: string
  type: 'sca' | 'scap'
  cve_id: string
  title: string
  description: string
  cvss_score: number
  cvss_vector: string
  severity: string
  affected_packages: Record<string, any> | null
  fix_suggestion: string | null
  references: string[] | null
  published_date: string | null
  has_exploit: boolean
  discovered_at: string
  updated_at: string
}

export interface AssetVulnerability {
  id: string
  asset_id: string
  asset_name: string
  asset_ip: string
  vulnerability_id: string
  cve_id: string
  title: string
  severity: string
  cvss_score: number
  status: string
  scanner: string
  detected_at: string
  fixed_at: string | null
  due_date?: string | null
  sla_status?: 'normal' | 'warning' | 'overdue' | null
}

export interface VulnerabilityListResponse {
  items: Vulnerability[]
  total: number
  skip: number
  limit: number
}

export interface VulnerabilityListParams {
  skip?: number
  limit?: number
  type?: 'sca' | 'scap'
  severity?: string
  scanner?: string
  status?: string
  search?: string
}

export interface ScoreBreakdown {
  vulnerability_id: string
  total_score: number
  weights: { cvss: number; criticality: number; exposure: number; exploit: number }
  asset_scores: {
    asset_name: string
    asset_ip: string
    criticality: string
    exposure_level: string
    score: number
    score_breakdown: {
      cvss_contribution: number
      criticality_contribution: number
      exposure_contribution: number
      exploit_bonus: number
    }
  }[]
}

export interface SyncStats {
  total_agents: number
  processed_agents: number
  new_vulnerabilities: number
  new_associations: number
  revived_associations?: number
  updated_associations: number
  skipped_no_asset?: number
  errors: number
  kev_enriched?: number
}

/**
 * 获取漏洞统计概览（仅CVE漏洞）
 */
export function getVulnerabilityStats(): Promise<VulnerabilityStats> {
  return request.get<VulnerabilityStats>({ url: `${API_PREFIX}/stats/overview` })
}

/**
 * 获取配置检查统计概览（仅SCA配置检查）
 *
 * §14.2 选型 (b)：概览页 SCA 卡数据源从 /sca/stats/overview（sca.py，未注册）
 * 切换到本接口（Vulnerability(type=sca) 口径，仅严重度分布）。
 */
export function getSCAStats(): Promise<VulnerabilityStats> {
  return request.get<VulnerabilityStats>({ url: `${API_PREFIX}/stats/sca-overview` })
}

/**
 * 获取脆弱性趋势数据
 */
export function getVulnerabilityTrend(days: number = 7): Promise<{
  cve: { current: number; change: number; change_percent: number }
  sca: { current: number; change: number; change_percent: number }
}> {
  return request.get<{
    cve: { current: number; change: number; change_percent: number }
    sca: { current: number; change: number; change_percent: number }
  }>({ url: `${API_PREFIX}/stats/trend`, params: { days } })
}

/**
 * 获取高风险资产排行
 */
export function getTopRiskyAssets(limit: number = 5): Promise<{
  rank: number
  asset_id: string
  asset_name: string
  asset_ip: string
  critical_count: number
  high_count: number
  medium_count: number
}[]> {
  return request.get<{
    rank: number
    asset_id: string
    asset_name: string
    asset_ip: string
    critical_count: number
    high_count: number
    medium_count: number
  }[]>({ url: `${API_PREFIX}/stats/top-assets`, params: { limit } })
}

/**
 * 获取最近发现的脆弱性
 */
export function getRecentDiscoveries(type: 'cve' | 'sca', limit: number = 5): Promise<{
  id: string
  cve_id: string
  title: string
  severity: string
  asset_name: string
  asset_ip: string
  discovered_at: string
}[]> {
  return request.get<{
    id: string
    cve_id: string
    title: string
    severity: string
    asset_name: string
    asset_ip: string
    discovered_at: string
  }[]>({ url: `${API_PREFIX}/stats/recent`, params: { vuln_type: type, limit } })
}

/**
 * 获取AI优先修复建议
 */
export function getAISuggestions(limit = 5, minSeverity?: string): Promise<AIVulnerabilitySuggestion[]> {
  const params: Record<string, any> = { limit }
  if (minSeverity) {
    params.min_severity = minSeverity
  }
  return request.get<AIVulnerabilitySuggestion[]>({ url: `${API_PREFIX}/stats/ai-suggestions`, params })
}

/**
 * 获取在野利用（CISA KEV）统计（T6）
 */
export function getExploitStats(): Promise<{
  kev_catalog_total: number
  kev_ransomware_related: number
  vulnerabilities_with_exploit: number
  open_associations_with_exploit: number
}> {
  return request.get<{
    kev_catalog_total: number
    kev_ransomware_related: number
    vulnerabilities_with_exploit: number
    open_associations_with_exploit: number
  }>({ url: `${API_PREFIX}/stats/exploit` })
}

/**
 * 获取漏洞列表
 */
export function getVulnerabilities(params: VulnerabilityListParams): Promise<VulnerabilityListResponse> {
  return request.get<VulnerabilityListResponse>({ url: `${API_PREFIX}/vulnerabilities`, params })
}

/**
 * 获取漏洞详情
 */
export function getVulnerability(id: string): Promise<Vulnerability> {
  return request.get<Vulnerability>({ url: `${API_PREFIX}/vulnerabilities/${id}` })
}

/**
 * 获取漏洞 AI 评分分解
 */
export function getScoreBreakdown(id: string): Promise<ScoreBreakdown> {
  return request.get<ScoreBreakdown>({ url: `${API_PREFIX}/vulnerabilities/${id}/score-breakdown` })
}

/**
 * 获取资产-漏洞关联列表
 */
export function getAssetVulnerabilities(params: {
  skip?: number
  limit?: number
  asset_id?: string
  vulnerability_id?: string
  severity?: string
  status?: string
  scanner?: string
}): Promise<{ items: AssetVulnerability[]; total: number; skip: number; limit: number }> {
  return request.get<{ items: AssetVulnerability[]; total: number; skip: number; limit: number }>({
    url: `${API_PREFIX}/asset-vulnerabilities`,
    params
  })
}

/**
 * 更新漏洞状态（C1：PATCH + JSON body）
 */
export function updateVulnerabilityStatus(
  id: string,
  status: string,
  notes?: string
): Promise<{ message: string; status: string }> {
  return request.patch<{ message: string; status: string }>({
    url: `${API_PREFIX}/asset-vulnerabilities/${id}/status`,
    data: { status, notes }
  })
}

/**
 * 漏洞→事件：一键生成安全事件（T11 / Phase 4.1）
 */
export function createIncidentFromVulnerability(
  assetVulnerabilityId: string
): Promise<{
  message: string
  incident: {
    id: string
    title: string
    severity: string
    status: string
    created_by: string
  }
}> {
  return request.post<{
    message: string
    incident: {
      id: string
      title: string
      severity: string
      status: string
      created_by: string
    }
  }>({ url: `${API_PREFIX}/asset-vulnerabilities/${assetVulnerabilityId}/create-incident` })
}

/**
 * 同步 SCAP（CVE）数据（T5：OpenSearch 源；C2：参数走 Query）
 */
export function syncWazuhVulnerabilities(limit = 1000, useMock = false): Promise<{
  message: string
  mode: string
  source?: string
  stats: SyncStats
}> {
  return request.post<{
    message: string
    mode: string
    source?: string
    stats: SyncStats
  }>({ url: `${API_PREFIX}/sync/wazuh`, params: { limit, use_mock: useMock } })
}

/**
 * 同步 SCA 配置检查数据（C2：参数走 Query）
 */
export function syncWazuhSCAChecks(limit = 1000): Promise<{
  message: string
  type: string
  stats: SyncStats
}> {
  return request.post<{
    message: string
    type: string
    stats: SyncStats
  }>({ url: `${API_PREFIX}/sync/wazuh/sca`, params: { limit } })
}

/**
 * 手动同步 CISA KEV 目录 + 存量富化（T6）
 */
export function syncCisaKev(): Promise<{ message: string; result: { total: number; upserted: number; source: string; enriched: number } }> {
  return request.post<{ message: string; result: { total: number; upserted: number; source: string; enriched: number } }>({
    url: `${API_PREFIX}/sync/kev`
  })
}

/**
 * 获取同步状态
 */
export function getSyncStatus(): Promise<{
  total_vulnerabilities: number
  total_associations: number
  severity_distribution: Record<string, number>
  last_sync: string | null
}> {
  return request.get<{
    total_vulnerabilities: number
    total_associations: number
    severity_distribution: Record<string, number>
    last_sync: string | null
  }>({ url: `${API_PREFIX}/sync/wazuh/status` })
}
