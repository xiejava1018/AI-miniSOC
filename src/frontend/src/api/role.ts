// src/frontend/src/api/role.ts
import axios from 'axios'
import type { Role, RoleCreate, RoleUpdate, RoleListResponse, RoleMenusRequest } from '@/types/role'
import { useAuthStore } from '@/stores/auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 创建axios实例
const roleAxios = axios.create()

// 请求拦截器 - 自动添加token
roleAxios.interceptors.request.use(
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

export const roleApi = {
  async getRoles(params?: { page?: number; page_size?: number; search?: string }): Promise<RoleListResponse> {
    const response = await roleAxios.get<RoleListResponse>(`${API_BASE}/roles`, { params })
    return response.data
  },

  async getRole(id: number): Promise<Role> {
    const response = await roleAxios.get<Role>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async createRole(data: RoleCreate): Promise<Role> {
    const response = await roleAxios.post<Role>(`${API_BASE}/roles`, data)
    return response.data
  },

  async updateRole(id: number, data: RoleUpdate): Promise<Role> {
    const response = await roleAxios.put<Role>(`${API_BASE}/roles/${id}`, data)
    return response.data
  },

  async deleteRole(id: number): Promise<{ success: boolean; message: string }> {
    const response = await roleAxios.delete<{ success: boolean; message: string }>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async getRoleMenus(id: number): Promise<{ role_id: number; menu_ids: number[]; menus: any[] }> {
    const response = await roleAxios.get(`${API_BASE}/roles/${id}/menus`)
    return response.data
  },

  async assignMenus(id: number, data: RoleMenusRequest): Promise<{ success: boolean; message: string; role: Role }> {
    const response = await roleAxios.put(`${API_BASE}/roles/${id}/menus`, data)
    return response.data
  },

  async getRoleUsers(id: number): Promise<{ role_id: number; users: any[] }> {
    const response = await roleAxios.get(`${API_BASE}/roles/${id}/users`)
    return response.data
  }
}
