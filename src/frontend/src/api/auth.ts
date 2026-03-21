/**
 * 认证API
 */

import apiClient from './client'

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: {
    id: number
    username: string
    email: string
    full_name: string
    role_id: number
    role_name: string
    is_admin: boolean
    status: string
    last_login: string | null
  }
}

export interface RefreshTokenRequest {
  refresh_token: string
}

export interface RefreshTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

/**
 * 用户登录
 */
export async function login(data: LoginRequest): Promise<LoginResponse> {
  return apiClient.post<LoginResponse>('/auth/login', data)
}

/**
 * 刷新访问令牌
 */
export async function refreshToken(data: RefreshTokenRequest): Promise<RefreshTokenResponse> {
  return apiClient.post<RefreshTokenResponse>('/auth/refresh', data)
}

/**
 * 用户登出
 */
export async function logout(): Promise<{ success: boolean; message: string }> {
  return apiClient.post<{ success: boolean; message: string }>('/auth/logout', {})
}

/**
 * 获取当前用户信息
 */
export async function getCurrentUser(): Promise<any> {
  return apiClient.get<any>('/auth/me')
}
