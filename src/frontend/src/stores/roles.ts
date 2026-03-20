import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Role } from '@/types/role'

export const useRolesStore = defineStore('roles', () => {
  const roles = ref<Role[]>([])
  const loading = ref(false)

  async function fetchRoles() {
    loading.value = true
    try {
      // TODO: 实现实际的API调用
      // 临时使用mock数据
      roles.value = [
        { id: 1, name: '管理员', code: 'admin', is_system: true },
        { id: 2, name: '普通用户', code: 'user', is_system: false }
      ]
    } catch (error) {
      console.error('获取角色列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    roles,
    loading,
    fetchRoles
  }
})
