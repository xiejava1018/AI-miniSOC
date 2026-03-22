// src/frontend/src/api/menu.ts
import axios from 'axios'
import type { Menu, MenuCreate, MenuUpdate } from '@/types/menu'
import { useAuthStore } from '@/stores/auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建axios实例
const menuAxios = axios.create()

// 请求拦截器 - 自动添加token
menuAxios.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    console.log('[menuApi] Request:', config.method?.toUpperCase(), config.url)
    console.log('[menuApi] Token exists:', !!authStore.token)
    console.log('[menuApi] Token value:', authStore.token?.substring(0, 20) + '...')
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
      console.log('[menuApi] Authorization header set:', config.headers.Authorization?.substring(0, 30) + '...')
    }
    return config
  },
  (error) => {
    console.error('[menuApi] Request error:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器 - 添加错误日志
menuAxios.interceptors.response.use(
  (response) => {
    console.log('[menuApi] Response:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('[menuApi] Response error:', error.response?.status, error.config?.url)
    console.error('[menuApi] Error data:', error.response?.data)
    return Promise.reject(error)
  }
)

export const menuApi = {
  async getMenus(): Promise<Menu[]> {
    const response = await menuAxios.get<Menu[]>(`${API_BASE}/menus`)
    return response.data
  },

  async getMenuTree(): Promise<Menu[]> {
    const response = await menuAxios.get<Menu[]>(`${API_BASE}/menus/tree`)
    return response.data
  },

  async getMenuOptions(): Promise<any[]> {
    const response = await menuAxios.get(`${API_BASE}/menus/options`)
    return response.data
  },

  async getMenu(id: number): Promise<Menu> {
    const response = await menuAxios.get<Menu>(`${API_BASE}/menus/${id}`)
    return response.data
  },

  async createMenu(data: MenuCreate): Promise<Menu> {
    const response = await menuAxios.post<Menu>(`${API_BASE}/menus`, data)
    return response.data
  },

  async updateMenu(id: number, data: MenuUpdate): Promise<Menu> {
    const response = await menuAxios.put<Menu>(`${API_BASE}/menus/${id}`, data)
    return response.data
  },

  async deleteMenu(id: number): Promise<{ success: boolean; message: string }> {
    const response = await menuAxios.delete<{ success: boolean; message: string }>(`${API_BASE}/menus/${id}`)
    return response.data
  }
}
