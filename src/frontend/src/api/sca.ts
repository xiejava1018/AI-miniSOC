/**
 * SCA基线核查 API
 */

import request from '@/utils/http'

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
  return request.get<ScaStats>({ url: '/sca/stats/overview' })
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
  }>({ url: '/sca/sync/all' })
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
  }>({ url: `/sca/sync/agent/${agentId}` })
}

/**
 * 获取SCA检查项列表
 */
export function getSCAChecks(params?: {
  skip?: number
  limit?: number
  policy_id?: string
}): Promise<ScaChecksResponse> {
  return request.get<ScaChecksResponse>({ url: '/sca/checks', params })
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
  return request.get<AssetScaResultsResponse>({ url: '/sca/results', params })
}
