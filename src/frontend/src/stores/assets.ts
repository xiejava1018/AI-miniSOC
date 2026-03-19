import { defineStore } from 'pinia'
import { ref } from 'vue'
import { assetsApi } from '@/api'

export interface Asset {
  id: string
  name: string
  asset_ip: string
  asset_type: string
  criticality: string
  owner?: string
  business_unit?: string
  asset_status?: string
  description?: string
  wazuh_agent_id?: string
  created_at: string
  updated_at: string
}

export const useAssetStore = defineStore('asset', () => {
  const assets = ref<Asset[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取资产列表
  async function fetchAssets(params?: { skip?: number; limit?: number }) {
    loading.value = true
    error.value = null
    try {
      const data = await assetsApi.list(params)
      assets.value = data.items || []
    } catch (err: any) {
      error.value = err.message || '获取资产列表失败'
      console.error('获取资产列表失败:', err)
    } finally {
      loading.value = false
    }
  }

  // 获取单个资产
  async function fetchAsset(id: string) {
    loading.value = true
    error.value = null
    try {
      const data = await assetsApi.get(id)
      return data
    } catch (err: any) {
      error.value = err.message || '获取资产详情失败'
      console.error('获取资产详情失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 创建资产
  async function createAsset(assetData: Partial<Asset>) {
    loading.value = true
    error.value = null
    try {
      const data = await assetsApi.create(assetData)
      assets.value.push(data)
      return data
    } catch (err: any) {
      error.value = err.message || '创建资产失败'
      console.error('创建资产失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 更新资产
  async function updateAsset(id: string, assetData: Partial<Asset>) {
    loading.value = true
    error.value = null
    try {
      const data = await assetsApi.update(id, assetData)
      const index = assets.value.findIndex(a => a.id === id)
      if (index !== -1) {
        assets.value[index] = data
      }
      return data
    } catch (err: any) {
      error.value = err.message || '更新资产失败'
      console.error('更新资产失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 删除资产
  async function deleteAsset(id: string) {
    loading.value = true
    error.value = null
    try {
      await assetsApi.delete(id)
      assets.value = assets.value.filter(a => a.id !== id)
    } catch (err: any) {
      error.value = err.message || '删除资产失败'
      console.error('删除资产失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    assets,
    loading,
    error,
    fetchAssets,
    fetchAsset,
    createAsset,
    updateAsset,
    deleteAsset
  }
})
