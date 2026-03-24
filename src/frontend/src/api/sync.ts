import apiClient from './client'

export interface SyncTask {
  id: string
  sync_type: string
  status: string
  total_count: number
  created_count: number
  updated_count: number
  failed_count: number
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at: string
  progress?: string
}

export interface ManualSyncResponse {
  task_id: string
  status: string
  message: string
}

export interface SyncTaskList {
  total: number
  items: SyncTask[]
}

export const syncApi = {
  manualSync: () =>
    apiClient.post<ManualSyncResponse>('/assets/sync/manual', {}),

  getTask: (taskId: string) =>
    apiClient.get<SyncTask>(`/sync/tasks/${taskId}`),

  listTasks: (params?: { skip?: number; limit?: number; status?: string }) =>
    apiClient.get<SyncTaskList>('/sync/tasks', params)
}
