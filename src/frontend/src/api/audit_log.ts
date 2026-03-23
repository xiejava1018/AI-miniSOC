// src/frontend/src/api/audit_log.ts
import axios from 'axios'
import type { AuditLog, AuditLogQuery, AuditLogListResponse, AuditLogExportRequest } from '@/types/audit_log'
import { useAuthStore } from '@/stores/auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建axios实例
const auditLogAxios = axios.create()

// 请求拦截器 - 自动添加token
auditLogAxios.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

export const auditLogApi = {
  async getAuditLogs(params: AuditLogQuery = {}): Promise<AuditLogListResponse> {
    const response = await auditLogAxios.get<AuditLogListResponse>(`${API_BASE}/audit-logs`, { params })
    return response.data
  },

  async getAuditLog(id: number): Promise<AuditLog> {
    const response = await auditLogAxios.get<AuditLog>(`${API_BASE}/audit-logs/${id}`)
    return response.data
  },

  async exportAuditLogs(filters: AuditLogExportRequest): Promise<Blob> {
    const response = await auditLogAxios.post(`${API_BASE}/audit-logs/export`, filters, {
      responseType: 'blob'
    })
    return response.data
  }
}
