<!--
  资产扫描 - 扫描任务

  - 任务列表（状态/类型/扫描器/时间/耗时/扫描项统计）
  - 触发扫描弹窗（mode + targets + 分配方式 + nmap 参数）
  - 取消 pending/running 任务
  - 查看失败原因
-->
<template>
  <div class="tasks-page art-full-height">
    <ElCard shadow="never" class="page-card">
      <template #header>
        <div class="card-header">
          <span class="title">扫描任务</span>
          <div class="actions">
            <ElSelect
              v-model="filterStatus"
              placeholder="全部状态"
              clearable
              style="width: 130px"
              @change="reload"
            >
              <ElOption v-for="s in STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
            </ElSelect>
            <ElButton :loading="loading" @click="reload">刷新</ElButton>
            <ElButton v-if="hasAuth('scan_run')" type="primary" @click="openRun">触发扫描</ElButton>
          </div>
        </div>
      </template>

      <ElTable v-loading="loading" :data="tasks" stripe style="width: 100%">
        <ElTableColumn label="任务 UUID" min-width="220">
          <template #default="{ row }">
            <span class="mono">{{ row.task_uuid.slice(0, 8) }}…</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="类型" width="100">
          <template #default="{ row }">
            <ElTag size="small" effect="plain">{{ modeLabel(row.mode) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="范围" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.scope || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="100">
          <template #default="{ row }">
            <ElTag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="扫描器" min-width="150">
          <template #default="{ row }">
            <span v-if="row.scanner_id" class="mono">{{ row.scanner_id.slice(0, 8) }}…</span>
            <span v-else-if="row.target_scanner_id" class="muted">
              指定 {{ row.target_scanner_id.slice(0, 8) }}…
            </span>
            <span v-else class="muted">自动分配</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="扫描项" min-width="150">
          <template #default="{ row }">
            <span v-if="row.status === 'pending' || row.status === 'running'" class="muted">—</span>
            <span v-else>
              <ElTooltip v-if="row.error_message" :content="row.error_message" placement="top">
                <span class="err-hint">
                  扫 {{ row.items_scanned ?? 0 }} / 新 {{ row.items_created ?? 0 }} / 更
                  {{ row.items_updated ?? 0 }} / 败 {{ row.items_failed ?? 0 }}
                </span>
              </ElTooltip>
              <span v-else>
                扫 {{ row.items_scanned ?? 0 }} / 新 {{ row.items_created ?? 0 }} / 更
                {{ row.items_updated ?? 0 }} / 败 {{ row.items_failed ?? 0 }}
              </span>
            </span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="耗时" width="90">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </ElTableColumn>
        <ElTableColumn label="开始时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.started_at) || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn v-if="hasAuth('scan_run')" label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <ElPopconfirm
              v-if="['pending', 'running'].includes(row.status)"
              title="取消该扫描任务？"
              @confirm="cancel(row)"
            >
              <template #reference>
                <ElButton link type="danger" size="small">取消</ElButton>
              </template>
            </ElPopconfirm>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadTasks"
          @size-change="loadTasks"
        />
      </div>
    </ElCard>

    <!-- 触发扫描弹窗 -->
    <ElDialog v-model="runVisible" title="触发扫描" width="560px">
      <ElForm :model="runForm" label-width="110px">
        <ElFormItem label="扫描类型" required>
          <ElRadioGroup v-model="runForm.mode" class="mode-group">
            <div class="mode-option" :class="{ active: runForm.mode === 'public' }">
              <ElRadio value="public">公网暴露面</ElRadio>
              <div class="mode-desc">台账 <code>exposure_level=public</code> 资产 → nmap <code>-sV -Pn --top-ports 1000</code> → 落库 <code>soc_asset_ports</code></div>
            </div>
            <div class="mode-option" :class="{ active: runForm.mode === 'internal' }">
              <ElRadio value="internal">内网发现</ElRadio>
              <div class="mode-desc"><b>必须填 CIDR</b>（如 <code>192.168.0.0/24</code>）→ nmap <code>-sn</code> 主机发现 → 落库 <code>soc_scan_findings</code>（需一键纳管才入台账）</div>
            </div>
            <div class="mode-option" :class="{ active: runForm.mode === 'ports' }">
              <ElRadio value="ports">端口扫描</ElRadio>
              <div class="mode-desc">对指定 IP 扫端口 → nmap <code>-sV -Pn --top-ports 1000</code> → 落库 <code>soc_asset_ports</code>（当前与 public 同实现，P4-B 加 NSE 漏洞脚本）</div>
            </div>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem label="目标">
          <ElInput
            v-model="runForm.targets"
            type="textarea"
            :rows="2"
            :placeholder="targetsPlaceholder"
          />
          <div v-if="targetEstimate" class="form-hint" :class="{ warn: targetEstimate.warn && !targetEstimate.error, error: targetEstimate.error }">
            <template v-if="targetEstimate.error">⚠️ {{ targetEstimate.error }}</template>
            <template v-else>
              预估扫描主机数：<b>{{ targetEstimate.hosts }}</b>
              <span v-if="targetEstimate.warn" class="warn-tag">（较大，建议确认耗时）</span>
            </template>
          </div>
          <div class="form-hint">提示：逗号分隔 IP 或 CIDR；CIDR 前缀范围 /16–/22，单 IP 不限。</div>
        </ElFormItem>
        <ElFormItem label="分配方式">
          <ElRadioGroup v-model="runForm.assign_mode">
            <ElRadio value="auto">自动分配</ElRadio>
            <ElRadio value="pinned">指定扫描器</ElRadio>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem v-if="runForm.assign_mode === 'pinned'" label="扫描器">
          <ElSelect v-model="runForm.target_scanner_id" placeholder="选择在线扫描器" style="width:100%">
            <ElOption
              v-for="a in onlineAgents"
              :key="a.scanner_id"
              :label="`${a.name} (${a.ip || a.scanner_id.slice(0, 8)})`"
              :value="a.scanner_id"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="nmap 参数">
          <ElInput v-model="runForm.nmap_args" placeholder="留空用默认；如 -sV -Pn --top-ports 1000" />
        </ElFormItem>
        <ElFormItem label="完成通知">
          <ElSwitch v-model="runForm.notify" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="runVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="running" @click="submitRun">建任务</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { ElMessage } from 'element-plus'
  import { useAuth } from '@/hooks/core/useAuth'
  import {
    getScanTasks,
    runScan,
    cancelScanTask,
    getScannerAgents,
    type ScanTask,
    type ScanMode
  } from '@/api/scan'

  defineOptions({ name: 'ScanTasks' })

  const { hasAuth } = useAuth()

  const tasks = ref<ScanTask[]>([])
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const filterStatus = ref('')

  const runVisible = ref(false)
  const running = ref(false)
  const runForm = ref({
    mode: 'public' as ScanMode,
    targets: '',
    assign_mode: 'auto',
    target_scanner_id: null as string | null,
    nmap_args: '',
    notify: true
  })

  // P4-D: 扫描类型 → 目标 placeholder 提示
  const targetsPlaceholder = computed(() => {
    switch (runForm.value.mode) {
      case 'internal':
        return 'CIDR 网段，必填。如 192.168.0.0/24（可多个，逗号分隔）'
      case 'public':
        return '公网资产 IP 或 CIDR。如 203.0.113.10 或 198.51.100.0/24'
      case 'ports':
        return '目标 IP，逗号分隔。如 192.168.0.1,192.168.0.8 或 192.168.0.0/28'
      default:
        return '逗号分隔 IP 或 CIDR'
    }
  })

  // P4-E: 实时计算输入 targets 的预估主机数
  type TargetEstimate = {
    hosts: number
    warn: boolean  // 主机数 > 256 视为较大
    error: string | null
  }
  const targetEstimate = computed<TargetEstimate | null>(() => {
    const raw = runForm.value.targets.trim()
    if (!raw) return null
    const items = raw.split(',').map(s => s.trim()).filter(Boolean)
    if (items.length === 0) return null

    let total = 0
    let firstError: string | null = null
    for (const it of items) {
      if (it.includes('/')) {
        // CIDR：用 /24 /28 /30 等长度估算（不展开 IP，只按位长计算）
        const m = it.match(/^([0-9.]+)\/(\d+)$/)
        if (!m) { firstError = firstError || `非法 CIDR: ${it}`; continue }
        const prefix = parseInt(m[2])
        if (prefix < 0 || prefix > 32) { firstError = firstError || `前缀越界: ${it}`; continue }
        total += Math.pow(2, 32 - prefix)
      } else {
        // 单 IP：1 台
        total += 1
      }
    }
    return {
      hosts: total,
      warn: total > 256,
      error: firstError,
    }
  })

  const onlineAgents = ref<any[]>([])

  const STATUS_OPTIONS = [
    { value: 'pending', label: '待认领' },
    { value: 'running', label: '扫描中' },
    { value: 'success', label: '成功' },
    { value: 'failed', label: '失败' },
    { value: 'cancelled', label: '已取消' }
  ]

  const statusType = (s: string) =>
    ({ success: 'success', running: 'warning', pending: 'info', failed: 'danger', cancelled: 'info' }[
      s
    ] || 'info')
  const statusLabel = (s: string) =>
    ({
      pending: '待认领',
      running: '扫描中',
      success: '成功',
      failed: '失败',
      cancelled: '已取消'
    }[s] || s)
  const modeLabel = (m: string) =>
    ({ public: '公网', internal: '内网', ports: '端口' }[m] || m)

  const formatTime = (t?: string | null) => {
    if (!t) return ''
    try {
      return new Date(t).toLocaleString('zh-CN', { hour12: false })
    } catch {
      return t
    }
  }
  const formatDuration = (ms?: number | null) => {
    if (!ms && ms !== 0) return '—'
    if (ms < 1000) return `${ms}ms`
    const s = ms / 1000
    if (s < 60) return `${s.toFixed(1)}s`
    return `${Math.floor(s / 60)}m${Math.round(s % 60)}s`
  }

  const loadTasks = async () => {
    loading.value = true
    try {
      const res = await getScanTasks({
        status: (filterStatus.value || undefined) as any,
        skip: (page.value - 1) * pageSize.value,
        limit: pageSize.value
      })
      tasks.value = res.items || []
      total.value = res.total || 0
    } catch (e: any) {
      ElMessage.error(e?.message || '加载任务失败')
    } finally {
      loading.value = false
    }
  }

  const reload = () => {
    page.value = 1
    loadTasks()
  }

  const openRun = async () => {
    runForm.value = {
      mode: 'public',
      targets: '',
      assign_mode: 'auto',
      target_scanner_id: null,
      nmap_args: '',
      notify: true
    }
    try {
      const res = await getScannerAgents()
      onlineAgents.value = (res.items || []).filter((a) => a.enabled && a.status === 'online')
    } catch {
      onlineAgents.value = []
    }
    runVisible.value = true
  }

  const submitRun = async () => {
    running.value = true
    try {
      await runScan({
        mode: runForm.value.mode,
        targets: runForm.value.targets.trim() || undefined,
        assign_mode: runForm.value.assign_mode as any,
        target_scanner_id:
          runForm.value.assign_mode === 'pinned' ? runForm.value.target_scanner_id : null,
        nmap_args: runForm.value.nmap_args.trim() || null,
        notify: runForm.value.notify
      })
      ElMessage.success('扫描任务已创建，等待扫描器认领')
      runVisible.value = false
      reload()
    } catch (e: any) {
      ElMessage.error(e?.message || '创建任务失败')
    } finally {
      running.value = false
    }
  }

  const cancel = async (row: ScanTask) => {
    try {
      await cancelScanTask(row.task_uuid)
      ElMessage.success('已取消')
      loadTasks()
    } catch (e: any) {
      ElMessage.error(e?.message || '取消失败')
    }
  }

  onMounted(loadTasks)
</script>

<style lang="scss" scoped>
  .tasks-page {
    padding: 12px;
  }
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    .title {
      font-weight: 600;
      font-size: 15px;
    }
    .actions {
      display: flex;
      gap: 8px;
    }
  }
  .mono {
    font-family: monospace;
  }
  .muted {
    color: var(--el-text-color-placeholder);
  }
  .err-hint {
    color: var(--el-color-danger);
    border-bottom: 1px dashed var(--el-color-danger);
    cursor: help;
  }
  .pager {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .form-hint {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
    margin-top: 4px;
  }
  .form-hint.warn {
    color: var(--el-color-warning);
  }
  .form-hint.error {
    color: var(--el-color-danger);
  }
  .warn-tag {
    margin-left: 4px;
    color: var(--el-color-warning);
  }

  /* P4-D: 扫描类型卡片化 */
  .mode-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
  }
  .mode-group :deep(.el-radio) {
    margin-right: 0;
  }
  .mode-group :deep(.el-radio__input) {
    margin-right: 6px;
  }
  .mode-option {
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
    padding: 6px 10px;
    background: var(--el-fill-color-blank);
    transition: border-color 0.15s;
  }
  .mode-option.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
  .mode-option :deep(.el-radio) {
    margin-right: 6px;
    height: auto;
  }
  .mode-desc {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.5;
    margin-top: 2px;
    margin-left: 22px;
  }
  .mode-desc code {
    background: var(--el-fill-color-light);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11px;
    color: var(--el-color-primary);
    margin: 0 2px;
  }
  .mode-desc b {
    color: var(--el-color-danger);
  }
</style>
