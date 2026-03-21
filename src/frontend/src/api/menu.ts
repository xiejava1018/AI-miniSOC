// src/frontend/src/api/menu.ts
import axios from 'axios'
import type { Menu, MenuCreate, MenuUpdate } from '@/types/menu'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const menuApi = {
  async getMenus(): Promise<Menu[]> {
    const response = await axios.get<Menu[]>(`${API_BASE}/menus`)
    return response.data
  },

  async getMenuTree(): Promise<Menu[]> {
    const response = await axios.get<Menu[]>(`${API_BASE}/menus/tree`)
    return response.data
  },

  async getMenuOptions(): Promise<any[]> {
    const response = await axios.get(`${API_BASE}/menus/options`)
    return response.data
  },

  async getMenu(id: number): Promise<Menu> {
    const response = await axios.get<Menu>(`${API_BASE}/menus/${id}`)
    return response.data
  },

  async createMenu(data: MenuCreate): Promise<Menu> {
    const response = await axios.post<Menu>(`${API_BASE}/menus`, data)
    return response.data
  },

  async updateMenu(id: number, data: MenuUpdate): Promise<Menu> {
    const response = await axios.put<Menu>(`${API_BASE}/menus/${id}`, data)
    return response.data
  },

  async deleteMenu(id: number): Promise<{ success: boolean; message: string }> {
    const response = await axios.delete<{ success: boolean; message: string }>(`${API_BASE}/menus/${id}`)
    return response.data
  }
}
