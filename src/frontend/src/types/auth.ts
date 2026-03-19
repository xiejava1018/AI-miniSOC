// User type definitions
export interface User {
  id: number
  username: string
  email?: string
  full_name?: string
  is_active: boolean
  role_id?: number
  role_name?: string
  permissions: string[]
}

// Login request
export interface LoginRequest {
  username: string
  password: string
}

// Token response
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// Change password request
export interface ChangePasswordRequest {
  old_password: string
  new_password: string
  confirm_password: string
}

// Auth response wrapper
export interface AuthResponse {
  success: boolean
  error?: string
}

// API error response
export interface ApiError {
  detail: string
  status_code?: number
}
