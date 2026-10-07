<template>
  <div class="dispatch-logs-page">
    <div class="page-header">
      <h3 class="page-title">投递日志</h3>
      <p class="page-subtitle">每通道投递状态 / 重试 / 错误（admin · OH-NOT-F2 Phase 3）</p>
    </div>

    <el-card shadow="never">
      <!-- 筛选 -->
      <div class="filters">
        <el-select v-model="filters.channel_code" placeholder="通道" clearable style="width: 140px">
          <el-option label="站内信" value="inbox" />
          <el-option label="邮件" value="email" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width: 140px">
          <el-option label="pending" value="pending" />
          <el-option label="sent" value="sent" />
          <el-option label="failed" value="failed" />
          <el-option label="bounced" value="bounced" />
          <el-option label="skipped_pref" value="skipped_pref" />
        </el-select>
        <el-input-number
          v-model="filters.user_id"
          :min="1"
          placeholder="用户 ID"
          controls-position="right"
          style="width: 140px"
        />
        <el-button type="primary" @click="onSearch">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border style="width: 100%">
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="channel_code" label="通道" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.channel_code === 'email' ? 'warning' : 'info'">
              {{ row.channel_code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="user_id" label="用户" width="70" />
        <el-table-column prop="retry_count" label="重试" width="70" align="center" />
        <el-table-column prop="sent_at" label="送达时间" width="180">
          <template #default="{ row }">{{ formatTime(row.sent_at) || '—' }}</template>
        </el-table-column>
        <el-table-column prop="next_retry_at" label="下次重试" width="180">
          <template #default="{ row }">{{ formatTime(row.next_retry_at) || '—' }}</template>
        </el-table-column>
        <el-table-column prop="error_text" label="错误" min-width="240" show-overflow-tooltip />
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * 通知投递日志（admin）— OH-NOT-F2 Phase 3
 *
 * observability：soc_notification_dispatch_logs 查询（通道/状态/用户筛选 + 分页）。
 */
import { onMounted, reactive, ref } from 'vue'
import { fetchDispatchLogs, type DispatchLogItem } from '@/api/notificationChannel'

defineOptions({ name: 'NotificationDispatchLogs' })

const loading = ref(false)
const rows = ref<DispatchLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

const filters = reactive<{ channel_code?: string; status?: string; user_id?: number }>({})

const statusType = (s: string) => {
  if (s === 'sent') return 'success'
  if (s === 'failed' || s === 'bounced') return 'danger'
  if (s === 'pending') return 'warning'
  return 'info'
}

const formatTime = (v: string | null) => (v ? v.replace('T', ' ').slice(0, 19) : '')

const load = async () => {
  loading.value = true
  try {
    const res = await fetchDispatchLogs({
      page: page.value,
      page_size: pageSize,
      channel_code: filters.channel_code || undefined,
      status: filters.status || undefined,
      user_id: filters.user_id || undefined
    })
    if (res.code === 200 && res.data) {
      rows.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.value = 1
  load()
}

const onReset = () => {
  filters.channel_code = undefined
  filters.status = undefined
  filters.user_id = undefined
  onSearch()
}

onMounted(load)
</script>

<style scoped>
.dispatch-logs-page {
  padding: 16px;
}
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.page-header {
  padding: 4px 0 12px;
}
.page-title {
  margin: 0;
  font-size: 18px;
}
.page-subtitle {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
