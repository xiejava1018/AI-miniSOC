<!--
  事件管理页

  对接后端 /api/v1/incidents：
  - 列表（分页 + status/severity 筛选）
  - 详情抽屉（含 AI 研判来源的描述、关联告警）
  - 状态流转（open → in_progress → resolved → closed）+ 处理说明

  事件来源：告警/告警簇一键建事件（Phase 3）、手动创建、MCP。
-->
<template>
  <div class="incident-page">
    <!-- 筛选 -->
    <ElCard shadow="never" class="filter-card">
      <ElForm :inline="true" @submit.prevent>
        <ElFormItem label="状态">
          <ElSelect v-model="filters.status" clearable placeholder="全部" style="width: 140px">
            <ElOption v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="严重度">
          <ElSelect v-model="filters.severity" clearable placeholder="全部" style="width: 140px">
            <ElOption v-for="s in SEVERITY_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="loading" @click="onSearch">查询</ElButton>
          <ElButton @click="resetFilter">重置</ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>

    <!-- 列表 -->
    <ElCard shadow="never">
      <ElTable :data="list" v-loading="loading" stripe>
        <ElTableColumn label="标题" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="incident-title">{{ row.title }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="严重度" width="90" align="center">
          <template #default="{ row }">
            <ElTag :type="severityMeta(row.severity).type" effect="dark" size="small">
              {{ severityMeta(row.severity).label }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="90" align="center">
          <template #default="{ row }">
            <ElTag :type="statusMeta(row.status).type" effect="plain" size="small">
              {{ statusMeta(row.status).label }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="创建人" width="110" prop="created_by" />
        <ElTableColumn label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <ElButton text type="primary" size="small" @click="showDetail(row)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>
      <div class="pagination">
        <ElPagination
          v-model:current-page="page.current"
          v-model:page-size="page.size"
          :total="page.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @size-change="onSizeChange"
          @current-change="fetchList"
        />
      </div>
    </ElCard>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="drawerVisible" title="事件详情" size="600px" destroy-on-close>
      <div v-loading="detailLoading">
        <template v-if="detail">
          <ElDescriptions :column="2" border>
            <ElDescriptionsItem label="标题" :span="2">{{ detail.title }}</ElDescriptionsItem>
            <ElDescriptionsItem label="严重度">
              <ElTag :type="severityMeta(detail.severity).type" effect="dark" size="small">
                {{ severityMeta(detail.severity).label }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="状态">
              <ElTag :type="statusMeta(detail.status).type" effect="plain" size="small">
                {{ statusMeta(detail.status).label }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="创建人">{{ detail.created_by }}</ElDescriptionsItem>
            <ElDescriptionsItem label="创建时间">{{ formatTime(detail.created_at) }}</ElDescriptionsItem>
            <ElDescriptionsItem v-if="detail.assigned_to" label="负责人">
              {{ detail.assigned_to }}
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="detail.resolved_at" label="解决时间">
              {{ formatTime(detail.resolved_at) }}
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="detail.wazuh_alert_id" label="来源告警" :span="2">
              <span class="mono">{{ detail.wazuh_alert_id }}</span>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="描述" :span="2">
              <pre class="desc-pre">{{ detail.description || '—' }}</pre>
            </ElDescriptionsItem>
            <ElDescriptionsItem v-if="detail.resolution_notes" label="处理说明" :span="2">
              <pre class="desc-pre">{{ detail.resolution_notes }}</pre>
            </ElDescriptionsItem>
          </ElDescriptions>

          <!-- 状态流转 -->
          <div class="status-flow">
            <div class="block-title">状态处理</div>
            <ElForm label-width="90px">
              <ElFormItem label="新状态">
                <ElSelect v-model="editForm.status" style="width: 160px">
                  <ElOption v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
                </ElSelect>
              </ElFormItem>
              <ElFormItem label="处理说明">
                <ElInput
                  v-model="editForm.resolution_notes"
                  type="textarea"
                  :rows="3"
                  placeholder="处理过程/结论（可选，状态置为已解决/已关闭时建议填写）"
                />
              </ElFormItem>
              <ElFormItem>
                <ElButton type="primary" :loading="saving" @click="saveStatus">保存</ElButton>
              </ElFormItem>
            </ElForm>
          </div>
        </template>
        <ElEmpty v-else-if="!detailLoading" description="未加载到事件" />
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getIncidentList,
  getIncidentDetail,
  updateIncident,
  statusMeta,
  severityMeta,
  STATUS_OPTIONS,
  SEVERITY_OPTIONS,
  type IncidentItem,
  type IncidentStatus
} from '@/api/incident'

defineOptions({ name: 'IncidentListPage' })

// ── 列表状态 ────────────────────────────────────────
const loading = ref(false)
const list = ref<IncidentItem[]>([])
const page = reactive({ current: 1, size: 20, total: 0 })
const filters = reactive({ status: '' as string, severity: '' as string })

// ── 详情 / 状态流转 ─────────────────────────────────
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<IncidentItem | null>(null)
const editForm = reactive({ status: 'open' as IncidentStatus, resolution_notes: '' })
const saving = ref(false)

const formatTime = (ts?: string | null) => {
  if (!ts) return '—'
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toLocaleString('zh-CN', { hour12: false })
}

const fetchList = async () => {
  loading.value = true
  try {
    const res: any = await getIncidentList({
      skip: (page.current - 1) * page.size,
      limit: page.size,
      status: filters.status || undefined,
      severity: filters.severity || undefined
    })
    const data = res?.data || res
    list.value = data?.items || []
    page.total = data?.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || '查询事件失败')
  } finally {
    loading.value = false
  }
}

const onSearch = () => {
  page.current = 1
  fetchList()
}

const onSizeChange = () => {
  page.current = 1
  fetchList()
}

const resetFilter = () => {
  filters.status = ''
  filters.severity = ''
  page.current = 1
  fetchList()
}

const showDetail = async (row: IncidentItem) => {
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const res: any = await getIncidentDetail(row.id)
    const d = res?.data || res
    detail.value = d
    editForm.status = d.status as IncidentStatus
    editForm.resolution_notes = d.resolution_notes || ''
  } catch {
    // 降级：用列表行数据
    detail.value = row
    editForm.status = row.status as IncidentStatus
    editForm.resolution_notes = row.resolution_notes || ''
  } finally {
    detailLoading.value = false
  }
}

const saveStatus = async () => {
  if (!detail.value) return
  saving.value = true
  try {
    const res: any = await updateIncident(detail.value.id, {
      status: editForm.status,
      resolution_notes: editForm.resolution_notes
    })
    const d = res?.data || res
    if (detail.value) detail.value = { ...detail.value, ...d }
    // 同步列表行
    const idx = list.value.findIndex((i) => i.id === detail.value?.id)
    if (idx >= 0) list.value[idx] = { ...list.value[idx], ...d }
    ElMessage.success('状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.message || '更新失败')
  } finally {
    saving.value = false
  }
}

onMounted(fetchList)
</script>

<style scoped lang="scss">
.incident-page {
  .filter-card {
    margin-bottom: 12px;
  }
  .pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .incident-title {
    font-weight: 500;
  }
  .mono {
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: 12px;
  }
  .desc-pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: inherit;
    font-size: 13px;
    line-height: 1.6;
  }
  .status-flow {
    margin-top: 20px;
    .block-title {
      font-weight: 600;
      margin-bottom: 12px;
      padding-left: 8px;
      border-left: 3px solid var(--el-color-primary);
    }
  }
}
</style>
