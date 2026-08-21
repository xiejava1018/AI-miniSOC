<!--
  资产对账（P3/F1.3）

  设计要点，都是 PRD 的硬要求：
  - 数据新鲜度横幅置顶。源异常时先告诉用户"结果可能不全"，
    绝不在数据不可信时让人以为台账是干净的
  - 判定结论来自规则引擎，页面标注「规则判定」；AI 只出现在报告卡里
  - 处理动作走状态机，已处理的行不再提供操作入口（后端也会拒绝，前端只是少一次往返）
-->
<template>
  <div class="recon-page art-full-height">
    <!-- 数据可信度横幅：degraded 时必须显示 -->
    <ElAlert
      v-if="freshness?.degraded"
      type="warning"
      :closable="false"
      show-icon
      class="freshness-alert"
    >
      <template #title>源异常中，结果可能不全</template>
      <div class="freshness-detail">
        <span v-if="freshness.wazuh_reachable === false" class="fr-item">
          Wazuh 不可达{{ freshness.wazuh_error ? `（${freshness.wazuh_error}）` : '' }}
        </span>
        <span v-if="freshness.sync_stale" class="fr-item">
          台账同步不新鲜（最近成功：{{ formatTime(freshness.last_sync_at) || '无记录' }}）
        </span>
        <span v-if="freshness.unhealthy_sources?.length" class="fr-item">
          {{ freshness.unhealthy_sources.length }} 个数据源异常：
          {{ freshness.unhealthy_sources.map((s) => s.source_key).join('、') }}
        </span>
        <span v-if="freshness.dead_letter_pending" class="fr-item">
          {{ freshness.dead_letter_pending }} 条同步死信待处理
        </span>
        <ElButton text type="primary" size="small" @click="goDataHealth"> 查看数据健康 → </ElButton>
      </div>
    </ElAlert>

    <!-- 摘要 -->
    <ElCard shadow="never" class="summary-card">
      <div v-if="!summary?.has_data" class="empty-run">
        <ElEmpty description="尚未执行过对账">
          <ElButton
            v-if="hasAuth('reconcile')"
            type="primary"
            :loading="running"
            @click="handleRun"
          >
            立即对账
          </ElButton>
        </ElEmpty>
      </div>
      <template v-else>
        <div class="summary-head">
          <div class="summary-title">
            <span class="t">资产对账</span>
            <ElTag size="small" effect="plain">规则判定</ElTag>
            <span class="meta">
              {{ formatTime(summary.checked_at) }} · 共 {{ summary.diff_total }} 项差异 · 待处理
              {{ summary.pending_total }} 项
            </span>
          </div>
          <div class="summary-actions">
            <ElButton
              v-if="hasAuth('reconcile')"
              type="primary"
              :loading="running"
              @click="handleRun"
            >
              重新对账
            </ElButton>
            <ElButton v-if="hasAuth('report')" :loading="reporting" @click="handleReport">
              AI 对账报告
            </ElButton>
          </div>
        </div>

        <ElRow :gutter="12" class="stat-row">
          <ElCol :xs="12" :sm="6">
            <div class="stat-box clickable" @click="filterByType('shadow')">
              <div class="stat-label">影子资产</div>
              <div class="stat-value danger">{{ summary.by_type?.shadow || 0 }}</div>
              <div class="stat-sub">Wazuh 有、台账无</div>
            </div>
          </ElCol>
          <ElCol :xs="12" :sm="6">
            <div class="stat-box clickable" @click="filterByType('offline')">
              <div class="stat-label">疑似下线</div>
              <div class="stat-value warning">{{ summary.by_type?.offline || 0 }}</div>
              <div class="stat-sub">台账有、Agent 断开</div>
            </div>
          </ElCol>
          <ElCol :xs="12" :sm="6">
            <div class="stat-box clickable" @click="filterByType('mismatch')">
              <div class="stat-label">信息不一致</div>
              <div class="stat-value info">{{ summary.by_type?.mismatch || 0 }}</div>
              <div class="stat-sub">IP/主机名/OS 不符</div>
            </div>
          </ElCol>
          <ElCol :xs="12" :sm="6">
            <div class="stat-box">
              <div class="stat-label">台账最近同步</div>
              <div class="stat-value small" :class="{ warning: freshness?.sync_stale }">
                {{ formatTime(freshness?.last_sync_at) || '无记录' }}
              </div>
              <div class="stat-sub">对账结果的可信度依据</div>
            </div>
          </ElCol>
        </ElRow>
      </template>
    </ElCard>

    <!-- AI 报告 -->
    <ElCard v-if="report" shadow="never" class="report-card">
      <div class="report-head">
        <span class="t">对账报告</span>
        <ElTag v-if="report.source === 'glm'" size="small" type="success" effect="plain">
          AI 生成
        </ElTag>
        <ElTag v-else size="small" type="info" effect="plain">规则模板（AI 未启用/降级）</ElTag>
        <span class="report-meta">
          数据窗口：{{ formatTime(report.provenance?.checked_at) }} · 基于
          {{ report.provenance?.diff_total }} 项差异
          <template v-if="report.provenance?.data_degraded">· 数据降级</template>
        </span>
      </div>
      <div class="report-body">{{ report.report }}</div>
      <AiFeedback v-if="report.source === 'glm'" target-type="report" :target-id="report.run_id" />
    </ElCard>

    <!-- 差异列表 -->
    <ElCard shadow="never" class="list-card">
      <div class="list-toolbar">
        <ElRadioGroup v-model="filterType" size="small" @change="() => loadList(1)">
          <ElRadioButton value="">全部类型</ElRadioButton>
          <ElRadioButton value="shadow">影子资产</ElRadioButton>
          <ElRadioButton value="offline">疑似下线</ElRadioButton>
          <ElRadioButton value="mismatch">信息不一致</ElRadioButton>
        </ElRadioGroup>
        <ElSelect
          v-model="filterStatus"
          size="small"
          placeholder="全部状态"
          clearable
          style="width: 130px"
          @change="() => loadList(1)"
        >
          <ElOption label="待处理" value="pending" />
          <ElOption label="已确认" value="confirmed" />
          <ElOption label="已忽略" value="ignored" />
          <ElOption label="已处理" value="resolved" />
        </ElSelect>
        <ElCheckbox v-model="allRuns" size="small" @change="() => loadList(1)">
          含历史批次
        </ElCheckbox>
      </div>

      <ElTable v-loading="listLoading" :data="rows" stripe row-key="id">
        <ElTableColumn label="差异类型" width="110">
          <template #default="{ row }">
            <ElTag size="small" :type="typeTag(row.reconciliation_type)" effect="light">
              {{ typeLabel(row.reconciliation_type) }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="对象" min-width="200">
          <template #default="{ row }">
            <div class="obj-cell">
              <div class="obj-main">{{ objName(row) }}</div>
              <div class="obj-sub">{{ objIp(row) }}</div>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="差异详情" min-width="300">
          <template #default="{ row }">
            <!-- mismatch：逐字段列出台账值 vs 实际值 -->
            <div v-if="row.reconciliation_type === 'mismatch'" class="diff-list">
              <div v-for="d in row.details?.diffs || []" :key="d.field" class="diff-row">
                <span class="diff-label">{{ d.label }}</span>
                <span class="diff-old">{{ d.ledger_value ?? '—' }}</span>
                <span class="diff-arrow">→</span>
                <span class="diff-new">{{ d.actual_value ?? '—' }}</span>
              </div>
            </div>
            <div v-else-if="row.reconciliation_type === 'offline'" class="detail-text">
              <template v-if="row.details?.reason === 'agent_deleted'">
                Wazuh 中已无此 Agent
              </template>
              <template v-else>
                Agent 状态 {{ row.details?.agent_status || 'unknown' }}， 已断开
                {{ row.details?.disconnected_days ?? '?' }} 天
                <span class="detail-sub">
                  （最后心跳 {{ formatTime(row.details?.last_keep_alive) || '未知' }}）
                </span>
              </template>
            </div>
            <div v-else class="detail-text">
              Agent {{ row.details?.agent?.id }} · {{ row.details?.agent?.os_name || '系统未知' }} ·
              状态 {{ row.details?.agent?.status }}
            </div>
            <div v-if="row.details?.suggestion" class="suggestion">
              建议：{{ row.details.suggestion }}
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="状态" width="150">
          <template #default="{ row }">
            <ElTag size="small" :type="statusTag(row.status)" effect="plain">
              {{ statusLabel(row.status) }}
            </ElTag>
            <div v-if="row.resolved_by" class="resolved-meta">
              {{ row.resolved_by }} · {{ formatTime(row.resolved_at) }}
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending' && hasAuth('resolve')">
              <ElButton text type="primary" size="small" @click="openResolve(row, 'resolved')">
                已处理
              </ElButton>
              <ElButton text size="small" @click="openResolve(row, 'confirmed')">确认</ElButton>
              <ElButton text size="small" @click="openResolve(row, 'ignored')">忽略</ElButton>
            </template>
            <span v-else-if="row.status !== 'pending'" class="muted">—</span>
            <span v-else class="muted">无权限</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="() => loadList()"
          @size-change="() => loadList(1)"
        />
      </div>
    </ElCard>

    <!-- 处理弹窗 -->
    <ElDialog v-model="resolveVisible" :title="resolveTitle" width="460px">
      <div class="resolve-body">
        <p class="resolve-target">{{ resolveTarget ? objName(resolveTarget) : '' }}</p>
        <ElInput
          v-model="resolveNote"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="处理说明（可选，会记入审计日志）"
        />
      </div>
      <template #footer>
        <ElButton @click="resolveVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="resolving" @click="submitResolve">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import {
    runReconcile,
    getReconcileSummary,
    getReconcileReport,
    getReconciliations,
    resolveReconciliation,
    type ReconciliationItem,
    type ReconciliationType,
    type ReconFreshness
  } from '@/api/asset'
  import { useAuth } from '@/hooks/core/useAuth'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'

  defineOptions({ name: 'AssetReconciliation' })

  const { hasAuth } = useAuth()
  const router = useRouter()

  const summary = ref<any>(null)
  const report = ref<any>(null)
  const running = ref(false)
  const reporting = ref(false)

  const rows = ref<ReconciliationItem[]>([])
  const listLoading = ref(false)
  const filterType = ref<'' | ReconciliationType>('')
  const filterStatus = ref<string>('')
  const allRuns = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)

  const resolveVisible = ref(false)
  const resolving = ref(false)
  const resolveNote = ref('')
  const resolveTarget = ref<ReconciliationItem | null>(null)
  const resolveStatus = ref<'confirmed' | 'ignored' | 'resolved'>('resolved')

  const freshness = computed<ReconFreshness | null>(() => summary.value?.freshness || null)
  const resolveTitle = computed(
    () =>
      ({
        resolved: '标记为已处理',
        confirmed: '确认差异属实',
        ignored: '忽略此差异'
      })[resolveStatus.value] || '处理差异'
  )

  const TYPE_LABEL: Record<string, string> = {
    shadow: '影子资产',
    offline: '疑似下线',
    mismatch: '信息不一致'
  }
  const STATUS_LABEL: Record<string, string> = {
    pending: '待处理',
    confirmed: '已确认',
    ignored: '已忽略',
    resolved: '已处理'
  }
  const typeLabel = (t: string) => TYPE_LABEL[t] || t
  const statusLabel = (s: string) => STATUS_LABEL[s] || s
  const typeTag = (t: string) =>
    ({ shadow: 'danger', offline: 'warning', mismatch: 'info' })[t] || 'info'
  const statusTag = (s: string) =>
    ({ pending: 'warning', confirmed: 'primary', ignored: 'info', resolved: 'success' })[s] ||
    'info'

  const formatTime = (v?: string | null) => {
    if (!v) return ''
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return String(v)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }

  /** 影子资产没有台账记录，对象名要取 agent 侧 */
  const objName = (row: ReconciliationItem) =>
    row.details?.ledger?.name || row.details?.agent?.name || '（未命名）'
  const objIp = (row: ReconciliationItem) =>
    row.details?.ledger?.asset_ip || row.details?.agent?.ip || ''

  const goDataHealth = () => router.push('/asset/data-health')

  const filterByType = (t: ReconciliationType) => {
    filterType.value = filterType.value === t ? '' : t
    loadList(1)
  }

  const loadSummary = async () => {
    try {
      const res = await getReconcileSummary()
      summary.value = res?.data || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载对账摘要失败')
    }
  }

  const loadList = async (toPage?: number) => {
    if (toPage) page.value = toPage
    listLoading.value = true
    try {
      const res = await getReconciliations({
        all_runs: allRuns.value,
        reconciliation_type: (filterType.value || undefined) as ReconciliationType | undefined,
        status: (filterStatus.value || undefined) as any,
        page: page.value,
        page_size: pageSize.value
      })
      rows.value = res?.data?.records || []
      total.value = res?.data?.total || 0
    } catch (e: any) {
      ElMessage.error(e?.message || '加载差异列表失败')
    } finally {
      listLoading.value = false
    }
  }

  const handleRun = async () => {
    running.value = true
    try {
      const res = await runReconcile()
      const s = res?.data
      const by = s?.by_type || {}
      ElMessage.success(
        `对账完成：影子 ${by.shadow || 0}、疑似下线 ${by.offline || 0}、不一致 ${by.mismatch || 0}`
      )
      report.value = null
      await Promise.all([loadSummary(), loadList(1)])
    } catch (e: any) {
      // Wazuh 不可达时后端返回 503 且带明确原因，必须原样告知用户，
      // 否则会误以为"对账失败=没差异"
      ElMessage.error(e?.message || '对账执行失败')
    } finally {
      running.value = false
    }
  }

  const handleReport = async () => {
    reporting.value = true
    try {
      const res = await getReconcileReport()
      report.value = res?.data || null
    } catch (e: any) {
      ElMessage.error(e?.message || 'AI 报告生成失败')
    } finally {
      reporting.value = false
    }
  }

  const openResolve = (row: ReconciliationItem, status: 'confirmed' | 'ignored' | 'resolved') => {
    resolveTarget.value = row
    resolveStatus.value = status
    resolveNote.value = ''
    resolveVisible.value = true
  }

  const submitResolve = async () => {
    if (!resolveTarget.value) return
    resolving.value = true
    try {
      await resolveReconciliation(resolveTarget.value.id, resolveStatus.value, resolveNote.value)
      ElMessage.success('处理成功')
      resolveVisible.value = false
      await Promise.all([loadSummary(), loadList()])
    } catch (e: any) {
      // 409 = 已被他人处理。刷新列表让用户看到最新状态，而不是干瞪眼
      ElMessage.error(e?.message || '处理失败')
      await loadList()
    } finally {
      resolving.value = false
    }
  }

  onMounted(async () => {
    await loadSummary()
    if (summary.value?.has_data) await loadList(1)
  })
