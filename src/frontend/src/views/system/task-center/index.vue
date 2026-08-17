<!--
  后台任务中心（v0.4.2 Phase 1.7 + Phase 2.4 进度条）

  功能：
  - 上方 6 个 summary 卡片（总数/启用/禁用/运行中/僵尸/连续失败）
  - 任务列表：名称、类型、调度、状态、上次运行、当前进度、连续失败、总执行、操作
  - 操作：手动触发、取消运行、查看历史、启用/禁用
  - 历史抽屉：分页 run 列表、状态、进度、错误堆栈
  - 表头列设置 / 其他设置（与其他系统管理页一致）
-->
<template>
  <div class="task-center-page art-full-height" id="task-center">
    <!-- 顶部统计卡片 -->
    <ElRow :gutter="12" class="summary-row">
      <ElCol :span="4" v-for="card in summaryCards" :key="card.key">
        <ElCard shadow="never" class="summary-card">
          <div class="summary-value" :class="card.cls">{{ card.value }}</div>
          <div class="summary-label">{{ card.label }}</div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 任务列表 -->
    <ElCard shadow="never" class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" @refresh="onManualRefresh">
        <template #left>
          <ElButton @click="onManualRefresh">刷新</ElButton>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="list"
        :columns="columns"
        :layout="{ marginTop: 10 }"
        table-layout="auto"
        :table-config="{ rowKey: 'task_key' }"
        :pagination="pagination"
        @pagination:size-change="onPageSizeChange"
        @pagination:current-change="onPageChange"
      >
        <template #task_name="{ row }">
          <div class="task-name">
            <span class="name">{{ row.task_name }}</span>
            <span class="key">{{ row.task_key }}</span>
          </div>
        </template>
        <template #task_type="{ row }">
          <ElTag size="small" :type="(typeTagMap[row.task_type] as any) || 'info'">
            {{ typeLabelMap[row.task_type] || row.task_type }}
          </ElTag>
        </template>
        <template #enabled="{ row }">
          <ElTag size="small" :type="row.enabled ? 'success' : 'info'">
            {{ row.enabled ? '启用' : '禁用' }}
          </ElTag>
        </template>
        <template #last_run_at="{ row }">
          <div v-if="row.last_run_at" class="last-run">
            <ElTag size="small" :type="(statusTagMap[row.last_status] as any) || 'info'">
              {{ statusLabelMap[row.last_status] || row.last_status }}
            </ElTag>
            <span class="time">{{ formatTime(row.last_run_at) }}</span>
            <span v-if="row.last_duration_ms != null" class="duration">
              {{ (row.last_duration_ms / 1000).toFixed(2) }}s
            </span>
          </div>
          <span v-else class="muted">从未运行</span>
        </template>
        <template #current_run="{ row }">
          <div v-if="row.current_run" class="progress-cell">
            <ElProgress
              :percentage="calcPercent(row.current_run)"
              :stroke-width="10"
              :status="progressStatus(row.current_run)"
              :text-inside="false"
            />
            <div class="progress-meta">
              <span class="stage">{{ stageLabel(row.current_run) }}</span>
              <span class="numbers">{{ progressNumbers(row.current_run) }}</span>
            </div>
          </div>
          <span v-else class="muted">-</span>
        </template>
        <template #consecutive_failures="{ row }">
          <ElTag v-if="row.consecutive_failures > 0" type="danger" size="small">
            {{ row.consecutive_failures }}
          </ElTag>
          <span v-else class="muted">0</span>
        </template>
        <template #action="{ row }">
          <ElButton
            v-if="hasAuth('trigger')"
            size="small"
            type="primary"
            :disabled="!row.enabled || !!row.current_run"
            @click="onTrigger(row)"
          >
            立即执行
          </ElButton>
          <ElButton
            v-if="hasAuth('cancel') && row.current_run"
            size="small"
            type="danger"
            plain
            @click="onCancel(row)"
          >
            取消运行
          </ElButton>
          <ElButton
            v-if="hasAuth('view_runs')"
            size="small"
            @click="onViewRuns(row)"
          >
            历史
          </ElButton>
          <ElButton
            v-if="hasAuth('toggle')"
            size="small"
            :type="row.enabled ? 'warning' : 'success'"
            @click="onToggle(row)"
          >
            {{ row.enabled ? '禁用' : '启用' }}
          </ElButton>
        </template>
      </ArtTable>
    </ElCard>

    <!-- 立即执行对话框 -->
    <ElDialog v-model="triggerDialog.visible" title="手动触发任务" width="480px">
      <ElForm label-width="80px">
        <ElFormItem label="任务">
          <span>{{ triggerDialog.task?.task_name }} ({{ triggerDialog.task?.task_key }})</span>
        </ElFormItem>
        <ElFormItem label="原因" required>
          <ElInput
            v-model="triggerDialog.reason"
            type="textarea"
            :rows="3"
            placeholder="请填写触发原因（≥3 字），将写入审计日志"
            maxlength="500"
            show-word-limit
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="triggerDialog.visible = false">取消</ElButton>
        <ElButton
          type="primary"
          :loading="triggerDialog.loading"
          :disabled="triggerDialog.reason.trim().length < 3"
          @click="confirmTrigger"
        >
          触发
        </ElButton>
      </template>
    </ElDialog>

    <!-- 历史抽屉 -->
    <ElDrawer
      v-model="runsDrawer.visible"
      :title="`执行历史 - ${runsDrawer.task?.task_name || ''}`"
      size="60%"
    >
      <ElTable v-loading="runsDrawer.loading" :data="runsDrawer.list" stripe border>
        <ElTableColumn prop="started_at" label="开始时间" width="170">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="status" label="状态" width="100">
          <template #default="{ row }">
            <ElTag size="small" :type="(statusTagMap[row.status] as any) || 'info'">
              {{ statusLabelMap[row.status] || row.status }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="trigger" label="触发方式" width="90" />
        <ElTableColumn label="耗时" width="90">
          <template #default="{ row }">
            {{ row.duration_ms != null ? (row.duration_ms / 1000).toFixed(2) + 's' : '-' }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="进度" width="160">
          <template #default="{ row }">
            <div v-if="row.processed != null || row.percent != null" class="progress-cell">
              <ElProgress
                :percentage="calcPercent(row)"
                :stroke-width="8"
                :show-text="false"
              />
              <div class="progress-meta">
                <span class="stage">{{ stageLabel(row) }}</span>
                <span class="numbers">{{ progressNumbers(row) }}</span>
              </div>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="主机" prop="host" width="140" />
        <ElTableColumn label="错误" min-width="200">
          <template #default="{ row }">
            <ElText v-if="row.error_text" type="danger" size="small" class="error-text">
              {{ row.error_text }}
            </ElText>
            <span v-else class="muted">-</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pagination-wrap">
        <ElPagination
          v-model:current-page="runsDrawer.page"
          :page-size="runsDrawer.pageSize"
          :total="runsDrawer.total"
          layout="total, prev, pager, next"
          @current-change="loadRuns"
        />
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchTaskList,
  fetchTaskRuns,
  fetchTaskSummary,
  triggerTask,
  toggleTask,
  cancelTaskRun,
  type TaskRegistry,
  type TaskRun,
  type TaskSummary
} from '@/api/taskObservability'
import { useTableColumns } from '@/hooks/core/useTableColumns'
import { useAuth } from '@/hooks/core/useAuth'

// ---------------------------------------------------------------------------
// 权限（脚本级，响应式读取 route.meta.authList，避免 v-auth 指令的 mount 时机问题）

const { hasAuth } = useAuth()

// ---------------------------------------------------------------------------
// 状态映射

const statusLabelMap: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  timeout: '超时',
  skipped: '跳过',
  zombie: '僵尸',
  unknown: '未知'
}

