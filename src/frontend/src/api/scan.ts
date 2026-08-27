/**
 * 资产扫描控制面 API
 *
 * 后端路由前缀 /api/v1/scan，定义见：
 *   src/backend/app/api/scan_tasks.py        任务 + 发现 + 纳管
 *   src/backend/app/api/scan_human_agents.py 扫描器注册/管理
 *
 * 响应统一走 axios 拦截器解 envelope（body.code/msg/data），
 * 这里各方法直接返回 data 部分。
 */
import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const API_PREFIX = '/api/v1/scan'

// ===================== 类型定义 =====================

export type ScanMode = 'internal' | 'public' | 'ports'
export type ScanStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
export type FindingStatus = 'new' | 'known' | 'adopted' | 'ignored'
export type ScannerStatus = 'online' | 'offline' | 'unknown' | 'disabled'
export type Exposure = 'internal' | 'public'

export interface ScannerAgent {
  scanner_id: string
  name: string
  ip?: string | null
  status: ScannerStatus
  capabilities: string[]
  reachable_subnets?: string[]
  enabled: boolean
  last_heartbeat?: string | null
  version?: string | null
  created_by?: string | null
  created_at?: string
  /** 仅注册接口返回一次明文 Key */
  api_key?: string
  api_key_hash_prefix?: string
}

export interface AffectedPort {
  id: string
  ip: string
  port: number
  protocol: string
  action: 'created' | 'updated'
  service?: string | null
  version?: string | null
}

export interface AffectedFinding {
  id: number
  ip: string
  mac?: string | null
  os_guess?: string | null
  exposure?: string | null
  finding_status?: string | null
  matched_asset_id?: string | null
  action: 'created' | 'updated'
}

export interface ScanTask {
  task_uuid: string
  mode: ScanMode
  scope?: string | null
  status: ScanStatus
  triggered_by?: string | null
  assign_mode?: string | null
  target_scanner_id?: string | null
  scanner_id?: string | null
  run_reason?: string | null
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  items_scanned?: number | null
  items_created?: number | null
  items_updated?: number | null
  items_failed?: number | null
  error_message?: string | null
  parent_task_id?: string | null
  /** F-S3：本次扫描动了哪些端口（port 任务专用）。老任务 / 未执行完为空数组 */
  affected_ports?: AffectedPort[]
  /** F-S3：本次扫描动了哪些发现（discovery 任务专用）。老任务 / 未执行完为空数组 */
  affected_findings?: AffectedFinding[]
}

export interface ScanFinding {
  id: number
  scan_task_uuid: string
  exposure: Exposure
  asset_ip: string
  mac_address?: string | null
  os_guess?: string | null
  discovery_source?: string | null
  scanner_id?: string | null
  finding_status: FindingStatus
  matched_asset_id?: string | null
  first_seen?: string
  last_seen?: string
}

export interface RunScanPayload {
  mode: ScanMode
  /** 逗号分隔的目标，如 "192.168.0.0/24" 或 "1.2.3.4,5.6.7.8"；不传则按 mode 自动选目标 */
  targets?: string
  assign_mode?: 'auto' | 'pinned'
  target_scanner_id?: string | null
  nmap_args?: string | null
  notify?: boolean
}

export interface AdoptPayload {
  asset_name?: string
  criticality?: string
  owner?: string
  business_unit?: string
}

export interface RegisterAgentPayload {
  name: string
  ip?: string
  capabilities?: string[]
  reachable_subnets?: string[]
}

export interface Paginated<T> {
  total: number
  items: T[]
}

// ===================== 扫描任务 =====================

/** 触发一次扫描（建 pending 任务，由扫描器轮询认领） */
export const runScan = (data: RunScanPayload): Promise<{ task_uuid: string; status: string }> => {
  return httpClient.post({ url: `${API_PREFIX}/run`, data })
}

/** 任务列表（分页 + 过滤） */
export const getScanTasks = (params: {
  status?: ScanStatus
  mode?: ScanMode
  skip?: number
  limit?: number
}): Promise<Paginated<ScanTask>> => {
  return httpClient.get({ url: `${API_PREFIX}/tasks`, params })
}

/** 任务详情 */
export const getScanTask = (taskUuid: string): Promise<ScanTask> => {
  return httpClient.get({ url: `${API_PREFIX}/tasks/${taskUuid}` })
}

/** 取消任务 */
export const cancelScanTask = (taskUuid: string): Promise<{ cancelled: boolean }> => {
  return httpClient.post({ url: `${API_PREFIX}/tasks/${taskUuid}/cancel` })
}

// ===================== 发现清单 =====================

/** 发现列表（分页 + 过滤） */
export const getScanFindings = (params: {
  status?: FindingStatus
  exposure?: Exposure
  asset_ip?: string
  skip?: number
  limit?: number
}): Promise<Paginated<ScanFinding>> => {
  return httpClient.get({ url: `${API_PREFIX}/findings`, params })
}

/** 一键纳管：把发现转成正式资产 */
export const adoptFinding = (
  findingId: number,
  data?: AdoptPayload
): Promise<{ finding_id: number; asset_id: string; finding_status: string }> => {
  return httpClient.post({ url: `${API_PREFIX}/findings/${findingId}/adopt`, data: data || {} })
}

/** 忽略发现 */
export const ignoreFinding = (
  findingId: number
): Promise<{ finding_id: number; finding_status: string }> => {
  return httpClient.post({ url: `${API_PREFIX}/findings/${findingId}/ignore` })
}

// ===================== 扫描器管理（admin） =====================

/** 扫描器列表 */
export const getScannerAgents = (): Promise<{ items: ScannerAgent[]; total: number }> => {
  return httpClient.get({ url: `${API_PREFIX}/agents` })
}

/** 注册扫描器（返回明文 Key，仅一次） */
export const registerScannerAgent = (
  data: RegisterAgentPayload
): Promise<ScannerAgent> => {
  return httpClient.post({ url: `${API_PREFIX}/agents`, data })
}

/** 编辑扫描器 / 轮换 Key（body 可含 name/ip/capabilities/reachable_subnets/enabled/rotate_key） */
export const updateScannerAgent = (
  scannerId: string,
  data: Partial<RegisterAgentPayload> & { enabled?: boolean; rotate_key?: boolean }
): Promise<ScannerAgent> => {
  return httpClient.patch({ url: `${API_PREFIX}/agents/${scannerId}`, data })
}

/** 注销扫描器 */
export const deleteScannerAgent = (
  scannerId: string
): Promise<{ scanner_id: string; disabled: boolean }> => {
  return httpClient.del({ url: `${API_PREFIX}/agents/${scannerId}` })
}
