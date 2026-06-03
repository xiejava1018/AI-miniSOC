<template>
  <div class="sca-list">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1 class="page-title">配置检查列表</h1>
      <div class="header-actions">
        <el-button type="primary" @click="syncWazuhSCAData" :loading="syncing">
          同步配置检查
        </el-button>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="filter-bar">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="检查结果">
          <el-select v-model="filters.result" placeholder="全部" clearable @change="loadSCAChecks">
            <el-option label="失败" value="failed" />
            <el-option label="通过" value="passed" />
            <el-option label="不适用" value="not applicable" />
          </el-select>
        </el-form-item>

        <el-form-item label="策略">
          <el-select v-model="filters.policy_id" placeholder="全部" clearable @change="loadSCAChecks">
            <el-option label="CIS Ubuntu 24.04" value="cis_ubuntu24-04" />
            <el-option label="CIS Debian 12" value="cis_debian12" />
            <el-option label="CIS Distribution Independent" value="sca_distro_independent_linux" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="filters.search"
            placeholder="搜索配置名称或资产"
            clearable
            @change="loadSCAChecks"
          >
            <template #prefix>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
    </div>

    <!-- 配置检查列表表格 -->
    <div class="table-container">
      <el-table
        :data="scaChecks"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="sca_check_id" label="检查项ID" width="200" fixed>
          <template #default="{ row }">
            <span class="config-id">{{ row.check_id }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="title" label="配置检查项" min-width="250" show-overflow-tooltip />

        <el-table-column prop="result" label="检查结果" width="100">
          <template #default="{ row }">
            <el-tag :type="getResultType(row.result)">
              {{ getResultLabel(row.result) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="asset_name" label="资产名称" width="150" />

        <el-table-column prop="policy_id" label="策略" width="150" show-overflow-tooltip />

        <el-table-column prop="last_scan_time" label="最后扫描时间" width="180">
          <template #default="{ row }">
            <span>{{ formatTime(row.last_scan_time) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadSCAChecks"
          @current-change="loadSCAChecks"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getVulnerabilities } from '@/api/vulnerabilities'
import { syncAllSCAChecks, getAssetSCAResults } from '@/api/sca'
import { ElMessage } from 'element-plus'

// 筛选条件
const filters = ref({
  result: '',
  policy_id: '',
  search: ''
})

// 分页
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 数据
const scaChecks = ref<any[]>([])
const loading = ref(false)
const syncing = ref(false)

// 方法
const loadSCAChecks = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {
      skip: (pagination.value.page - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize,
      result: filters.value.result || undefined,
      policy_id: filters.value.policy_id || undefined
    }

    const data = await getAssetSCAResults(params)
    scaChecks.value = data.items
    pagination.value.total = data.total
  } catch (error) {
    console.error('加载配置检查列表失败:', error)
    ElMessage.error('加载配置检查列表失败')
  } finally {
    loading.value = false
  }
}

const syncWazuhSCAData = async () => {
  syncing.value = true
  try {
    const result = await syncAllSCAChecks()
    ElMessage.success(`同步完成！新增${result.new_results}条检查结果`)
    await loadSCAChecks()
  } catch (error) {
    console.error('同步失败:', error)
    ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

const viewDetail = (check: any) => {
  ElMessage.info(`查看详情: ${check.title} (ID: ${check.check_id})`)
  // TODO: 打开详情对话框或跳转到详情页
}

const getResultLabel = (result: string) => {
  const labels: Record<string, string> = {
    'passed': '通过',
    'failed': '失败',
    'not applicable': '不适用'
  }
  return labels[result] || result
}

const getResultType = (result: string) => {
  const types: Record<string, any> = {
    'passed': 'success',
    'failed': 'danger',
    'not applicable': 'info'
  }
  return types[result] || ''
}

const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 生命周期
onMounted(() => {
  loadSCAChecks()
})
</script>

<style scoped>
.sca-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.filter-bar {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  padding: 20px;
}

.filter-form {
  margin: 0;
}

.table-container {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  padding: 20px;
}

.config-id {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: var(--accent-cyan);
  font-size: 12px;
}

.score {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