const statusTagMap: Record<string, string> = {
  pending: 'info',
  running: 'warning',
  success: 'success',
  failed: 'danger',
  timeout: 'danger',
  skipped: 'info',
  zombie: 'danger',
  unknown: 'info'
}

const typeLabelMap: Record<string, string> = {
  scheduled: '定时',
  async: '异步',
  thread: '线程',
  watchdog: '看门狗'
}

const typeTagMap: Record<string, string> = {
  scheduled: '',
  async: 'success',
  thread: 'warning',
  watchdog: 'danger'
}

// ---------------------------------------------------------------------------
// 列可见性（与 ArtTableHeader 的列设置/其他设置联动；ArtTable 从 columns 渲染）

const { columns, columnChecks } = useTableColumns<TaskRegistry>(() => [
  { prop: 'task_name', label: '任务', minWidth: 180, useSlot: true },
  { prop: 'task_type', label: '类型', width: 100, useSlot: true },
  { prop: 'schedule_expr', label: '调度', width: 140 },
  { prop: 'enabled', label: '状态', width: 90, useSlot: true },
  { prop: 'last_run_at', label: '上次运行', minWidth: 220, useSlot: true },
  { prop: 'current_run', label: '当前进度', width: 200, useSlot: true },
  { prop: 'consecutive_failures', label: '连续失败', width: 100, useSlot: true },
  { prop: 'total_runs', label: '总执行', width: 90 },
  { prop: 'action', label: '操作', width: 300, fixed: 'right', useSlot: true }
])

