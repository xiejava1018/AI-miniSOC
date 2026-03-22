import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Role } from '@/types/role'
import { roleApi } from '@/api/role'

export const useRolesStore = defineStore('roles', () => {
  const roles = ref<Role[]>([])
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    page_size: 20,
    total: 0
  })

  // 搜索和筛选
  const filters = ref({
    search: ''
  })

  async function fetchRoles(params?: { search?: string; page?: number; page_size?: number }) {
    loading.value = true
    try {
      const response = await roleApi.getRoles({
        search: params?.search || filters.value.search,
        page: params?.page || pagination.value.page,
        page_size: params?.page_size || pagination.value.page_size
      })

      roles.value = response.items
      pagination.value = {
        page: response.page,
        page_size: response.page_size,
        total: response.total
      }
    } catch (error) {
      console.error('获取角色列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createRole(data: any) {
    loading.value = true
    try {
      const response = await roleApi.createRole(data)
      await fetchRoles() // 刷新列表
      return response
    } catch (error) {
      console.error('创建角色失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function updateRole(id: number, data: any) {
    loading.value = true
    try {
      const response = await roleApi.updateRole(id, data)
      await fetchRoles() // 刷新列表
      return response
    } catch (error) {
      console.error('更新角色失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function deleteRole(id: number) {
    loading.value = true
    try {
      await roleApi.deleteRole(id)
      await fetchRoles() // 刷新列表
    } catch (error) {
      console.error('删除角色失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function assignMenus(roleId: number, menuIds: number[]) {
    loading.value = true
    try {
      await roleApi.assignMenus(roleId, { menu_ids: menuIds })
    } catch (error) {
      console.error('分配菜单权限失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  function resetFilters() {
    filters.value = {
      search: ''
    }
    pagination.value = {
      page: 1,
      page_size: 20,
      total: 0
    }
  }

  return {
    roles,
    loading,
    pagination,
    filters,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
    assignMenus,
    resetFilters
  }
})
