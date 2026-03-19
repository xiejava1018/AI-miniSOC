<template>
  <div class="incidents-page">
    <div class="page-header">
      <h2>事件管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        创建事件
      </el-button>
    </div>

    <el-card>
      <el-table :data="incidents" v-loading="loading" stripe>
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="status" label="状态">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="严重性">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)">
              {{ row.severity }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="assigned_to" label="负责人" />
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="viewIncident(row)">查看</el-button>
            <el-button size="small" type="primary" @click="editIncident(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { useIncidentStore } from '@/stores/incidents'

const router = useRouter()
const incidentStore = useIncidentStore()

const loading = ref(false)
const incidents = ref<any[]>([])
const showCreateDialog = ref(false)

onMounted(async () => {
  await loadIncidents()
})

async function loadIncidents() {
  loading.value = true
  try {
    await incidentStore.fetchIncidents()
    incidents.value = incidentStore.incidents
  } finally {
    loading.value = false
  }
}

function getStatusType(status: string) {
  const map: Record<string, string> = {
    open: 'danger',
    in_progress: 'warning',
    resolved: 'success',
    closed: 'info'
  }
  return map[status] || 'info'
}

function getStatusLabel(status: string) {
  const map: Record<string, string> = {
    open: '待处理',
    in_progress: '处理中',
    resolved: '已解决',
    closed: '已关闭'
  }
  return map[status] || status
}

function getSeverityType(severity: string) {
  const map: Record<string, string> = {
    critical: 'danger',
    high: 'warning',
    medium: 'info',
    low: 'info'
  }
  return map[severity] || 'info'
}

function viewIncident(incident: any) {
  router.push(`/incidents/${incident.id}`)
}

function editIncident(incident: any) {
  console.log('编辑事件:', incident)
}
</script>

<style scoped>
.incidents-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
</style>
