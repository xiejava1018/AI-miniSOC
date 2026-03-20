export interface User {
  id: number
  username: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id: number
  role_name?: string
  status: 'active' | 'locked' | 'disabled'
  is_locked: boolean
  last_login?: string
  password_changed_at?: string
  created_at: string
  updated_at: string
}

export interface UserCreate {
  username: string
  password: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id: number
}

export interface UserUpdate {
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id?: number
  is_active?: boolean
}

export interface Role {
  id: number
  name: string
  code: string
  description?: string
  is_system: boolean
}

export interface UserListResponse {
  total: number
  page: number
  page_size: number
  items: User[]
}

export interface ResetPasswordRequest {
  new_password?: string
}

export interface LockUserRequest {
  is_locked: boolean
  lock_reason?: string
}
