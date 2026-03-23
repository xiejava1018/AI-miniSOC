// API 基础配置
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建 API 客户端
class ApiClient {
  private baseURL: string

  constructor(baseURL: string) {
    this.baseURL = baseURL
  }

  async get<T>(url: string, params?: Record<string, any>): Promise<T> {
    const queryString = params ? new URLSearchParams(params).toString() : ''
    // 确保URL末尾有斜杠以避免307重定向
    const normalizedUrl = url.endsWith('/') ? url : `${url}/`
    const response = await fetch(`${this.baseURL}${normalizedUrl}${queryString ? `?${queryString}` : ''}`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return response.json()
  }

  async post<T>(url: string, data?: any): Promise<T> {
    console.log('POST request:', `${this.baseURL}${url}`, data)
    // 确保URL末尾有斜杠以避免307重定向
    const normalizedUrl = url.endsWith('/') ? url : `${url}/`
    const response = await fetch(`${this.baseURL}${normalizedUrl}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: data ? JSON.stringify(data) : undefined
    })
    if (!response.ok) {
      const errorText = await response.text()
      console.error('POST error:', response.status, errorText)
      throw new Error(`HTTP error! status: ${response.status} - ${errorText}`)
    }
    return response.json()
  }

  async put<T>(url: string, data?: any): Promise<T> {
    // 确保URL末尾有斜杠以避免307重定向
    const normalizedUrl = url.endsWith('/') ? url : `${url}/`
    const response = await fetch(`${this.baseURL}${normalizedUrl}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: data ? JSON.stringify(data) : undefined
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return response.json()
  }

  async delete<T>(url: string): Promise<T> {
    // 确保URL末尾有斜杠以避免307重定向
    const normalizedUrl = url.endsWith('/') ? url : `${url}/`
    const response = await fetch(`${this.baseURL}${normalizedUrl}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return response.json()
  }
}

export const apiClient = new ApiClient(API_BASE_URL)
export default apiClient
