import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types/auth'

/**
 * Authentication composable for easy access to auth state and methods
 */
export function useAuth() {
  const authStore = useAuthStore()

  // Computed properties
  const user = computed(() => authStore.user)
  const isAuthenticated = computed(() => authStore.isAuthenticated)
  const isLoading = computed(() => authStore.isLoading)
  const isAdmin = computed(() => authStore.isAdmin)
  const userDisplayName = computed(() => authStore.userDisplayName)
  const userInitials = computed(() => authStore.userInitials)

  // Methods
  const login = authStore.login
  const logout = authStore.logout
  const changePassword = authStore.changePassword
  const checkSession = authStore.checkSession

  // Permission helpers
  const hasPermission = authStore.hasPermission
  const hasAnyPermission = authStore.hasAnyPermission
  const hasAllPermissions = authStore.hasAllPermissions

  return {
    user,
    isAuthenticated,
    isLoading,
    isAdmin,
    userDisplayName,
    userInitials,
    login,
    logout,
    changePassword,
    checkSession,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions
  }
}

/**
 * Check if user has specific permission
 * @param permission - Permission string to check
 * @returns boolean indicating if user has permission
 */
export function hasPermission(permission: string): boolean {
  const authStore = useAuthStore()
  return authStore.hasPermission(permission)
}

/**
 * Check if user has any of the specified permissions
 * @param permissions - Array of permission strings to check
 * @returns boolean indicating if user has any of the permissions
 */
export function hasAnyPermission(permissions: string[]): boolean {
  const authStore = useAuthStore()
  return authStore.hasAnyPermission(permissions)
}

/**
 * Check if user has all of the specified permissions
 * @param permissions - Array of permission strings to check
 * @returns boolean indicating if user has all permissions
 */
export function hasAllPermissions(permissions: string[]): boolean {
  const authStore = useAuthStore()
  return authStore.hasAllPermissions(permissions)
}

/**
 * Check if current user is admin
 * @returns boolean indicating if user is admin
 */
export function isAdmin(): boolean {
  const authStore = useAuthStore()
  return authStore.isAdmin
}

/**
 * Get current user
 * @returns Current user object or null
 */
export function getCurrentUser(): User | null {
  const authStore = useAuthStore()
  return authStore.user
}
