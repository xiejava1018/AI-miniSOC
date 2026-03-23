import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AuditLog, AuditLogQuery, AuditLogListResponse } from '@/types/audit_log'
import { auditLogApi } from '@/api/audit_log'

export const useAuditLogsStore = defineStore('auditLogs', () => {
  const auditLogs = ref<AuditLog[]>([])
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    page_size: 20,
    total: 0
  })

  // 筛选条件
  const filters = ref<AuditLogQuery>({})

  async function fetchAuditLogs(params?: AuditLogQuery) {
    loading.value = true
    try {
      const response = await auditLogApi.getAuditLogs({
        ...filters.value,
        ...params,
        page: params?.page || pagination.value.page,
        page_size: params?.page_size || pagination.value.page_size
      })

      auditLogs.value = response.items
      pagination.value = {
        page: response.page,
        page_size: response.page_size,
        total: response.total
      }
    } catch (error) {
      console.error('获取审计日志列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function getAuditLogDetail(id: number): Promise<AuditLog> {
    try {
      return await auditLogApi.getAuditLog(id)
    } catch (error) {
      console.error('获取审计日志详情失败:', error)
      throw error
    }
  }

  async function exportAuditLogs(filters: AuditLogQuery) {
    try {
      const blob = await auditLogApi.exportAuditLogs(filters)

      // 创建下载链接
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('导出审计日志失败:', error)
      throw error
    }
  }

  function resetFilters() {
    filters.value = {}
    pagination.value = {
      page: 1,
      page_size: 20,
      total: 0
    }
  }

  function setFilters(newFilters: AuditLogQuery) {
    filters.value = { ...newFilters }
    pagination.value.page = 1 // 重置到第一页
  }

  return {
    auditLogs,
    loading,
    pagination,
    filters,
    fetchAuditLogs,
    getAuditLogDetail,
    exportAuditLogs,
    resetFilters,
    setFilters
  }
})
