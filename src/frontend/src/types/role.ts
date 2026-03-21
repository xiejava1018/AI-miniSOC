// src/frontend/src/types/role.ts
export interface Role {
  id: number
  name: string
  code: string
  description?: string
  is_system: boolean
  user_count: number
  created_at: string
  updated_at: string
}

export interface RoleCreate {
  name: string
  code: string
  description?: string
  menu_ids?: number[]
}

export interface RoleUpdate {
  name?: string
  description?: string
  menu_ids?: number[]
}

export interface RoleListResponse {
  total: number
  items: Role[]
  page: number
  page_size: number
}

export interface RoleMenusRequest {
  menu_ids: number[]
}
