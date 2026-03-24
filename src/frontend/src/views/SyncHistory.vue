<template>
  <div class="sync-history">
    <el-page-header @back="goBack" title="返回">
      <template #content><span>同步历史</span></template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-table :data="tasks" style="width: 100%">
        <el-table-column prop="sync_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeTag(row.sync_type)">{{ getTypeLabel(row.sync_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)">{{ getStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="统计" width="300">
          <template #default="{ row }">
            总: {{ row.total_count }} | 新增: {{ row.created_count }} | 更新: {{ row.updated_count }} | 失败: {{ row.failed_count }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="开始时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        @current-change="loadTasks"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { syncApi, type SyncTask } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const loading = ref(false)
const tasks = ref<SyncTask[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

onMounted(() => loadTasks())

async function loadTasks() {
  loading.value = true
  try {
    const data = await syncApi.listTasks({
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value
    })
    tasks.value = data.items
    total.value = data.total
  } catch (error) {
    console.error('加载同步历史失败:', error)
    ElMessage.error('加载同步历史失败')
  } finally {
    loading.value = false
  }
}

function viewDetail(taskId: string) {
  router.push(`/sync-tasks/${taskId}`)
}

function getTypeTag(type: string) {
  const tags: Record<string, string> = { manual: '', webhook: 'success', scheduled: 'warning' }
  return tags[type] || ''
}

function getTypeLabel(type: string) {
  const labels: Record<string, string> = { manual: '手动', webhook: 'Webhook', scheduled: '定时' }
  return labels[type] || type
}

function getStatusTag(status: string) {
  const tags: Record<string, string> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger' }
  return tags[status] || ''
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = { pending: '待执行', running: '执行中', completed: '已完成', failed: '失败' }
  return labels[status] || status
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString('zh-CN')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.sync-history {
  padding: 20px;
}
</style>
