import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginRequest, ChangePasswordRequest, AuthResponse } from '@/types/auth'

// API base URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const isAuthenticated = ref<boolean>(false)
  const isLoading = ref<boolean>(false)

  // Getters
  const isAdmin = computed(() => {
    return user.value?.role_name === 'admin'
  })

  const hasPermission = (permission: string): boolean => {
    if (!user.value) return false
    if (isAdmin.value) return true
    return user.value.permissions.includes(permission)
  }

  const hasAnyPermission = (permissions: string[]): boolean => {
    if (!user.value) return false
    if (isAdmin.value) return true
    return permissions.some(permission => user.value.permissions.includes(permission))
  }

  const hasAllPermissions = (permissions: string[]): boolean => {
    if (!user.value) return false
    if (isAdmin.value) return true
    return permissions.every(permission => user.value.permissions.includes(permission))
  }

  const userDisplayName = computed(() => {
    if (!user.value) return ''
    return user.value.full_name || user.value.username
  })

  const userInitials = computed(() => {
    if (!user.value) return ''
    const name = user.value.full_name || user.value.username
    const parts = name.split(' ').filter(Boolean)
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase()
    }
    return name.substring(0, 2).toUpperCase()
  })

  // Helper function to make API calls with auth
  async function apiCall<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers
    }

    if (token.value) {
      headers['Authorization'] = `Bearer ${token.value}`
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Network error' }))
      throw error
    }

    return response.json()
  }

  // Actions
  async function login(username: string, password: string): Promise<AuthResponse> {
    isLoading.value = true

    try {
      const response = await apiCall<{ access_token: string; refresh_token: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password })
      })

      const { access_token, refresh_token } = response

      // Save tokens
      token.value = access_token
      refreshToken.value = refresh_token
      localStorage.setItem('auth_token', access_token)
      localStorage.setItem('auth_refresh_token', refresh_token)

      // Fetch user info
      await fetchUser()

      isAuthenticated.value = true

      return { success: true }
    } catch (error: any) {
      console.error('Login failed:', error)
      return {
        success: false,
        error: error.detail || error.message || '登录失败，请检查用户名和密码'
      }
    } finally {
      isLoading.value = false
    }
  }

  async function logout(): Promise<void> {
    isLoading.value = true

    try {
      // Call logout API
      if (token.value) {
        await apiCall('/auth/logout', { method: 'POST' })
      }
    } catch (error) {
      console.error('Logout API call failed:', error)
    } finally {
      // Clear state
      user.value = null
      token.value = null
      refreshToken.value = null
      isAuthenticated.value = false

      // Clear localStorage
      localStorage.removeItem('auth_token')
      localStorage.removeItem('auth_refresh_token')

      isLoading.value = false
    }
  }

  async function refreshAccessToken(): Promise<string> {
    if (!refreshToken.value) {
      throw new Error('No refresh token available')
    }

    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ refresh_token: refreshToken.value })
    })

    if (!response.ok) {
      throw new Error('Token refresh failed')
    }

    const data = await response.json()
    const { access_token } = data

    // Update token
    token.value = access_token
    localStorage.setItem('auth_token', access_token)

    return access_token
  }

  async function fetchUser(): Promise<User> {
    if (!token.value) {
      throw new Error('No token available')
    }

    const userData = await apiCall<User>('/auth/me')
    user.value = userData
    return userData
  }

  async function changePassword(
    oldPassword: string,
    newPassword: string
  ): Promise<AuthResponse> {
    isLoading.value = true

    try {
      await apiCall('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
          confirm_password: newPassword
        })
      })

      return { success: true }
    } catch (error: any) {
      console.error('Change password failed:', error)
      return {
        success: false,
        error: error.detail || error.message || '修改密码失败'
      }
    } finally {
      isLoading.value = false
    }
  }

  async function initialize(): Promise<void> {
    const savedToken = localStorage.getItem('auth_token')
    const savedRefreshToken = localStorage.getItem('auth_refresh_token')

    if (savedToken && savedRefreshToken) {
      token.value = savedToken
      refreshToken.value = savedRefreshToken

      try {
        await fetchUser()
        isAuthenticated.value = true
      } catch (error: any) {
        console.error('Failed to restore session:', error)
        // Token invalid, clear
        await logout()
      }
    }
  }

  // Check if current session is valid
  async function checkSession(): Promise<boolean> {
    if (!token.value) {
      return false
    }

    try {
      await fetchUser()
      return true
    } catch (error) {
      return false
    }
  }

  return {
    // State
    user,
    token,
    refreshToken,
    isAuthenticated,
    isLoading,

    // Getters
    isAdmin,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    userDisplayName,
    userInitials,

    // Actions
    login,
    logout,
    refreshToken: refreshAccessToken,
    fetchUser,
    changePassword,
    initialize,
    checkSession
  }
})
