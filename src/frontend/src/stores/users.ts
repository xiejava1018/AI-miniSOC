import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { User, UserCreate, UserUpdate } from '@/types/user'
import { apiCall } from '@/api'

interface UserFilters {
  search?: string
  role_id?: number
  status?: string
}

interface Pagination {
  page: number
  page_size: number
  total: number
}

export const useUsersStore = defineStore('users', () => {
  // State
  const users = ref<User[]>([])
  const loading = ref(false)
  const pagination = reactive<Pagination>({
    page: 1,
    page_size: 20,
    total: 0
  })
  const filters = reactive<UserFilters>({})

  // Computed
  const totalPages = computed(() => {
    if (pagination.total === 0) return 0
    return Math.ceil(pagination.total / pagination.page_size)
  })

  // Actions
  async function fetchUsers() {
    loading.value = true
    try {
      const params = new URLSearchParams({
        page: pagination.page.toString(),
        page_size: pagination.page_size.toString(),
        ...(filters.search && { search: filters.search }),
        ...(filters.role_id && { role_id: filters.role_id.toString() }),
        ...(filters.status && { status: filters.status })
      })

      const response = await apiCall<{
        total: number
        page: number
        page_size: number
        items: User[]
      }>(`/users?${params}`)

      users.value = response.items
      pagination.total = response.total
    } catch (error) {
      console.error('获取用户列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createUser(data: UserCreate) {
    loading.value = true
    try {
      const response = await apiCall<User>('/users', {
        method: 'POST',
        body: JSON.stringify(data)
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('创建用户失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function updateUser(id: number, data: UserUpdate) {
    loading.value = true
    try {
      const response = await apiCall<User>(`/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('更新用户失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function deleteUser(id: number) {
    loading.value = true
    try {
      await apiCall(`/users/${id}`, { method: 'DELETE' })
      await fetchUsers()
    } catch (error) {
      console.error('删除用户失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function resetPassword(id: number, new_password?: string) {
    try {
      const response = await apiCall<{ new_password: string }>(
        `/users/${id}/reset-password`,
        {
          method: 'POST',
          body: JSON.stringify({ new_password })
        }
      )
      return response.new_password
    } catch (error) {
      console.error('重置密码失败:', error)
      throw error
    }
  }

  async function toggleLock(id: number, locked: boolean, reason?: string) {
    loading.value = true
    try {
      const response = await apiCall<User>(`/users/${id}/lock`, {
        method: 'POST',
        body: JSON.stringify({ is_locked: locked, lock_reason: reason })
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('锁定用户失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  function resetFilters() {
    filters.search = undefined
    filters.role_id = undefined
    filters.status = undefined
    pagination.page = 1
  }

  return {
    users,
    loading,
    pagination,
    filters,
    totalPages,
    fetchUsers,
    createUser,
    updateUser,
    deleteUser,
    resetPassword,
    toggleLock,
    resetFilters
  }
})
