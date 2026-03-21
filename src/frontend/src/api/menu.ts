// src/frontend/src/api/menu.ts
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface Menu {
  id: number
  parent_id?: number
  name: string
  path: string
  icon: string
  sort_order: number
  is_visible: boolean
}

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
  }
}
