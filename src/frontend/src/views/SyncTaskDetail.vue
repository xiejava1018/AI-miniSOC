<template>
  <div class="sync-task-detail">
    <el-page-header @back="goBack" title="返回">
      <template #content><span>同步任务详情</span></template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-descriptions v-if="task" :column="2" border>
        <el-descriptions-item label="任务ID">{{ task.id }}</el-descriptions-item>
        <el-descriptions-item label="同步类型">
          <el-tag :type="getTypeTag(task.sync_type)">{{ getTypeLabel(task.sync_type) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTag(task.status)">{{ getStatusLabel(task.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">{{ task.progress || '0%' }}</el-descriptions-item>
        <el-descriptions-item label="总数">{{ task.total_count }}</el-descriptions-item>
        <el-descriptions-item label="新增">{{ task.created_count }}</el-descriptions-item>
        <el-descriptions-item label="更新">{{ task.updated_count }}</el-descriptions-item>
        <el-descriptions-item label="失败">{{ task.failed_count }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatDate(task.started_at) }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ formatDate(task.completed_at) }}</el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="task.error_message" :span="2">
          <el-text type="danger">{{ task.error_message }}</el-text>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-alert v-if="task?.status === 'running'" type="info" :closable="false" style="margin-top: 20px">
      任务执行中，页面将自动刷新...
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { syncApi, type SyncTask } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const task = ref<SyncTask | null>(null)
let refreshInterval: number | null = null

onMounted(() => {
  loadTask()
  if (task.value?.status === 'running') {
    startAutoRefresh()
  }
})

onUnmounted(() => stopAutoRefresh())

async function loadTask() {
  loading.value = true
  try {
    const taskId = route.params.id as string
    task.value = await syncApi.getTask(taskId)
    if (task.value.status !== 'running') {
      stopAutoRefresh()
    } else {
      startAutoRefresh()
    }
  } catch (error) {
    console.error('加载任务详情失败:', error)
    ElMessage.error('加载任务详情失败')
  } finally {
    loading.value = false
  }
}

function startAutoRefresh() {
  if (refreshInterval === null) {
    refreshInterval = window.setInterval(() => {
      loadTask()
    }, 5000)
  }
}

function stopAutoRefresh() {
  if (refreshInterval !== null) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
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

function formatDate(dateStr?: string) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.sync-task-detail {
  padding: 20px;
}
</style>
