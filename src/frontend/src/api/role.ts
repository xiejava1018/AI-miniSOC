// src/frontend/src/api/role.ts
import axios from 'axios'
import type { Role, RoleCreate, RoleUpdate, RoleListResponse, RoleMenusRequest } from '@/types/role'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const roleApi = {
  async getRoles(params?: { page?: number; page_size?: number; search?: string }): Promise<RoleListResponse> {
    const response = await axios.get<RoleListResponse>(`${API_BASE}/roles`, { params })
    return response.data
  },

  async getRole(id: number): Promise<Role> {
    const response = await axios.get<Role>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async createRole(data: RoleCreate): Promise<Role> {
    const response = await axios.post<Role>(`${API_BASE}/roles`, data)
    return response.data
  },

  async updateRole(id: number, data: RoleUpdate): Promise<Role> {
    const response = await axios.put<Role>(`${API_BASE}/roles/${id}`, data)
    return response.data
  },

  async deleteRole(id: number): Promise<{ success: boolean; message: string }> {
    const response = await axios.delete<{ success: boolean; message: string }>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async getRoleMenus(id: number): Promise<{ role_id: number; menu_ids: number[]; menus: any[] }> {
    const response = await axios.get(`${API_BASE}/roles/${id}/menus`)
    return response.data
  },

  async assignMenus(id: number, data: RoleMenusRequest): Promise<{ success: boolean; message: string; role: Role }> {
    const response = await axios.put(`${API_BASE}/roles/${id}/menus`, data)
    return response.data
  },

  async getRoleUsers(id: number): Promise<{ role_id: number; users: any[] }> {
    const response = await axios.get(`${API_BASE}/roles/${id}/users`)
    return response.data
  }
}