// ---------------------------------------------------------------------------
// Summary

const summary = ref<TaskSummary>({
  total_tasks: 0,
  enabled_tasks: 0,
  disabled_tasks: 0,
  running_runs: 0,
  zombie_runs: 0,
  consecutive_failed_tasks: 0,
  queue_size: 0
})

const summaryCards = computed(() => [
  { key: 'total', label: '任务总数', value: summary.value.total_tasks, cls: '' },
  { key: 'enabled', label: '启用中', value: summary.value.enabled_tasks, cls: 'text-success' },
  { key: 'disabled', label: '已禁用', value: summary.value.disabled_tasks, cls: 'text-muted' },
  { key: 'running', label: '运行中', value: summary.value.running_runs, cls: 'text-warning' },
  { key: 'zombie', label: '僵尸任务', value: summary.value.zombie_runs, cls: 'text-danger' },
  { key: 'failed', label: '连续失败', value: summary.value.consecutive_failed_tasks, cls: 'text-danger' }
])

// ---------------------------------------------------------------------------
// 列表（与 ArtTable 控询：使用其期望的 pagination { current, size, total } 形状）

const list = ref<TaskRegistry[]>([])
const loading = ref(false)
const pagination = reactive({
  current: 1,
  size: 50,
  total: 0
})

