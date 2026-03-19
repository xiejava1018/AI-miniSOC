<template>
  <div class="incident-detail">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span>事件详情</span>
      </template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-descriptions v-if="incident" :column="2" border>
        <el-descriptions-item label="标题">{{ incident.title }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(incident.status)">
            {{ getStatusLabel(incident.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="严重性">
          <el-tag :type="getSeverityType(incident.severity)">
            {{ incident.severity }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="负责人">{{ incident.assigned_to || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ incident.created_by }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ incident.created_at }}</el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">
          {{ incident.description || '-' }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card style="margin-top: 20px" header="处理时间线">
      <el-empty description="暂无时间线记录" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useIncidentStore } from '@/stores/incidents'

const router = useRouter()
const route = useRoute()
const incidentStore = useIncidentStore()

const loading = ref(false)
const incident = ref<any>(null)

onMounted(async () => {
  await loadIncident()
})

async function loadIncident() {
  loading.value = true
  try {
    const id = route.params.id as string
    incident.value = await incidentStore.fetchIncident(id)
  } catch (error) {
    console.error('获取事件详情失败:', error)
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

function goBack() {
  router.back()
}
</script>

<style scoped>
.incident-detail {
  padding: 20px;
}
</style>
