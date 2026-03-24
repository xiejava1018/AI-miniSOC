import apiClient from './client'

// 导出认证相关API
export * from './auth'

// 导出同步相关API
export * from './sync'

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
  delete: (id: string) => apiClient.delete(`/assets/${id}`),

  // 从 Wazuh 同步资产
  syncFromWazuh: () => apiClient.post('/assets/sync/from-wazuh', {})
}

// 资产端口 API
export const assetPortsApi = {
  // 获取资产端口列表
  list: (assetId: string, params?: { skip?: number; limit?: number; protocol?: string; state?: string }) =>
    apiClient.get(`/assets/${assetId}/ports`, params),

  // 获取端口详情
  get: (portId: string) => apiClient.get(`/assets/ports/${portId}`),

  // 创建端口
  create: (assetId: string, data: any) => apiClient.post(`/assets/${assetId}/ports`, data),

  // 更新端口
  update: (portId: string, data: any) => apiClient.put(`/assets/ports/${portId}`, data),

  // 删除端口
  delete: (portId: string) => apiClient.delete(`/assets/ports/${portId}`),

  // 删除资产的所有端口
  deleteAll: (assetId: string) => apiClient.delete(`/assets/${assetId}/ports`)
}

// 资产标签 API
export const assetTagsApi = {
  // 获取资产标签列表
  list: (assetId: string, params?: { skip?: number; limit?: number; tag_key?: string }) =>
    apiClient.get(`/assets/${assetId}/tags`, params),

  // 获取标签详情
  get: (tagId: string) => apiClient.get(`/assets/tags/${tagId}`),

  // 创建标签
  create: (assetId: string, data: any) => apiClient.post(`/assets/${assetId}/tags`, data),

  // 更新标签
  update: (tagId: string, data: any) => apiClient.put(`/assets/tags/${tagId}`, data),

  // 删除标签
  delete: (tagId: string) => apiClient.delete(`/assets/tags/${tagId}`),

  // 删除资产的所有标签
  deleteAll: (assetId: string) => apiClient.delete(`/assets/${assetId}/tags`),

  // 获取常用标签键
  getCommonKeys: () => apiClient.get('/assets/tags/common-keys')
}

// 资产-事件关联 API
export const assetIncidentsApi = {
  // 获取资产关联的事件列表
  list: (assetId: string, params?: { status?: string; severity?: string }) =>
    apiClient.get(`/assets/${assetId}/incidents`, params),

  // 关联资产和事件
  link: (assetId: string, incidentId: string) =>
    apiClient.post(`/assets/${assetId}/incidents/${incidentId}`, {}),

  // 取消关联
  unlink: (assetId: string, incidentId: string) =>
    apiClient.delete(`/assets/${assetId}/incidents/${incidentId}`)
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
