<!-- 审计日志页面 -->
<template>
  <div class="audit-log-page art-full-height" id="table-full-screen">
    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="resetSearchParams"
      @search="getDataByPage"
    />

    <ElCard shadow="never" class="art-table-card">
      <!-- 表格头部 -->
      <ArtTableHeader v-model:columns="columnChecks" @refresh="refresh">
        <template #left>
          <ElButton @click="handleExport" :loading="exportLoading">导出CSV</ElButton>
        </template>
      </ArtTableHeader>

      <!-- 表格 -->
      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />

      <!-- 详情弹窗 -->
      <ElDialog
        v-model="detailVisible"
        title="审计日志详情"
        width="900px"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <div v-if="detail" class="detail-content">
          <ElDescriptions :column="2" border>
            <ElDescriptionsItem label="ID">{{ detail.id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="用户名">{{ detail.username }}</ElDescriptionsItem>
            <ElDescriptionsItem label="操作类型">
              <ElTag :type="getActionTagType(detail.action)" size="small">
                {{ detail.action }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="资源类型">{{ detail.resource_type || '-' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="资源ID">{{ detail.resource_id ?? '-' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="资源名称">{{ detail.resource_name || '-' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="IP地址">{{ detail.ip_address || '-' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="状态">
              <ElTag :type="detail.status === 'success' ? 'success' : 'danger'" size="small">
                {{ detail.status }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="创建时间" :span="2">{{ formatDateTime(detail.created_at) }}</ElDescriptionsItem>
            <ElDescriptionsItem label="错误信息" :span="2">
              {{ detail.error_message || '-' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="User Agent" :span="2">
              <span class="ua-text">{{ detail.user_agent || '-' }}</span>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="变更前数据" :span="2">
              <pre v-if="detail.old_values" class="json-pre">{{ formatJson(detail.old_values) }}</pre>
              <span v-else class="muted">-</span>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="变更后数据" :span="2">
              <pre v-if="detail.new_values" class="json-pre">{{ formatJson(detail.new_values) }}</pre>
              <span v-else class="muted">-</span>
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>
      </ElDialog>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, h, resolveComponent } from 'vue'
  import { ElMessage } from 'element-plus'
  import axios from 'axios'
  import { getAuditLogList, getAuditLogDetail } from '@/api/audit-log'
  import { useUserStore } from '@/store/modules/user'
  import { useTable } from '@/composables/useTable'
  import type { SearchFormItem } from '@/types'

  defineOptions({ name: 'AuditLog' })

  const userStore = useUserStore()

  // 操作类型下拉
  const actionOptions = [
    { label: 'CREATE', value: 'CREATE' },
    { label: 'UPDATE', value: 'UPDATE' },
    { label: 'DELETE', value: 'DELETE' },
    { label: 'LOGIN', value: 'LOGIN' },
    { label: 'LOGOUT', value: 'LOGOUT' },
    { label: 'EXPORT', value: 'EXPORT' },
    { label: 'IMPORT', value: 'IMPORT' },
  ]

  // 状态下拉
  const statusOptions = [
    { label: '成功', value: 'success' },
    { label: '失败', value: 'failure' },
  ]

  // 搜索表单配置
  const searchItems: SearchFormItem[] = [
    {
      label: '用户名',
      key: 'username',
      type: 'input',
      clearable: true,
      placeholder: '请输入用户名',
    },
    {
      label: '操作类型',
      key: 'action',
      type: 'select',
      clearable: true,
      placeholder: '请选择',
      options: actionOptions,
    },
    {
      label: '资源类型',
      key: 'resource_type',
      type: 'input',
      clearable: true,
      placeholder: '如 user / role / menu',
    },
    {
      label: '状态',
      key: 'status',
      type: 'select',
      clearable: true,
      placeholder: '请选择',
      options: statusOptions,
    },
    {
      label: '开始日期',
      key: 'start_date',
      type: 'date',
      clearable: true,
      placeholder: '开始日期',
    },
    {
      label: '结束日期',
      key: 'end_date',
      type: 'date',
      clearable: true,
      placeholder: '结束日期',
    },
  ]

  // 详情弹窗
  const detailVisible = ref(false)
  const detail = ref<Api.AuditLog.AuditLogItem | null>(null)
  const exportLoading = ref(false)

  // 操作类型 Tag 颜色
  const getActionTagType = (action: string) => {
    const map: Record<string, string> = {
      CREATE: 'success',
      UPDATE: 'warning',
      DELETE: 'danger',
      LOGIN: 'primary',
      LOGOUT: 'info',
      EXPORT: 'info',
      IMPORT: 'info',
    }
    return (map[action] || "info") as "info" | "primary" | "success" | "warning" | "danger"
  }

  // JSON 格式化
  const formatJson = (val: any) => {
    if (!val) return ''
    try {
      if (typeof val === 'string') return val
      return JSON.stringify(val, null, 2)
    } catch {
      return String(val)
    }
  }

  // 时间格式化（友好显示）
  const formatDateTime = (val: any): string => {
    if (!val) return '-'
    try {
      const d = new Date(val)
      if (isNaN(d.getTime())) return String(val)
      return d.toLocaleString('zh-CN', { hour12: false })
    } catch {
      return String(val)
    }
  }

  // useTable
  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    searchParams,
    getData: getDataByPage,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshAll: refresh,
  } = useTable<any>({
    core: {
      apiFn: getAuditLogList,
      apiParams: {
        page: 1,
        page_size: 20,
        username: '',
        action: '',
        resource_type: '',
        status: '',
        start_date: '',
        end_date: '',
      },
      paginationKey: {
        current: 'page',
        size: 'page_size'
      },
      columnsFactory: () => [
        {
          prop: 'id',
          label: 'ID',
          align: 'center',
          width: 80,
        },
        {
          prop: 'username',
          label: '用户名',
          align: 'center',
          width: 120,
        },
        {
          prop: 'action',
          label: '操作类型',
          align: 'center',
          width: 110,
          formatter: (row: any) =>
            h(
              resolveComponent('ElTag'),
              { type: getActionTagType(row.action) as any, size: 'small' },
              { default: () => row.action }
            ),
        },
        {
          prop: 'resource_type',
          label: '资源类型',
          align: 'center',
          width: 120,
          formatter: (row: any) => row.resource_type || '-',
        },
        {
          prop: 'resource_name',
          label: '资源名称',
          align: 'center',
          minWidth: 140,
          showOverflowTooltip: true,
          formatter: (row: any) => row.resource_name || '-',
        },
        {
          prop: 'ip_address',
          label: 'IP地址',
          align: 'center',
          width: 140,
          formatter: (row: any) => row.ip_address || '-',
        },
        {
          prop: 'status',
          label: '状态',
          align: 'center',
          width: 80,
          formatter: (row: any) =>
            h(
              resolveComponent('ElTag'),
              { type: (row.status === 'success' ? 'success' : 'danger') as any, size: 'small' },
              { default: () => (row.status === 'success' ? '成功' : '失败') }
            ),
        },
        {
          prop: 'created_at',
          label: '创建时间',
          align: 'center',
          width: 170,
          formatter: (row: any) => formatDateTime(row.created_at),
        },
        {
          prop: 'operation',
          label: '操作',
          align: 'center',
          width: 100,
          fixed: 'right',
          formatter: (row: any) =>
            h(
              'el-button',
              {
                type: 'primary',
                link: true,
                onClick: () => showDetail(row.id),
              },
              { default: () => '查看' }
            ),
        },
      ],
    },
    hooks: {
      onError: (error) => ElMessage.error(error.message),
    },
  })

  // 查看详情
  const showDetail = async (id: number) => {
    try {
      const data = await getAuditLogDetail(id)
      detail.value = data
      detailVisible.value = true
    } catch (e: any) {
      ElMessage.error(e?.message || '获取详情失败')
    }
  }

  // 导出 CSV
  const handleExport = async () => {
    exportLoading.value = true
    try {
      const params: Record<string, any> = {
        user_id: (searchParams as any).user_id,
        username: (searchParams as any).username,
        action: (searchParams as any).action,
        resource_type: (searchParams as any).resource_type,
        status: (searchParams as any).status,
        start_date: (searchParams as any).start_date,
        end_date: (searchParams as any).end_date,
      }
      // 清理空值
      Object.keys(params).forEach((k) => {
        if (params[k] === '' || params[k] === undefined || params[k] === null) {
          delete params[k]
        }
      })

      const { VITE_API_URL } = import.meta.env
      // 直接通过 axios 调用，避免被全局 response 拦截器解析
      const res = await axios.post(`${VITE_API_URL}/api/v1/audit-logs/export`, params, {
        responseType: 'blob',
        headers: {
          Authorization: userStore.accessToken
            ? /^Bearer\s+/i.test(userStore.accessToken)
              ? userStore.accessToken
              : `Bearer ${userStore.accessToken}`
            : '',
        },
        timeout: 30000,
      })

      // 提取文件名
      const dispo = res.headers['content-disposition'] || ''
      let filename = `audit_logs_${Date.now()}.csv`
      const match = /filename=([^;]+)/.exec(dispo)
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '').trim()
      }

      // 触发浏览器下载
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)

      ElMessage.success('导出成功')
    } catch (e: any) {
      ElMessage.error(e?.message || '导出失败')
    } finally {
      exportLoading.value = false
    }
  }
</script>

<style lang="scss" scoped>
  .audit-log-page {
    .json-pre {
      max-height: 240px;
      overflow: auto;
      padding: 8px 12px;
      margin: 0;
      background-color: var(--el-fill-color-light);
      border-radius: 4px;
      font-size: 12px;
      font-family: 'Courier New', Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .ua-text {
      word-break: break-all;
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }
    .muted {
      color: var(--el-text-color-placeholder);
    }
  }
</style>
