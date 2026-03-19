<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card>
          <div class="stat-card">
            <div class="stat-value">{{ stats.totalAssets }}</div>
            <div class="stat-label">总资产</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-card">
            <div class="stat-value critical">{{ stats.openIncidents }}</div>
            <div class="stat-label">待处理事件</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-card">
            <div class="stat-value high">{{ stats.highAlerts }}</div>
            <div class="stat-label">高危告警</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <div class="stat-card">
            <div class="stat-value">{{ stats.onlineAssets }}</div>
            <div class="stat-label">在线资产</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <el-card header="最近事件">
          <el-empty v-if="recentIncidents.length === 0" description="暂无事件" />
          <el-timeline v-else>
            <el-timeline-item
              v-for="incident in recentIncidents"
              :key="incident.id"
              :timestamp="incident.created_at"
            >
              {{ incident.title }}
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="高危告警">
          <el-empty v-if="highAlerts.length === 0" description="暂无告警" />
          <div v-else>
            <div v-for="alert in highAlerts" :key="alert.id" class="alert-item">
              {{ alert.title }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const stats = ref({
  totalAssets: 0,
  openIncidents: 0,
  highAlerts: 0,
  onlineAssets: 0
})

const recentIncidents = ref<any[]>([])
const highAlerts = ref<any[]>([])

onMounted(async () => {
  // TODO: 从 API 获取统计数据
  stats.value = {
    totalAssets: 14,
    openIncidents: 3,
    highAlerts: 5,
    onlineAssets: 8
  }
})
</script>

<style scoped>
.dashboard {
  padding: 20px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 36px;
  font-weight: bold;
  color: #409eff;
}

.stat-value.critical {
  color: #f56c6c;
}

.stat-value.high {
  color: #e6a23c;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}

.alert-item {
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
}
</style>
