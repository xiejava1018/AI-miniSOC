// src/frontend/src/types/audit_log.ts
export interface AuditLog {
  id: number
  user_id?: number
  username: string
  action: string
  resource_type?: string
  resource_id?: number
  resource_name?: string
  old_values?: Record<string, any>
  new_values?: Record<string, any>
  ip_address?: string
  user_agent?: string
  session_id?: number
  request_id?: string
  status: string
  error_message?: string
  created_at: string
}

export interface AuditLogQuery {
  page?: number
  page_size?: number
  user_id?: number
  username?: string
  action?: string
  resource_type?: string
  status?: string
  start_date?: string
  end_date?: string
}

export interface AuditLogListResponse {
  total: number
  items: AuditLog[]
  page: number
  page_size: number
}

export interface AuditLogExportRequest {
  user_id?: number
  username?: string
  action?: string
  resource_type?: string
  status?: string
  start_date?: string
  end_date?: string
}
