/**
 * 后台任务可观测性 API（v0.4.2 Phase 1.7）
 */

import request from '@/utils/http'
import type { HttpClient } from '@/utils/http'

const httpClient = request as HttpClient

const PREFIX = '/api/v1/tasks'

// ---------------------------------------------------------------------------
// 类型

export type TaskRunStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'timeout'
  | 'skipped'
  | 'zombie'
  | 'unknown'

export type TaskType = 'scheduled' | 'async' | 'thread' | 'watchdog'

export interface TaskRegistry {
  task_key: string
  task_name: string
  task_type: TaskType
  owner_module: string | null
  schedule_expr: string | null
  expected_interval_s: number | null
  timeout_s: number
  enabled: boolean
  current_run_id: string | null
  lock_owner: string | null
  last_run_at: string | null
  last_status: TaskRunStatus | null
  last_error: string | null
  last_duration_ms: number | null
  last_stats: Record<string, any> | null
  consecutive_failures: number
  total_runs: number
  /** Phase 2.4：当前运行进度（仅当 status=running 时存在） */
  current_run?: TaskRun | null
}

export interface TaskRun {
  id: string
  task_key: string
  trigger: 'scheduled' | 'manual' | 'api' | 'replay' | 'startup' | 'watchdog'
  started_at: string
  finished_at: string | null
  status: TaskRunStatus
  duration_ms: number | null
  error_text: string | null
  stats_json: Record<string, any> | null
  total: number | null
  processed: number | null
  percent: number | null
  last_progress_at: string | null
  correlation_id: string | null
  host: string | null
  triggered_by_user: string | null
}

export interface TaskSummary {
  total_tasks: number
  enabled_tasks: number
  disabled_tasks: number
  running_runs: number
  zombie_runs: number
  consecutive_failed_tasks: number
  queue_size: number
}

export interface ListResp<T> {
  total: number
  page: number
  page_size: number
  records: T[]
}

export interface TriggerResponse {
  run_id: string
  status: string
}

export interface CancelResponse {
  cancelled: boolean
  run_id: string
}

// ---------------------------------------------------------------------------
// API

export const fetchTaskSummary = () => {
  return httpClient.get<Http.BaseResponse<TaskSummary>>({
    url: `${PREFIX}/summary`,
    keepFullResponse: true
  })
}

export const fetchTaskList = (params?: { page?: number; page_size?: number }) => {
  return httpClient.get<Http.BaseResponse<ListResp<TaskRegistry>>>({
    url: `${PREFIX}`,
    params: { page: 1, page_size: 50, ...params },
    keepFullResponse: true
  })
}

export const fetchTaskDetail = (taskKey: string) => {
  return httpClient.get<Http.BaseResponse<TaskRegistry>>({
    url: `${PREFIX}/${taskKey}`,
    keepFullResponse: true
  })
}

export const fetchTaskRuns = (
  taskKey: string,
  params?: { page?: number; page_size?: number; status_filter?: TaskRunStatus }
) => {
  return httpClient.get<Http.BaseResponse<ListResp<TaskRun>>>({
    url: `${PREFIX}/${taskKey}/runs`,
    params: { page: 1, page_size: 20, ...params },
    keepFullResponse: true
  })
}

export const fetchRunDetail = (runId: string) => {
  return httpClient.get<Http.BaseResponse<TaskRun>>({
    url: `${PREFIX}/runs/${runId}`,
    keepFullResponse: true
  })
}

export const triggerTask = (taskKey: string, reason: string) => {
  return httpClient.post<Http.BaseResponse<TriggerResponse>>({
    url: `${PREFIX}/${taskKey}/trigger`,
    data: { reason }
  })
}

export const cancelTaskRun = (taskKey: string, runId: string) => {
  return httpClient.post<Http.BaseResponse<CancelResponse>>({
    url: `${PREFIX}/${taskKey}/cancel/${runId}`
  })
}

export const toggleTask = (
  taskKey: string,
  payload: { enabled?: boolean; timeout_s?: number; reason: string }
) => {
  return httpClient.patch<Http.BaseResponse<TaskRegistry>>({
    url: `${PREFIX}/${taskKey}`,
    data: payload
  })
}
