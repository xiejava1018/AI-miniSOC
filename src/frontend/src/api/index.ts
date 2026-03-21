import apiClient from './client'

// 导出认证相关API
export * from './auth'

// 通用API调用函数
export async function apiCall<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const token = localStorage.getItem('token')

  const response = await fetch(`${baseURL}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options?.headers
    }
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Network error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// 资产管理 API
export const assetsApi = {
  // 获取资产列表
  list: (params?: { skip?: number; limit?: number }) =>
    apiClient.get('/assets', params),

  // 获取资产详情
  get: (id: string) => apiClient.get(`/assets/${id}`),

  // 创建资产
  create: (data: any) => apiClient.post('/assets', data),

  // 更新资产
  update: (id: string, data: any) => apiClient.put(`/assets/${id}`, data),

  // 删除资产
  delete: (id: string) => apiClient.delete(`/assets/${id}`)
}

// 事件管理 API
export const incidentsApi = {
  // 获取事件列表
  list: (params?: { skip?: number; limit?: number }) =>
    apiClient.get('/incidents', params),

  // 获取事件详情
  get: (id: string) => apiClient.get(`/incidents/${id}`),

  // 创建事件
  create: (data: any) => apiClient.post('/incidents', data),

  // 更新事件
  update: (id: string, data: any) => apiClient.put(`/incidents/${id}`, data),

  // 添加时间线记录
  addTimeline: (id: string, data: any) =>
    apiClient.post(`/incidents/${id}/timeline`, data)
}

// 告警管理 API
export const alertsApi = {
  // 获取告警列表
  list: (params?: { skip?: number; limit?: number; level?: number }) =>
    apiClient.get('/alerts', params),

  // 获取告警详情
  get: (id: string) => apiClient.get(`/alerts/${id}`),

  // 从告警创建事件
  createIncident: (id: string, data: any) =>
    apiClient.post(`/alerts/${id}/create-incident`, data)
}

// AI 分析 API
export const aiApi = {
  // 分析告警
  analyzeAlert: (data: {
    alert_id: string
    rule_id?: number
    rule_level?: number
    rule_description?: string
    full_log?: string
    agent_name?: string
    agent_ip?: string
  }) => apiClient.post('/ai/analyze-alert', data),

  // 获取分析结果
  getAnalysis: (id: string) => apiClient.get(`/ai/analysis/${id}`),

  // 解释日志
  explainLog: (data: any) => apiClient.post('/ai/explain', data)
}
