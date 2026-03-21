// src/frontend/src/stores/menus.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Menu, MenuCreate, MenuUpdate } from '@/types/menu'
import { menuApi } from '@/api/menu'
import { ElMessage } from 'element-plus'

export const useMenusStore = defineStore('menus', () => {
  const menus = ref<Menu[]>([])
  const menuTree = ref<Menu[]>([])
  const loading = ref(false)

  async function fetchMenus() {
    loading.value = true
    try {
      menus.value = await menuApi.getMenus()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '获取菜单列表失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  async function fetchMenuTree() {
    loading.value = true
    try {
      menuTree.value = await menuApi.getMenuTree()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '获取菜单树失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createMenu(data: MenuCreate) {
    try {
      await menuApi.createMenu(data)
      ElMessage.success('菜单创建成功')
      await fetchMenuTree()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '创建菜单失败')
      throw error
    }
  }

  async function updateMenu(id: number, data: MenuUpdate) {
    try {
      await menuApi.updateMenu(id, data)
      ElMessage.success('菜单更新成功')
      await fetchMenuTree()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '更新菜单失败')
      throw error
    }
  }

  async function deleteMenu(id: number) {
    try {
      await menuApi.deleteMenu(id)
      ElMessage.success('菜单删除成功')
      await fetchMenuTree()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '删除菜单失败')
      throw error
    }
  }

  return {
    menus,
    menuTree,
    loading,
    fetchMenus,
    fetchMenuTree,
    createMenu,
    updateMenu,
    deleteMenu
  }
})
