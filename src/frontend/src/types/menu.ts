// src/frontend/src/types/menu.ts
export interface Menu {
  id: number
  parent_id?: number
  name: string
  path: string
  icon: string
  sort_order: number
  is_visible: boolean
  created_at: string
  updated_at: string
  children?: Menu[]
}

export interface MenuCreate {
  name: string
  path: string
  icon?: string
  parent_id?: number
  sort_order?: number
  is_visible?: boolean
}

export interface MenuUpdate {
  name?: string
  path?: string
  icon?: string
  parent_id?: number
  sort_order?: number
  is_visible?: boolean
}

export interface MenuOption {
  id: number
  name: string
  path: string
}
