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
        <ElTableColumn label="任务 UUID" min-width="280">
          <template #default="{ row }">
            <span class="mono">{{ row.task_uuid }}</span>
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
        <ElTableColumn label="扫描器" min-width="160">
          <template #default="{ row }">
            <span v-if="row.scanner_name">{{ row.scanner_name }}</span>
            <span v-else-if="row.scanner_id" class="mono">{{ row.scanner_id.slice(0, 8) }}…</span>
            <span v-else-if="row.target_scanner_name">指定 {{ row.target_scanner_name }}</span>
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
        <ElTableColumn v-if="hasAuth('scan_run')" label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" size="small" @click="openDetail(row)">详情</ElButton>
            <ElPopconfirm
              v-if="['pending', 'running'].includes(row.status)"
              title="取消该扫描任务？"
              @confirm="cancel(row)"
            >
              <template #reference>
                <ElButton link type="danger" size="small">取消</ElButton>
              </template>
            </ElPopconfirm>
            <ElPopconfirm
              v-if="['success', 'failed', 'cancelled'].includes(row.status)"
              :title="`删除该扫描任务？${row.task_uuid.slice(0, 8)}… (仅删记录，发现数据保留)`"
              @confirm="remove(row)"
            >
              <template #reference>
                <ElButton link type="danger" size="small">删除</ElButton>
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

    <!-- 任务详情弹窗（F-S3 增强：看到「扫 X / 新 Y / 更 Z / 败 W」对应的具体端口/发现） -->
    <ElDialog
      v-model="detailVisible"
      :title="detailTitle"
      width="800px"
      align-center
      :close-on-click-modal="false"
    >
      <div v-loading="detailLoading">
        <!-- 基本信息 -->
        <ElDescriptions :column="2" border size="small" class="detail-desc">
          <ElDescriptionsItem label="任务 UUID">
            <span class="mono">{{ detail?.task_uuid }}</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="状态">
            <ElTag :type="statusType(detail?.status)" size="small">
              {{ statusLabel(detail?.status) }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="类型">
            <ElTag size="small" effect="plain">{{ modeLabel(detail?.mode) }}</ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="范围">{{ detail?.scope || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="分配方式">{{ detail?.assign_mode || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="实际扫描器">
            <span v-if="detail?.scanner_name">{{ detail.scanner_name }}</span>
            <span v-else-if="detail?.scanner_id" class="mono">{{ detail.scanner_id.slice(0, 8) }}…</span>
            <span v-else class="muted">未认领</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="触发人">{{ detail?.triggered_by || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="触发原因">{{ detail?.run_reason || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="开始时间">{{ formatTime(detail?.started_at) || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="结束时间">{{ formatTime(detail?.finished_at) || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="耗时" :span="2">{{ formatDuration(detail?.duration_ms) }}</ElDescriptionsItem>
          <ElDescriptionsItem label="目标">
            <span v-if="detail?.target_summary?.length">
              <span v-for="(t, i) in detail.target_summary" :key="i" class="target-chip">
                {{ t.value }}
              </span>
            </span>
            <span v-else class="muted">—</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="扫描统计">
            扫 {{ detail?.items_scanned ?? 0 }} / 新 {{ detail?.items_created ?? 0 }} /
            更 {{ detail?.items_updated ?? 0 }} / 败 {{ detail?.items_failed ?? 0 }}
          </ElDescriptionsItem>
          <ElDescriptionsItem v-if="detail?.error_message" label="错误" :span="2">
            <span class="err-text">{{ detail.error_message }}</span>
          </ElDescriptionsItem>
        </ElDescriptions>

        <!-- 明细 Tabs（按 mode 选不同明细） -->
        <ElTabs v-model="detailTab" class="detail-tabs">
          <ElTabPane
            v-if="detail?.mode === 'ports' || detail?.mode === 'public'"
            :label="`端口明细 (${detail?.affected_ports?.length ?? 0})`"
            name="ports"
          >
            <div v-if="!detail?.affected_ports?.length" class="empty-tip">
              本次任务未产生端口明细（可能仍在执行、推送来源非 scanner，或任务未完成）
            </div>
            <ElTable v-else :data="detail.affected_ports" stripe size="small" max-height="380">
              <ElTableColumn label="动作" width="80">
                <template #default="{ row }">
                  <ElTag :type="row.action === 'created' ? 'success' : 'warning'" size="small" effect="plain">
                    {{ row.action === 'created' ? '新增' : '更新' }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="IP" prop="ip" width="140" />
              <ElTableColumn label="端口" width="80" align="center">
                <template #default="{ row }">{{ row.port }}</template>
              </ElTableColumn>
              <ElTableColumn label="协议" prop="protocol" width="80" align="center" />
              <ElTableColumn label="服务" prop="service" width="120" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.service">{{ row.service }}</span>
                  <span v-else class="muted">—</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="版本" prop="version" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.version">{{ row.version }}</span>
                  <span v-else class="muted">—</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="ID" width="120">
                <template #default="{ row }">
                  <span class="mono">{{ row.id.slice(0, 8) }}…</span>
                </template>
              </ElTableColumn>
            </ElTable>
          </ElTabPane>
          <ElTabPane
            v-if="detail?.mode === 'internal' || detail?.mode === 'public'"
            :label="`发现明细 (${detail?.affected_findings?.length ?? 0})`"
            name="findings"
          >
            <div v-if="!detail?.affected_findings?.length" class="empty-tip">
              本次任务未产生发现明细（可能仍在执行、推送来源非 scanner，或任务未完成）
            </div>
            <ElTable v-else :data="detail.affected_findings" stripe size="small" max-height="380">
              <ElTableColumn label="动作" width="80">
                <template #default="{ row }">
                  <ElTag :type="row.action === 'created' ? 'success' : 'warning'" size="small" effect="plain">
                    {{ row.action === 'created' ? '新增' : '更新' }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="IP" prop="ip" width="140" />
              <ElTableColumn label="MAC" prop="mac" width="160" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.mac">{{ row.mac }}</span>
                  <span v-else class="muted">—</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="OS 推测" prop="os_guess" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.os_guess">{{ row.os_guess }}</span>
                  <span v-else class="muted">—</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="暴露面" prop="exposure" width="90" />
              <ElTableColumn label="发现状态" width="100">
                <template #default="{ row }">
                  <ElTag size="small" effect="plain">{{ row.finding_status }}</ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="关联资产" width="280" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.matched_asset_id" class="mono">{{ row.matched_asset_id.slice(0, 8) }}…</span>
                  <span v-else class="muted">未纳管</span>
                </template>
              </ElTableColumn>
            </ElTable>
          </ElTabPane>
        </ElTabs>
      </div>
    </ElDialog>

    <!-- 触发扫描弹窗 -->
    <ElDialog v-model="runVisible" title="触发扫描" width="560px">
      <ElForm :model="runForm" label-width="110px">
        <ElFormItem label="扫描类型" required>
          <ElRadioGroup v-model="runForm.mode" class="mode-group">
            <div class="mode-option" :class="{ active: runForm.mode === 'public' }">
              <ElRadio value="public">公网暴露面</ElRadio>
            </div>
            <div class="mode-option" :class="{ active: runForm.mode === 'internal' }">
              <ElRadio value="internal">内网发现</ElRadio>
            </div>
            <div class="mode-option" :class="{ active: runForm.mode === 'ports' }">
              <ElRadio value="ports">端口扫描</ElRadio>
            </div>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem label="目标">
          <!-- 公网模式：只能从台账登记了公网 IP 的资产里选，不允许随意输入 -->
          <template v-if="runForm.mode === 'public'">
            <ElSelect
              v-model="runForm.publicTargets"
              multiple
              filterable
              placeholder="从台账公网资产中选择（未登记公网IP的资产不会出现）"
              style="width: 100%"
              :loading="publicAssetsLoading"
            >
              <ElOption
                v-for="a in publicAssetOptions"
                :key="a.value"
                :label="a.label"
                :value="a.value"
              />
            </ElSelect>
            <div class="form-hint">
              可选范围＝资产台账中登记了「公网IP」的资产；若要新增目标，请先在资产管理里补录公网 IP。
            </div>
          </template>
          <ElInput
            v-else
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
  import { ref, computed, watch, onMounted } from 'vue'
  import { ElMessage } from 'element-plus'
  import { useAuth } from '@/hooks/core/useAuth'
  import { getAssetList } from '@/api/asset'
  import {
    getScanTasks,
    runScan,
    cancelScanTask,
    deleteScanTask,
    getScanTask,
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
    publicTargets: [] as string[],
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

  // 公网模式可选目标：台账中登记了公网 IP 的资产
  const publicAssetOptions = ref<{ label: string; value: string }[]>([])
  const publicAssetsLoading = ref(false)
  const loadPublicAssets = async () => {
    if (publicAssetOptions.value.length || publicAssetsLoading.value) return
    publicAssetsLoading.value = true
    try {
      const res: any = await getAssetList({ page: 1, pageSize: 500 })
      const rows = res?.data?.records || res?.data?.list || res?.data?.items || []
      publicAssetOptions.value = rows
        .filter((a: any) => a.public_ip)
        .map((a: any) => ({
          label: `${a.public_ip}（${a.name || a.asset_ip}）`,
          value: a.public_ip
        }))
    } catch {
      publicAssetOptions.value = []
    } finally {
      publicAssetsLoading.value = false
    }
  }
  watch(
    () => runForm.value.mode,
    (m) => {
      if (m === 'public') loadPublicAssets()
    }
  )

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
    if (runForm.value.mode === 'public') loadPublicAssets()
  }

  const submitRun = async () => {
    // 公网模式：目标只能来自台账公网资产多选
    const targets =
      runForm.value.mode === 'public'
        ? runForm.value.publicTargets.join(',')
        : runForm.value.targets.trim()
    if (runForm.value.mode === 'public' && !targets) {
      ElMessage.warning('请至少选择一个台账公网资产')
      return
    }
    running.value = true
    try {
      await runScan({
        mode: runForm.value.mode,
        targets: targets || undefined,
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

  const remove = async (row: ScanTask) => {
    try {
      await deleteScanTask(row.task_uuid)
      ElMessage.success('任务已删除（发现数据保留）')
      loadTasks()
    } catch (e: any) {
      ElMessage.error(e?.message || '删除失败')
    }
  }

  // ===================== 任务详情（F-S3） =====================
  const detailVisible = ref(false)
  const detailLoading = ref(false)
  const detail = ref<ScanTask | null>(null)
  const detailTab = ref('ports')
  const detailTitle = computed(() => {
    if (!detail.value) return '任务详情'
    const id8 = detail.value.task_uuid.slice(0, 8)
    return `任务详情 ${id8}…  · ${modeLabel(detail.value.mode)}  ·  ${statusLabel(detail.value.status)}`
  })
  const openDetail = async (row: ScanTask) => {
    detail.value = row  // 先用列表行的粗略数据
    detailVisible.value = true
    detailLoading.value = true
    // 默认 Tab：discovery / public / internal 看发现；ports 看端口
    detailTab.value = row.mode === 'ports' ? 'ports' : 'findings'
    try {
      const full = await getScanTask(row.task_uuid)
      detail.value = full
    } catch (e: any) {
      ElMessage.error(e?.message || '加载详情失败')
    } finally {
      detailLoading.value = false
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

  /* F-S3：任务详情弹窗 */
  .detail-desc {
    margin-bottom: 16px;
  }
  .detail-desc :deep(.el-descriptions__label) {
    width: 90px;
    color: var(--el-text-color-secondary);
  }
  .detail-tabs {
    margin-top: 4px;
  }
  .target-chip {
    display: inline-block;
    margin-right: 6px;
    padding: 1px 6px;
    background: var(--el-fill-color-light);
    border-radius: 3px;
    font-family: monospace;
    font-size: 12px;
  }
  .empty-tip {
    padding: 24px;
    text-align: center;
    color: var(--el-text-color-secondary);
    font-size: 13px;
    background: var(--el-fill-color-blank);
    border: 1px dashed var(--el-border-color);
    border-radius: 4px;
  }
  .err-text {
    color: var(--el-color-danger);
    font-family: monospace;
    font-size: 12px;
    word-break: break-all;
  }

  /* P4-D: 扫描类型卡片化 */
  .mode-group {
    display: flex;
    flex-direction: row;
    gap: 8px;
    width: 100%;
  }
  .mode-group :deep(.el-radio) {
    margin-right: 0;
  }
  .mode-group :deep(.el-radio__input) {
    margin-right: 6px;
  }
  .mode-option {
    flex: 1;
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
    padding: 6px 10px;
    background: var(--el-fill-color-blank);
    transition: border-color 0.15s;
    text-align: center;
  }
  .mode-option.active {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
  .mode-option :deep(.el-radio) {
    margin-right: 6px;
    height: auto;
  }
</style>