</script>

<style lang="scss" scoped>
  .recon-page {
    .freshness-alert {
      margin-bottom: 12px;

      .freshness-detail {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        margin-top: 4px;
        font-size: 12px;

        .fr-item::after {
          margin-left: 12px;
          color: var(--el-border-color);
          content: '|';
        }

        .fr-item:last-of-type::after {
          content: '';
        }
      }
    }

    .summary-card,
    .report-card,
    .list-card {
      margin-bottom: 12px;
    }

    .summary-head {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;

      .summary-title {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;

        .t {
          font-size: 16px;
          font-weight: 600;
        }

        .meta {
          font-size: 12px;
          color: var(--art-text-gray-600);
        }
      }
    }

    .stat-row {
      .stat-box {
        padding: 12px;
        text-align: center;
        background: var(--art-main-bg-color);
        border-radius: 6px;

        &.clickable {
          cursor: pointer;
          transition: background 0.2s;

          &:hover {
            background: var(--art-gray-100);
          }
        }

        .stat-label {
          font-size: 12px;
          color: var(--art-text-gray-600);
        }

        .stat-value {
          margin: 4px 0;
          font-size: 24px;
          font-weight: 600;

          &.small {
            font-size: 13px;
          }

          &.danger {
            color: var(--el-color-danger);
          }

          &.warning {
            color: var(--el-color-warning);
          }

          &.info {
            color: var(--el-color-info);
          }
        }

        .stat-sub {
          font-size: 11px;
          color: var(--art-text-gray-500);
        }
      }
    }

    .report-head {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 8px;

      .t {
        font-size: 15px;
        font-weight: 600;
      }

      .report-meta {
        font-size: 12px;
        color: var(--art-text-gray-500);
      }
    }

    .report-body {
      font-size: 13px;
      line-height: 1.8;
      white-space: pre-wrap;
    }

    .list-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }

    .obj-cell {
      .obj-main {
        font-weight: 500;
      }

      .obj-sub {
        font-size: 12px;
        color: var(--art-text-gray-500);
      }
    }

    .diff-list {
      .diff-row {
        display: flex;
        gap: 6px;
        align-items: center;
        font-size: 12px;
        line-height: 1.9;

        .diff-label {
          min-width: 62px;
          color: var(--art-text-gray-600);
        }

        .diff-old {
          color: var(--el-color-danger);
          text-decoration: line-through;
        }

        .diff-arrow {
          color: var(--art-text-gray-400);
        }

        .diff-new {
          color: var(--el-color-success);
        }
      }
    }

    .detail-text {
      font-size: 12px;

      .detail-sub {
        color: var(--art-text-gray-500);
      }
    }

    .suggestion {
      margin-top: 4px;
      font-size: 12px;
      color: var(--el-color-primary);
    }

    .resolved-meta {
      margin-top: 2px;
      font-size: 11px;
      color: var(--art-text-gray-500);
    }

    .muted {
      color: var(--art-text-gray-400);
    }

    .pager {
      display: flex;
      justify-content: flex-end;
      margin-top: 12px;
    }

    .resolve-body {
      .resolve-target {
        margin-bottom: 10px;
        font-weight: 500;
      }
    }
  }
</style>
