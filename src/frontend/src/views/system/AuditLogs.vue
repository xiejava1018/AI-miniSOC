<!-- src/frontend/src/views/system/AuditLogs.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuditLogsStore } from '@/stores/audit_logs'
import type { AuditLog, AuditLogQuery } from '@/types/audit_log'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'

const auditLogsStore = useAuditLogsStore()

// 筛选条件
const filters = ref<AuditLogQuery>({
  username: '',
  action: '',
  resource_type: '',
  status: '',
  start_date: '',
  end_date: ''
})

// 详情对话框
const detailDialogVisible = ref(false)
const currentLog = ref<AuditLog | null>(null)

// 操作类型选项
const actionOptions = [
  { label: '登录', value: 'LOGIN' },
  { label: '登出', value: 'LOGOUT' },
  { label: '创建', value: 'CREATE' },
  { label: '更新', value: 'UPDATE' },
  { label: '删除', value: 'DELETE' },
  { label: '查询', value: 'QUERY' },
  { label: '导出', value: 'EXPORT' }
]

// 资源类型选项
const resourceTypeOptions = [
  { label: '认证', value: 'auth' },
  { label: '用户', value: 'user' },
  { label: '角色', value: 'role' },
  { label: '菜单', value: 'menu' },
  { label: '资产', value: 'asset' },
  { label: '事件', value: 'incident' },
  { label: '告警', value: 'alert' }
]

// 状态选项
const statusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failure' }
]

// 获取审计日志列表
async function fetchAuditLogs() {
  await auditLogsStore.fetchAuditLogs(filters.value)
}

// 搜索
function handleSearch() {
  auditLogsStore.setFilters(filters.value)
  fetchAuditLogs()
}

// 重置筛选
function handleReset() {
  filters.value = {
    username: '',
    action: '',
    resource_type: '',
    status: '',
    start_date: '',
    end_date: ''
  }
  auditLogsStore.resetFilters()
  fetchAuditLogs()
}

// 查看详情
function viewDetail(log: AuditLog) {
  currentLog.value = log
  detailDialogVisible.value = true
}

