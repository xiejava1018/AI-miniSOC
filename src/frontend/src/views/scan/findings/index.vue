<!--
  资产扫描 - 发现清单

  - scanner 发现的设备/端口（与台账解耦，ADR-6）
  - 筛选：finding_status / exposure / IP
  - 单条操作：纳管（adopt）/ 忽略（ignore）/ 解除忽略（unignore）/ 删除（delete）
  - 批量操作：多选 → 忽略/解除忽略/删除
  - adopted 状态不可删除/忽略/解除忽略（已在台账）
-->
<template>
  <div class="findings-page art-full-height">
    <ElCard shadow="never" class="page-card">
      <template #header>
        <div class="card-header">
          <span class="title">发现清单</span>
          <div class="actions">
            <ElSelect
              v-model="filterStatus"
              placeholder="全部状态"
              clearable
              style="width: 120px"
              @change="reload"
            >
              <ElOption label="待处置(new)" value="new" />
              <ElOption label="已知(known)" value="known" />
              <ElOption label="已纳管" value="adopted" />
              <ElOption label="已忽略" value="ignored" />
            </ElSelect>
            <ElSelect
              v-model="filterExposure"
              placeholder="全部暴露面"
              clearable
              style="width: 120px"
              @change="reload"
            >
              <ElOption label="内网 internal" value="internal" />
              <ElOption label="公网 public" value="public" />
            </ElSelect>
            <ElInput
              v-model="filterIp"
              placeholder="按 IP 筛选"
              clearable
              style="width: 160px"
              @keyup.enter="reload"
              @clear="reload"
            />
            <ElButton type="primary" @click="reload">查询</ElButton>
          </div>
        </div>
      </template>

      <ElAlert
        type="info"
        :closable="false"
        show-icon
        class="hint"
        title="扫描发现不直接进入资产台账"
        description="确认归属后点「一键纳管」写入台账并记录审计；确认为噪音/非自有资产点「忽略」。已纳管发现不可删除/忽略/解禁。"
      />

      <!-- 批量操作栏（仅选中时显示） -->
      <div v-if="selectedRows.length" class="bulk-bar">
        <span class="bulk-info">已选 <b>{{ selectedRows.length }}</b> 条</span>
        <ElButton
          type="info"
          size="small"
          :disabled="!canBulkIgnore"
          @click="bulkIgnore"
        >
          批量忽略 ({{ selectedRows.length }})
        </ElButton>
        <ElButton
          type="warning"
          size="small"
          :disabled="!canBulkUnignore"
          @click="bulkUnignore"
        >
          批量解禁 ({{ selectedRows.length }})
        </ElButton>
        <ElButton
          type="danger"
          size="small"
          :disabled="!canBulkDelete"
          @click="bulkDelete"
        >
          批量删除 ({{ selectedRows.length }})
        </ElButton>
        <ElButton link size="small" @click="clearSelection">清空选择</ElButton>
      </div>

      <ElTable
        ref="tableRef"
        v-loading="loading"
        :data="findings"
        stripe
        style="width: 100%"
        @selection-change="onSelectionChange"
      >
        <ElTableColumn type="selection" width="50" :selectable="row => row.finding_status !== 'adopted'" />
        <ElTableColumn prop="asset_ip" label="IP" min-width="130" />
        <ElTableColumn label="暴露面" width="90">
          <template #default="{ row }">
            <ElTag size="small" :type="row.exposure === 'public' ? 'danger' : 'info'">
              {{ row.exposure === 'public' ? '公网' : '内网' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="mac_address" label="MAC" min-width="150">
          <template #default="{ row }">{{ row.mac_address || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn prop="os_guess" label="系统猜测" min-width="140">
          <template #default="{ row }">{{ row.os_guess || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn label="状态" width="100">
          <template #default="{ row }">
            <ElTag :type="findingStatusType(row.finding_status)" size="small">
              {{ findingStatusLabel(row.finding_status) }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="匹配台账" min-width="140">
          <template #default="{ row }">
            <span v-if="row.matched_asset_id" class="mono">
              {{ row.matched_asset_id.slice(0, 8) }}…
            </span>
            <span v-else class="muted">未匹配</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="首次发现" min-width="160">
          <template #default="{ row }">{{ formatTime(row.first_seen) || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn label="最近发现" min-width="160">
          <template #default="{ row }">{{ formatTime(row.last_seen) || '—' }}</template>
        </ElTableColumn>
        <ElTableColumn
          v-if="hasAuth('scan_finding_manage')"
          label="操作"
          width="260"
          fixed="right"
        >
          <template #default="{ row }">
            <template v-if="['new', 'known'].includes(row.finding_status)">
              <ElButton link type="primary" size="small" @click="openAdopt(row)">纳管</ElButton>
              <ElPopconfirm title="确认忽略该发现？" @confirm="ignore(row)">
                <template #reference>
                  <ElButton link type="info" size="small">忽略</ElButton>
                </template>
              </ElPopconfirm>
            </template>
            <ElPopconfirm
              v-if="row.finding_status === 'ignored'"
              title="解除忽略？恢复为待处置/已知。"
              @confirm="unignore(row)"
            >
              <template #reference>
                <ElButton link type="warning" size="small">解禁</ElButton>
              </template>
            </ElPopconfirm>
            <ElPopconfirm
              v-if="row.finding_status !== 'adopted'"
              :title="`删除该发现？${row.asset_ip}`"
              @confirm="remove(row)"
            >
              <template #reference>
                <ElButton link type="danger" size="small">删除</ElButton>
              </template>
            </ElPopconfirm>
            <span v-if="row.finding_status === 'adopted'" class="muted">已纳管</span>
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
          @current-change="loadFindings"
          @size-change="loadFindings"
        />
      </div>
    </ElCard>

    <!-- 纳管弹窗 -->
    <ElDialog v-model="adoptVisible" title="一键纳管为资产" width="520px">
      <ElAlert
        type="warning"
        :closable="false"
        show-icon
        class="adopt-alert"
        :title="`将把 ${adoptTarget?.asset_ip} 写入资产台账`"
      />
      <ElForm :model="adoptForm" label-width="100px">
        <ElFormItem label="资产名称">
          <ElInput v-model="adoptForm.asset_name" placeholder="留空则用系统猜测或 IP" />
        </ElFormItem>
        <ElFormItem label="重要性">
          <ElSelect v-model="adoptForm.criticality" style="width:100%">
            <ElOption label="高 critical" value="critical" />
            <ElOption label="中 medium" value="medium" />
            <ElOption label="低 low" value="low" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="负责人">
          <ElInput v-model="adoptForm.owner" placeholder="如 ops-team" />
        </ElFormItem>
        <ElFormItem label="业务组">
          <ElInput v-model="adoptForm.business_unit" placeholder="如 ops" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="adoptVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="adopting" @click="submitAdopt">确认纳管</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useAuth } from '@/hooks/core/useAuth'
  import {
    getScanFindings,
    adoptFinding,
    ignoreFinding,
    unignoreFinding,
    deleteFinding,
    bulkActionFindings,
    type ScanFinding
  } from '@/api/scan'

  defineOptions({ name: 'ScanFindings' })

  const { hasAuth } = useAuth()

  const findings = ref<ScanFinding[]>([])
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const filterStatus = ref('')
  const filterExposure = ref('')
  const filterIp = ref('')

  // 批量选择
  const tableRef = ref()
  const selectedRows = ref<ScanFinding[]>([])
  const onSelectionChange = (rows: ScanFinding[]) => {
    selectedRows.value = rows
  }
  const clearSelection = () => {
    tableRef.value?.clearSelection()
    selectedRows.value = []
  }

  // 批量按钮可用性：忽略只能对 new/known 操作；解禁只能对 ignored；删除只能对非 adopted
  const canBulkIgnore = computed(() =>
    selectedRows.value.some(r => ['new', 'known'].includes(r.finding_status))
  )
  const canBulkUnignore = computed(() =>
    selectedRows.value.some(r => r.finding_status === 'ignored')
  )
  const canBulkDelete = computed(() =>
    selectedRows.value.some(r => r.finding_status !== 'adopted')
  )

  const adoptVisible = ref(false)
  const adopting = ref(false)
  const adoptTarget = ref<ScanFinding | null>(null)
  const adoptForm = ref({
    asset_name: '',
    criticality: 'medium',
    owner: '',
    business_unit: ''
  })

  const findingStatusType = (s: string) =>
    ({ new: 'warning', known: 'info', adopted: 'success', ignored: 'info' }[s] || 'info')
  const findingStatusLabel = (s: string) =>
    ({ new: '待处置', known: '已知', adopted: '已纳管', ignored: '已忽略' }[s] || s)

  const formatTime = (t?: string | null) => {
    if (!t) return ''
    try {
      return new Date(t).toLocaleString('zh-CN', { hour12: false })
    } catch {
      return t
    }
  }

  const loadFindings = async () => {
    loading.value = true
    try {
      const res = await getScanFindings({
        status: (filterStatus.value || undefined) as any,
        exposure: (filterExposure.value || undefined) as any,
        asset_ip: filterIp.value.trim() || undefined,
        skip: (page.value - 1) * pageSize.value,
        limit: pageSize.value
      })
      findings.value = res.items || []
      total.value = res.total || 0
      clearSelection()
    } catch (e: any) {
      ElMessage.error(e?.message || '加载发现失败')
    } finally {
      loading.value = false
    }
  }

  const reload = () => {
    page.value = 1
    loadFindings()
  }

  const openAdopt = (row: ScanFinding) => {
    adoptTarget.value = row
    adoptForm.value = {
      asset_name: row.os_guess ? `${row.os_guess}-${row.asset_ip}` : '',
      criticality: 'medium',
      owner: '',
      business_unit: ''
    }
    adoptVisible.value = true
  }

  const submitAdopt = async () => {
    if (!adoptTarget.value) return
    adopting.value = true
    try {
      const res = await adoptFinding(adoptTarget.value.id, {
        asset_name: adoptForm.value.asset_name.trim() || undefined,
        criticality: adoptForm.value.criticality,
        owner: adoptForm.value.owner.trim() || undefined,
        business_unit: adoptForm.value.business_unit.trim() || undefined
      })
      ElMessage.success(`已纳管，资产 ID ${(res.asset_id || '').slice(0, 8)}…`)
      adoptVisible.value = false
      loadFindings()
    } catch (e: any) {
      ElMessage.error(e?.message || '纳管失败')
    } finally {
      adopting.value = false
    }
  }

  const ignore = async (row: ScanFinding) => {
    try {
      await ignoreFinding(row.id)
      ElMessage.success('已忽略')
      loadFindings()
    } catch (e: any) {
      ElMessage.error(e?.message || '忽略失败')
    }
  }

  const unignore = async (row: ScanFinding) => {
    try {
      await unignoreFinding(row.id)
      ElMessage.success('已解除忽略')
      loadFindings()
    } catch (e: any) {
      ElMessage.error(e?.message || '解禁失败')
    }
  }

  const remove = async (row: ScanFinding) => {
    try {
      await deleteFinding(row.id)
      ElMessage.success('已删除')
      loadFindings()
    } catch (e: any) {
      ElMessage.error(e?.message || '删除失败')
    }
  }

  // ===================== 批量操作 =====================
  // 统一封装：弹确认框 → 调 API → 显示结果摘要 → reload
  const runBulk = async (
    action: 'ignore' | 'unignore' | 'delete',
    confirmMsg: string,
    successMsg: string,
    errMsg: string,
  ) => {
    if (!selectedRows.value.length) return
    try {
      await ElMessageBox.confirm(confirmMsg, '确认批量操作', {
        type: action === 'delete' ? 'warning' : 'info',
        confirmButtonText: '确认',
        cancelButtonText: '取消',
      })
    } catch {
      return  // 用户取消
    }
    const ids = selectedRows.value.map(r => r.id)
    try {
      const res = await bulkActionFindings(action, ids)
      const { succeeded, failed } = res
      const total = res.requested
      if (failed.length === 0) {
        ElMessage.success(`${successMsg}（${succeeded.length}/${total}）`)
      } else {
        // 部分失败：弹 detail 看具体原因
        const preview = failed
          .slice(0, 5)
          .map(f => `#${f.id}: ${f.reason}`)
          .join('\n')
        const more = failed.length > 5 ? `\n… 还有 ${failed.length - 5} 条` : ''
        ElMessageBox.alert(
          `成功 ${succeeded.length}/${total}。失败明细：\n${preview}${more}`,
          errMsg,
          { type: 'warning' },
        )
      }
      loadFindings()
    } catch (e: any) {
      ElMessage.error(e?.message || errMsg)
    }
  }

  const bulkIgnore = () =>
    runBulk('ignore', `忽略选中的 ${selectedRows.value.length} 条发现？`,
            '已忽略', '批量忽略')
  const bulkUnignore = () =>
    runBulk('unignore', `解除选中的 ${selectedRows.value.length} 条忽略？`,
            '已解除忽略', '批量解禁')
  const bulkDelete = () =>
    runBulk('delete', `删除选中的 ${selectedRows.value.length} 条发现（不可恢复）？`,
            '已删除', '批量删除')

  onMounted(loadFindings)
</script>

<style lang="scss" scoped>
  .findings-page {
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
  .hint {
    margin-bottom: 12px;
  }
  .bulk-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    margin-bottom: 12px;
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-5);
    border-radius: 4px;
    .bulk-info {
      font-size: 13px;
      color: var(--el-text-color-regular);
      margin-right: 4px;
      b {
        color: var(--el-color-primary);
        font-weight: 600;
      }
    }
  }
  .mono {
    font-family: monospace;
  }
  .muted {
    color: var(--el-text-color-placeholder);
  }
  .pager {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .adopt-alert {
    margin-bottom: 12px;
  }
</style>
