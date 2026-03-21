// src/frontend/src/stores/roles.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Role, RoleCreate, RoleUpdate } from '@/types/role'
import { roleApi } from '@/api/role'
import { ElMessage } from 'element-plus'

export const useRolesStore = defineStore('roles', () => {
  const roles = ref<Role[]>([])
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    page_size: 20,
    total: 0
  })

  async function fetchRoles(params?: { page?: number; search?: string }) {
    loading.value = true
    try {
      const response = await roleApi.getRoles({
        page: params?.page || pagination.value.page,
        page_size: pagination.value.page_size,
        search: params?.search
      })
      roles.value = response.items
      pagination.value.total = response.total
      pagination.value.page = response.page
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '获取角色列表失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createRole(data: RoleCreate) {
    try {
      await roleApi.createRole(data)
      ElMessage.success('角色创建成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '创建角色失败')
      throw error
    }
  }

  async function updateRole(id: number, data: RoleUpdate) {
    try {
      await roleApi.updateRole(id, data)
      ElMessage.success('角色更新成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '更新角色失败')
      throw error
    }
  }

  async function deleteRole(id: number) {
    try {
      await roleApi.deleteRole(id)
      ElMessage.success('角色删除成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '删除角色失败')
      throw error
    }
  }

  async function assignMenus(roleId: number, menuIds: number[]) {
    try {
      await roleApi.assignMenus(roleId, { menu_ids: menuIds })
      ElMessage.success('菜单权限分配成功')
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '分配菜单权限失败')
      throw error
    }
  }

  function resetFilters() {
    pagination.value.page = 1
  }

  return {
    roles,
    loading,
    pagination,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
    assignMenus,
    resetFilters
  }
})
