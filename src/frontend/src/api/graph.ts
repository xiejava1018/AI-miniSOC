/**
 * 资产知识图谱 API 客户端
 *
 * 后端端点：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.5
 * 前缀：/api/v1/graph
 */

import request, { type HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/graph'

// ============ 类型定义（对齐后端 §6.5.2） ============

export type NodeCategory =
  | 'asset'
  | 'port'
  | 'vulnerability'
  | 'account'
  | 'ip'
  | 'business_system'
  | 'department'
  | 'person'
  | 'segment'
  | 'alert_group'
  | 'unknown'

export interface GraphNode {
  id: string
  label: string
  category: NodeCategory
  rawProps: Record<string, any>
}

export interface GraphLink {
  id: string
  source: string
  target: string
  relType: string
  confidence: number
  weight: number
  direction: 'directed' | 'undirected'
  lineStyle: { color: string; width: number; type: 'solid' | 'dashed' }
  evidence: Record<string, any>
  sourceLabel: string
  updated: string | null
  firstSeen?: string | null
  lastSeen?: string | null
  sources?: string[]
}

export interface GraphCenter {
  id: string
  label: string
  category: NodeCategory
  rawProps: Record<string, any>
}

export interface GraphStats_Stats {
  nodeCount: number
  edgeCount: number
  depth?: number
  byRelType?: Record<string, number>
  byConfidence?: Record<string, number>
  empty?: boolean
}

export interface GraphNeighborsResponse {
  center: GraphCenter
  nodes: GraphNode[]
  links: GraphLink[]
  truncated: boolean
  stats: GraphStats_Stats
  message?: string
}

export interface GraphPathStep {
  relType: string
  confidence: number
  srcKey: string
  dstKey: string
}

export interface GraphPath {
  nodeKeys: string[]
  edges: GraphPathStep[]
  cost: number
  minConfidence: number
  depth: number
}

export interface GraphPathsResponse {
  paths: GraphPath[]
  stats: { pathCount: number; minCost: number | null; maxDepthUsed: number }
  message?: string
}

export interface GraphScope {
  nodes: GraphNode[]
  links: GraphLink[]
  byBusinessSystem: Record<string, number>
  byOwner: Record<string, number>
  byCriticality: Record<string, number>
}

export interface GraphScopeWarning {
  code: string
  message: string
  count?: number
}

export interface GraphImpactScopeResponse {
  scope: GraphScope
  warnings: GraphScopeWarning[]
  degraded: boolean
  score: number
  message: string
}

export interface GraphChokepoint {
  vulnKey: string
  cveId: string
  cvss: number
  severity: string
  reachableCriticalCount: number
  reachableAssets: string[]
}

export interface GraphChokepointsResponse {
  chokepoints: GraphChokepoint[]
  method: string
  params: Record<string, any>
  message?: string
}

export interface GraphCoverage {
  assetsTotal: number
  assetsWithAnyEdge: number
  assetsWithD1D2Edges: number
  criticalAssetsWithOwner: number
  criticalAssetsTotal: number
  assetsWithBusinessSystem: number
}

export interface GraphStatsResponse {
  nodes: {
    total: number
    byType: Record<string, number>
  }
  edges: {
    total: number
    byRelType: Record<string, number>
    byConfidence: Record<string, number>
    activeAfterExpiry: number
  }
  coverage: GraphCoverage
  health: { queried_at: string }
}

// ============ API 调用 ============

/** GET /graph/assets/{asset_id}/neighbors — 资产 N 跳邻居子图 */
export const getAssetNeighbors = (
  assetId: string,
  params?: {
    depth?: number
    minConf?: number
    relTypes?: string
    includeInferred?: boolean
    limit?: number
  }
): Promise<Http.BaseResponse<GraphNeighborsResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/assets/${assetId}/neighbors`,
    params: params || {},
    keepFullResponse: true
  })
}

/** GET /graph/paths — 两节点间最短路径 */
export const getGraphPaths = (params: {
  src: string
  dst: string
  maxDepth?: number
  minConf?: number
  maxPaths?: number
}): Promise<Http.BaseResponse<GraphPathsResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/paths`,
    params,
    keepFullResponse: true
  })
}

/** POST /graph/impact-scope — 影响面分析 */
export const postImpactScope = (body: {
  targetKeys: string[]
  maxDepth?: number
  includeInferred?: boolean
  minConfidence?: number
}): Promise<Http.BaseResponse<GraphImpactScopeResponse>> => {
  return httpClient.post({
    url: `${API_PREFIX}/impact-scope`,
    data: body,
    keepFullResponse: true
  })
}

/** GET /graph/vuln-chokepoints — 修复阻塞点 */
export const getVulnChokepoints = (params?: {
  limit?: number
  maxDepth?: number
  minConf?: number
  criticality?: string
}): Promise<Http.BaseResponse<GraphChokepointsResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/vuln-chokepoints`,
    params: params || {},
    keepFullResponse: true
  })
}

/** GET /graph/stats — 全图统计 */
export const getGraphStats = (): Promise<Http.BaseResponse<GraphStatsResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/stats`,
    keepFullResponse: true
  })
}

/** POST /graph/rebuild — 触发重建 */
export const postGraphRebuild = (
  builder: 'all' | 'asset_port_vuln' | 'identity' | 'topology' | 'alert_group' | 'manual' = 'all'
): Promise<Http.BaseResponse<{ builder: string; stats: Record<string, any> }>> => {
  return httpClient.post({
    url: `${API_PREFIX}/rebuild`,
    data: { builder },
    keepFullResponse: true
  })
}

// ============ OH-3.6 图谱 P95 性能看板 ============

export type GraphQueryType = 'neighbors' | 'paths' | 'impact_scope' | 'vuln_chokepoints'

export interface GraphPerfSnapshot {
  window_size: number
  samples: Record<GraphQueryType, number>
  p50_ms: Record<GraphQueryType, number>
  p95_ms: Record<GraphQueryType, number>
  max_ms: Record<GraphQueryType, number>
  avg_ms: Record<GraphQueryType, number>
  slow_count: Record<GraphQueryType, number>
  slow_threshold_ms: number
}

export interface GraphSlowQuery {
  latency_ms: number
  query_type: GraphQueryType
  asset_key: string | null
  ts: number
}

export interface GraphPerfResponse {
  snapshot: GraphPerfSnapshot
  recent_slow: GraphSlowQuery[]
}

/** GET /graph/perf — 图谱 4 类查询 P95 性能看板 */
export const getGraphPerf = (
  recentSlowLimit = 10
): Promise<Http.BaseResponse<GraphPerfResponse>> => {
  return httpClient.get({
    url: `${API_PREFIX}/perf`,
    params: { recent_slow_limit: recentSlowLimit },
    keepFullResponse: true
  })
}

/** POST /graph/perf/reset — 清空 perf 采样（admin） */
export const postGraphPerfReset = (): Promise<Http.BaseResponse<{ reset: boolean }>> => {
  return httpClient.post({
    url: `${API_PREFIX}/perf/reset`,
    keepFullResponse: true
  })
}
