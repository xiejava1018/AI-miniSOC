import { defineStore } from 'pinia'
import { ref } from 'vue'
import { incidentsApi } from '@/api'

export interface Incident {
  id: string
  title: string
  description?: string
  status: 'open' | 'in_progress' | 'resolved' | 'closed'
  severity: 'critical' | 'high' | 'medium' | 'low'
  assigned_to?: string
  created_by: string
  created_at: string
  resolved_at?: string
  resolution_notes?: string
}

export const useIncidentStore = defineStore('incident', () => {
  const incidents = ref<Incident[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 获取事件列表
  async function fetchIncidents(params?: { skip?: number; limit?: number }) {
    loading.value = true
    error.value = null
    try {
      const data = await incidentsApi.list(params)
      incidents.value = data.items || []
    } catch (err: any) {
      error.value = err.message || '获取事件列表失败'
      console.error('获取事件列表失败:', err)
    } finally {
      loading.value = false
    }
  }

  // 获取单个事件
  async function fetchIncident(id: string) {
    loading.value = true
    error.value = null
    try {
      const data = await incidentsApi.get(id)
      return data
    } catch (err: any) {
      error.value = err.message || '获取事件详情失败'
      console.error('获取事件详情失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 创建事件
  async function createIncident(incidentData: Partial<Incident>) {
    loading.value = true
    error.value = null
    try {
      const data = await incidentsApi.create(incidentData)
      incidents.value.push(data)
      return data
    } catch (err: any) {
      error.value = err.message || '创建事件失败'
      console.error('创建事件失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  // 更新事件
  async function updateIncident(id: string, incidentData: Partial<Incident>) {
    loading.value = true
    error.value = null
    try {
      const data = await incidentsApi.update(id, incidentData)
      const index = incidents.value.findIndex(i => i.id === id)
      if (index !== -1) {
        incidents.value[index] = data
      }
      return data
    } catch (err: any) {
      error.value = err.message || '更新事件失败'
      console.error('更新事件失败:', err)
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    incidents,
    loading,
    error,
    fetchIncidents,
    fetchIncident,
    createIncident,
    updateIncident
  }
})