// 导出
async function handleExport() {
  try {
    await auditLogsStore.exportAuditLogs(filters.value)
    ElMessage.success('导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

// 获取操作类型标签类型
function getActionTagType(action: string): string {
  const actionMap: Record<string, string> = {
    'LOGIN': 'success',
    'LOGOUT': 'info',
    'CREATE': 'success',
    'UPDATE': 'warning',
    'DELETE': 'danger',
    'QUERY': 'info',
    'EXPORT': 'primary'
  }
  return actionMap[action] || 'info'
}

// 获取操作类型显示名称
function getActionLabel(action: string): string {
  const option = actionOptions.find(opt => opt.value === action)
  return option?.label || action
}

// 格式化JSON显示
function formatJson(data: Record<string, any> | undefined): string {
  if (!data) return '-'
  return JSON.stringify(data, null, 2)
}

// 格式化时间
function formatTime(dateStr: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

onMounted(() => {
  fetchAuditLogs()
})
</script>

<template>
  <div class="audit-logs-container">
    <!-- 筛选工具栏 -->
    <div class="filter-bar">
      <el-form :model="filters" class="filter-form">
        <!-- 第一行：基本筛选条件 -->
        <el-row :gutter="16" class="filter-row">
          <el-col :xs="24" :sm="12" :md="6" :lg="6">
            <el-form-item label="用户">
              <el-input
                v-model="filters.username"
                placeholder="用户名"
                clearable
                @keyup.enter="handleSearch"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6" :lg="6">
            <el-form-item label="操作">
              <el-select
                v-model="filters.action"
                placeholder="操作类型"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="opt in actionOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6" :lg="6">
            <el-form-item label="资源">
              <el-select
                v-model="filters.resource_type"
                placeholder="资源类型"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="opt in resourceTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6" :lg="6">
            <el-form-item label="状态">
              <el-select
                v-model="filters.status"
                placeholder="状态"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="opt in statusOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 第二行：时间范围和操作按钮 -->
        <el-row :gutter="16" class="filter-row">
          <el-col :xs="24" :sm="12" :md="8" :lg="8">
            <el-form-item label="开始时间">
              <el-date-picker
                v-model="filters.start_date"
                type="datetime"
                placeholder="开始时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8" :lg="8">
            <el-form-item label="结束时间">
              <el-date-picker
                v-model="filters.end_date"
                type="datetime"
                placeholder="结束时间"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="8" :lg="8">
            <el-form-item class="action-item">
              <el-button type="primary" @click="handleSearch">搜索</el-button>
              <el-button @click="handleReset">重置</el-button>
              <el-button type="success" @click="handleExport" :icon="Download">导出</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </div>

    <!-- 数据表格 -->
    <div class="table-wrapper">
      <el-table
        :data="auditLogsStore.auditLogs"
        v-loading="auditLogsStore.loading"
        stripe
        @row-click="viewDetail"
        class="audit-table"
        :flexible="true"
      >
        <el-table-column prop="id" label="ID" width="80" align="center" />
        <el-table-column prop="username" label="用户" min-width="120" show-overflow-tooltip />
        <el-table-column prop="action" label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getActionTagType(row.action)" size="small">
              {{ getActionLabel(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="100" align="center">
          <template #default="{ row }">
            <span>{{ row.resource_type || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="resource_name" label="资源名称" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.resource_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="140" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" align="center">
          <template #default="{ row }">
            <span class="time-cell">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="auditLogsStore.pagination.page"
        v-model:page-size="auditLogsStore.pagination.page_size"
        :total="auditLogsStore.pagination.total"
        @current-change="fetchAuditLogs"
        layout="total, sizes, prev, pager, next, jumper"
        :page-sizes="[10, 20, 50, 100]"
      />
    </div>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="审计日志详情" width="800px">
      <el-descriptions v-if="currentLog" :column="2" border>
        <el-descriptions-item label="日志ID">{{ currentLog.id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ currentLog.username }}</el-descriptions-item>
        <el-descriptions-item label="操作类型">
          <el-tag :type="getActionTagType(currentLog.action)">
            {{ getActionLabel(currentLog.action) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="currentLog.status === 'success' ? 'success' : 'danger'">
            {{ currentLog.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="资源类型">{{ currentLog.resource_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源ID">{{ currentLog.resource_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源名称" :span="2">{{ currentLog.resource_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ currentLog.ip_address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="请求ID">{{ currentLog.request_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间" :span="2">
          {{ formatTime(currentLog.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="用户代理" :span="2">
          <div class="user-agent-text">
            {{ currentLog.user_agent || '-' }}
          </div>
        </el-descriptions-item>
        <el-descriptions-item v-if="currentLog.error_message" label="错误信息" :span="2">
          <div class="error-message">{{ currentLog.error_message }}</div>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 变更数据 -->
      <div v-if="currentLog" class="change-data">
        <el-divider content-position="left">变更数据</el-divider>
        <el-tabs type="border-card">
          <el-tab-pane label="变更前数据">
            <pre class="json-display">{{ formatJson(currentLog.old_values) }}</pre>
          </el-tab-pane>
          <el-tab-pane label="变更后数据">
            <pre class="json-display">{{ formatJson(currentLog.new_values) }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.audit-logs-container {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.filter-bar {
  margin-bottom: 16px;
  padding: 16px;
  background-color: var(--el-fill-color-light);
  border-radius: 8px;
}

.filter-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  margin: 0 !important;
}

.filter-row :deep(.el-form-item) {
  margin-bottom: 0;
  width: 100%;
}

.filter-row :deep(.el-form-item__label) {
  width: 80px;
  min-width: 80px;
}

.action-item :deep(.el-form-item__content) {
  display: flex;
  gap: 8px;
}

.table-wrapper {
  flex: 1;
  overflow: auto;
  min-height: 0;
}

.audit-table {
  width: 100%;
  cursor: pointer;
}

.audit-table :deep(.el-table__header-wrapper) {
  position: sticky;
  top: 0;
  z-index: 10;
}

.audit-table :deep(.el-table__body) {
  width: 100% !important;
}

.time-cell {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.change-data {
  margin-top: 20px;
}

.json-display {
  max-height: 300px;
  overflow: auto;
  background-color: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  font-family: 'Courier New', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.user-agent-text {
  max-height: 80px;
  overflow: auto;
  word-break: break-all;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}

.error-message {
  color: #f56c6c;
  word-break: break-word;
  white-space: pre-wrap;
}

/* 响应式布局 */
@media (max-width: 768px) {
  .audit-logs-container {
    padding: 12px;
  }

  .filter-bar {
    padding: 12px;
  }

  .filter-row :deep(.el-form-item__label) {
    width: 70px;
    min-width: 70px;
  }

  .audit-table :deep(.el-table__body-wrapper) {
    overflow-x: auto;
  }

  .action-item :deep(.el-form-item__content) {
    width: 100%;
  }

  .action-item :deep(.el-button) {
    flex: 1;
  }
}
</style>
