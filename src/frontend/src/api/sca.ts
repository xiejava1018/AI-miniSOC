/**
 * SCA基线核查 API（DEPRECATED，T8 / 决策3，2026-08-15）
 *
 * 后端 sca.py 路由不注册，wazuh_sca_sync_v2 不再运行：SCA 数据统一由
 * Vulnerability(type=sca) 单表示承载（wazuh_sca_sync + /vulnerabilities/* 接口）。
 * 本文件保留仅为回滚便利（§6），勿新增引用；脆弱性页面已全部改用
 * @/api/vulnerabilities（含 getSCAStats / getRecentDiscoveries('sca')）。
 * 原裸路径已补 /api/v1 前缀（T13），万一临时启用不再 404。
 */

import request from '@/utils/http'

const API_PREFIX = '/api/v1/sca'

export interface ScaStats {
  total_checks: number
  total_results: number
  by_result: {
    passed: number
    failed: number
    'not applicable': number
  }
  by_asset: Record<string, number>
}

export interface ScaCheck {
  id: string
  check_id: number
  policy_id: string
  title: string
  description: string
  rationale: string
  remediation: string
}

export interface AssetScaResult {
  id: string
  asset_id: string
  asset_name: string
  sca_check_id: string
  check_id: number
  policy_id: string
  title: string
  result: 'passed' | 'failed' | 'not applicable'
  reason: string
  status: string
  last_scan_time: string
}

export interface ScaChecksResponse {
  total: number
  items: ScaCheck[]
}

export interface AssetScaResultsResponse {
  total: number
  items: AssetScaResult[]
}

/**
 * 获取SCA统计数据
 */
export function getSCAStatistics(): Promise<ScaStats> {
  return request.get<ScaStats>({ url: `${API_PREFIX}/stats/overview` })
}

/**
 * 同步所有SCA数据
 */
export function syncAllSCAChecks(): Promise<{
  total_agents: number
  processed_agents: number
  new_checks: number
  new_results: number
  updated_results: number
  errors: number
}> {
  return request.post<{
    total_agents: number
    processed_agents: number
    new_checks: number
    new_results: number
    updated_results: number
    errors: number
  }>({ url: `${API_PREFIX}/sync/all` })
}

/**
 * 同步指定agent的SCA数据
 */
export function syncAgentSCAChecks(agentId: string): Promise<{
  new_checks: number
  new_results: number
  updated_results: number
}> {
  return request.post<{
    new_checks: number
    new_results: number
    updated_results: number
  }>({ url: `${API_PREFIX}/sync/agent/${agentId}` })
}

/**
 * 获取SCA检查项列表
 */
export function getSCAChecks(params?: {
  skip?: number
  limit?: number
  policy_id?: string
}): Promise<ScaChecksResponse> {
  return request.get<ScaChecksResponse>({ url: `${API_PREFIX}/checks`, params })
}

/**
 * 获取资产SCA检查结果列表
 */
export function getAssetSCAResults(params?: {
  skip?: number
  limit?: number
  asset_id?: string
  result?: 'passed' | 'failed' | 'not applicable'
}): Promise<AssetScaResultsResponse> {
  return request.get<AssetScaResultsResponse>({ url: `${API_PREFIX}/results`, params })
}
