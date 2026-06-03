/**
 * 脆弱性管理 API
 */

import request from '@/utils/http'

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

/**
 * 获取漏洞统计概览（仅CVE漏洞）
 */
export function getVulnerabilityStats(): Promise<VulnerabilityStats> {
  return request.get<VulnerabilityStats>({ url: '/vulnerabilities/stats/overview' })
}

/**
 * 获取配置检查统计概览（仅SCA配置检查）
 */
export function getSCAStats(): Promise<VulnerabilityStats> {
  return request.get<VulnerabilityStats>({ url: '/vulnerabilities/stats/sca-overview' })
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
  }>({ url: '/vulnerabilities/stats/trend', params: { days } })
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
}[]>({ url: '/vulnerabilities/stats/top-assets', params: { limit } })
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
  }[]>({ url: '/vulnerabilities/stats/recent', params: { vuln_type: type, limit } })
}

/**
 * 获取AI优先修复建议
 */
export function getAISuggestions(limit = 5, minSeverity?: string): Promise<AIVulnerabilitySuggestion[]> {
  const params: Record<string, any> = { limit }
  if (minSeverity) {
    params.min_severity = minSeverity
  }
  return request.get<AIVulnerabilitySuggestion[]>({ url: '/vulnerabilities/stats/ai-suggestions', params })
}

/**
 * 获取漏洞列表
 */
export function getVulnerabilities(params: VulnerabilityListParams): Promise<VulnerabilityListResponse> {
  return request.get<VulnerabilityListResponse>({ url: '/vulnerabilities/vulnerabilities', params })
}

/**
 * 获取漏洞详情
 */
export function getVulnerability(id: string): Promise<Vulnerability> {
  return request.get<Vulnerability>({ url: `/vulnerabilities/vulnerabilities/${id}` })
}

/**
 * 获取资产-漏洞关联列表
 */
export function getAssetVulnerabilities(params: {
  skip?: number
  limit?: number
  asset_id?: string
  severity?: string
  status?: string
  scanner?: string
}): Promise<{ items: AssetVulnerability[]; total: number; skip: number; limit: number }> {
  return request.get<{ items: AssetVulnerability[]; total: number; skip: number; limit: number }>({
    url: '/vulnerabilities/asset-vulnerabilities',
    params
  })
}

/**
 * 更新漏洞状态
 */
export function updateVulnerabilityStatus(
  id: string,
  status: string,
  notes?: string
): Promise<{ message: string; status: string }> {
  return request.put<{ message: string; status: string }>({
    url: `/vulnerabilities/asset-vulnerabilities/${id}/status`,
    data: { status, notes }
  })
}

/**
 * 同步Wazuh SCAP数据
 */
export function syncWazuhVulnerabilities(limit = 1000, useMock = false): Promise<{
  message: string
  mode: string
  stats: {
    total_agents: number
    processed_agents: number
    new_vulnerabilities: number
    new_associations: number
    updated_associations: number
    errors: number
  }
}> {
  return request.post<{
    message: string
    mode: string
    stats: {
      total_agents: number
      processed_agents: number
      new_vulnerabilities: number
      new_associations: number
      updated_associations: number
      errors: number
    }
  }>({ url: '/vulnerabilities/sync/wazuh', data: { limit, use_mock: useMock } })
}

/**
 * 同步Wazuh SCA配置检查数据
 */
export function syncWazuhSCAChecks(limit = 1000): Promise<{
  message: string
  type: string
  stats: {
    total_agents: number
    processed_agents: number
    new_vulnerabilities: number
    new_associations: number
    updated_associations: number
    errors: number
  }
}> {
  return request.post<{
    message: string
    type: string
    stats: {
      total_agents: number
      processed_agents: number
      new_vulnerabilities: number
      new_associations: number
      updated_associations: number
      errors: number
    }
  }>({ url: '/vulnerabilities/sync/wazuh/sca', data: { limit } })
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
  }>({ url: '/vulnerabilities/sync/wazuh/status' })
}