async function loadList() {
  loading.value = true
  try {
    const res = await fetchTaskList({
      page: pagination.current,
      page_size: pagination.size
    })
    if (res.code === 200 && res.data) {
      list.value = res.data.records
      pagination.total = res.data.total
    }
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  pagination.current = p
  loadList()
}

function onPageSizeChange(s: number) {
  pagination.size = s
  pagination.current = 1
  loadList()
}

async function loadSummary() {
  try {
    const res = await fetchTaskSummary()
    if (res.code === 200 && res.data) {
      summary.value = res.data
    }
  } catch (e) {
    // 静默
  }
}

// 表头手动刷新：同时刷列表 + 统计
function onManualRefresh() {
  loadList()
  loadSummary()
}

// ---------------------------------------------------------------------------
// 触发对话框

const triggerDialog = reactive({
  visible: false,
  loading: false,
  task: null as TaskRegistry | null,
  reason: ''
})

function onTrigger(row: TaskRegistry) {
  triggerDialog.task = row
  triggerDialog.reason = ''
  triggerDialog.visible = true
}

async function confirmTrigger() {
  if (!triggerDialog.task) return
  triggerDialog.loading = true
  try {
    const res = await triggerTask(triggerDialog.task.task_key, triggerDialog.reason.trim())
    if (res.code === 200 || res.code === 202) {
      ElMessage.success(`已触发，run_id=${res.data?.run_id?.slice(0, 8) || ''}`)
      triggerDialog.visible = false
      setTimeout(() => {
        loadList()
        loadSummary()
      }, 1500)
    } else {
      ElMessage.error(res.msg || '触发失败')
    }
  } finally {
    triggerDialog.loading = false
  }
}

// ---------------------------------------------------------------------------
// 取消运行

async function onCancel(row: TaskRegistry) {
  if (!row.current_run) return
  try {
    await ElMessageBox.confirm(
      `确认取消任务“${row.task_name}”当前运行？\n（同步任务会在当前步骤完成后停止，不会强制中断数据库操作）`,
      '取消运行',
      { confirmButtonText: '确认取消', cancelButtonText: '返回', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res = await cancelTaskRun(row.task_key, row.current_run.id)
    if (res.code === 200) {
      ElMessage.success('已标记取消')
      loadList()
      loadSummary()
    } else {
      ElMessage.error(res.msg || '取消失败')
    }
  } catch {
    ElMessage.error('取消失败，请稍后重试')
  }
}

// ---------------------------------------------------------------------------
// 启用/禁用

async function onToggle(row: TaskRegistry) {
  const action = row.enabled ? '禁用' : '启用'
  try {
    const { value } = await ElMessageBox.prompt(
      `确认${action}任务"${row.task_name}"？`,
      action,
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: `请填写${action}原因（≥3 字）`,
        inputValidator: (v: string) => (v && v.trim().length >= 3) || '原因至少 3 个字符'
      }
    )
    const res = await toggleTask(row.task_key, {
      enabled: !row.enabled,
      reason: value
    })
    if (res.code === 200) {
      ElMessage.success(`${action}成功`)
      loadList()
    } else {
      ElMessage.error(res.msg || `${action}失败`)
    }
  } catch {
    // 用户取消
  }
}

// ---------------------------------------------------------------------------
// 历史抽屉

const runsDrawer = reactive({
  visible: false,
  loading: false,
  task: null as TaskRegistry | null,
  list: [] as TaskRun[],
  page: 1,
  pageSize: 20,
  total: 0
})

function onViewRuns(row: TaskRegistry) {
  runsDrawer.task = row
  runsDrawer.page = 1
  runsDrawer.visible = true
  loadRuns()
}

async function loadRuns() {
  if (!runsDrawer.task) return
  runsDrawer.loading = true
  try {
    const res = await fetchTaskRuns(runsDrawer.task.task_key, {
      page: runsDrawer.page,
      page_size: runsDrawer.pageSize
    })
    if (res.code === 200 && res.data) {
      runsDrawer.list = res.data.records
      runsDrawer.total = res.data.total
    }
  } finally {
    runsDrawer.loading = false
  }
}

// ---------------------------------------------------------------------------
// 进度计算（Phase 2.4）

function calcPercent(run: { processed?: number | null; total?: number | null; percent?: number | null }): number {
  if (run.percent != null) return Math.max(0, Math.min(100, run.percent))
  if (run.processed != null && run.total != null && run.total > 0) {
    return Math.min(100, Math.round((run.processed / run.total) * 100))
  }
  return 0
}

function progressNumbers(run: { processed?: number | null; total?: number | null }): string {
  if (run.processed == null) return ''
  if (run.total != null) return `${run.processed}/${run.total}`
  return `${run.processed}`
}

function stageLabel(run: { stats_json?: Record<string, any> | null }): string {
  const stage = run.stats_json?.stage
  const stageMap: Record<string, string> = {
    fetch: '拉取中',
    parse: '解析中',
    baseline: '基线加载',
    evaluate: '规则评估',
    persist: '写入中',
    done: '完成',
    upsert: '写入中',
    enrich: '富化中',
    sync_kev: '同步中',
    snapshot: '快照中',
    cleanup: '清理中',
    generate: '生成中',
    finalize: '收尾中'
  }
  return stage ? (stageMap[stage] || stage) : ''
}

function progressStatus(run: { status?: string }): '' | 'success' | 'warning' | 'exception' {
  if (run.status === 'success') return 'success'
  if (run.status === 'failed' || run.status === 'timeout' || run.status === 'zombie') return 'exception'
  return ''
}

const hasRunning = computed(() =>
  list.value.some((t) => t.current_run && t.current_run.status === 'running')
)

let autoRefreshTimer: any = null
function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
  // 每 5s 检查：有 running 任务才刷 list，否则只刷 summary
  autoRefreshTimer = setInterval(async () => {
    if (hasRunning.value) {
      await loadList()
    }
    await loadSummary()
  }, 5000)
}

// ---------------------------------------------------------------------------
// 工具

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

onMounted(() => {
  loadSummary()
  loadList()
  startAutoRefresh()
})

onUnmounted(() => {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
})
</script>

<style lang="scss" scoped>
.task-center-page {
  padding: 12px;
}

.summary-row {
  margin-bottom: 12px;
}

.summary-card {
  text-align: center;
}

.summary-value {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;

  &.text-success {
    color: var(--el-color-success);
  }
  &.text-warning {
    color: var(--el-color-warning);
  }
  &.text-danger {
    color: var(--el-color-danger);
  }
  &.text-muted {
    color: var(--el-text-color-secondary);
  }
}

.summary-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.art-table-card {
  margin-bottom: 12px;
}

.task-name {
  .name {
    font-weight: 500;
    display: block;
  }
  .key {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    font-family: monospace;
  }
}

.last-run {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;

  .time {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .duration {
    font-size: 12px;
    color: var(--el-color-primary);
  }
}

.muted {
  color: var(--el-text-color-placeholder);
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.error-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.progress-cell {
  width: 100%;
  :deep(.el-progress) {
    margin-bottom: 2px;
  }
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.2;

  .stage {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 70%;
  }
  .numbers {
    font-family: monospace;
    flex-shrink: 0;
  }
}
</style>
