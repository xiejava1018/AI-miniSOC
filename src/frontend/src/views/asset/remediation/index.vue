<!--
  OH-UI.13 整改工单处理流

  数据源：OH-4.6 soc_remediation_tickets（对账差异 / 合规 fail 项派生）。
  设计要点（参照 attribution-workbench 基准）：
  - 入口型列表在前：状态 radio（未完结优先）+ 来源筛选
  - 责任链可查：派单人 → 责任人 → 处理人 → 验证人
-->
<template>
  <div class="rem-page art-full-height">
    <ElCard shadow="never" class="list-card">
      <template #header>
        <div class="card-head">
          <span class="t">整改工单处理流</span>
          <ElTag size="small" type="warning" effect="plain">
            未完结 {{ openCount }}
          </ElTag>
          <span class="meta">
            对账差异与合规问题的整改责任链：派单 → 指派 → 处理 → 验证
          </span>
        </div>
      </template>

      <div class="toolbar">
        <ElRadioGroup v-model="statusFilter" size="small" @change="loadList(1)">
          <ElRadioButton value="">全部</ElRadioButton>
          <ElRadioButton value="open">待处理</ElRadioButton>
          <ElRadioButton value="in_progress">处理中</ElRadioButton>
          <ElRadioButton value="resolved">待验证</ElRadioButton>
          <ElRadioButton value="verified">已验证</ElRadioButton>
          <ElRadioButton value="cancelled">已取消</ElRadioButton>
        </ElRadioGroup>
        <div class="toolbar-right">
          <ElSelect
            v-model="sourceFilter"
            clearable
            placeholder="来源"
            size="small"
            style="width: 130px"
            @change="loadList(1)"
          >
            <ElOption label="对账差异" value="reconciliation" />
            <ElOption label="合规问题" value="compliance" />
          </ElSelect>
          <ElButton
            :icon="Refresh"
            circle
            size="small"
            @click="loadList(1)"
          />
        </div>
      </div>

      <ElTable v-loading="loading" :data="rows" stripe row-key="id">
        <ElTableColumn label="工单" min-width="220">
          <template #default="{ row }">
            <div class="obj-cell">
              <div class="obj-main">{{ row.title }}</div>
              <div class="obj-sub">
                {{ sourceLabel(row.source_type) }} · {{ severityLabel(row.severity) }}
                <template v-if="row.occurrence_count > 1">
                  · 重复 {{ row.occurrence_count }} 次
                </template>
              </div>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="状态" width="100" align="center">
          <template #default="{ row }">
            <ElTag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="责任人" width="110">
          <template #default="{ row }">
            <span v-if="row.assignee">{{ row.assignee }}</span>
            <span v-else class="muted">未指派</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="期限" width="110">
          <template #default="{ row }">
            <span :class="{ overdue: isOverdue(row) }">
              {{ formatDate(row.due_at) }}
            </span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="责任链" min-width="150">
          <template #default="{ row }">
            <div class="chain">
              <span>派单 {{ row.created_by }}</span>
              <span v-if="row.resolved_by">处理 {{ row.resolved_by }}</span>
              <span v-if="row.verified_by">验证 {{ row.verified_by }}</span>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="创建时间" min-width="150">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.created_at) }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'open'">
              <ElButton
                v-if="hasAuth('assign')"
                text
                type="primary"
                size="small"
                @click="openAssign(row)"
              >
                指派
              </ElButton>
              <ElButton
                v-if="hasAuth('advance')"
                text
                size="small"
                @click="doAdvance(row, 'in_progress')"
              >
                开始
              </ElButton>
            </template>
            <ElButton
              v-if="row.status === 'in_progress' && hasAuth('advance')"
              text
              type="success"
              size="small"
              @click="openResolve(row)"
            >
              完成
            </ElButton>
            <template v-if="row.status === 'resolved' && hasAuth('advance')">
              <ElButton
                text
                type="success"
                size="small"
                @click="doAdvance(row, 'verified')"
              >
                验证通过
              </ElButton>
              <ElButton
                text
                type="danger"
                size="small"
                @click="openReopen(row)"
              >
                重开
              </ElButton>
            </template>
            <ElButton
              v-if="canCancel(row) && hasAuth('advance')"
              text
              type="info"
              size="small"
              @click="doAdvance(row, 'cancelled')"
            >
              取消
            </ElButton>
            <ElButton text size="small" @click="openDetail(row)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="() => loadList()"
          @size-change="() => loadList(1)"
        />
      </div>
    </ElCard>

    <!-- 指派抽屉 -->
    <ElDialog v-model="assignVisible" title="指派责任人" width="420px">
      <ElForm label-width="80px">
        <ElFormItem label="责任人">
          <ElInput v-model="assignForm.assignee" placeholder="责任人用户名" />
        </ElFormItem>
        <ElFormItem label="整改期限">
          <ElDatePicker
            v-model="assignForm.dueAt"
            type="datetime"
            placeholder="可选"
            style="width: 100%"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="assignVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="submitAssign">
          确认指派
        </ElButton>
      </template>
    </ElDialog>

    <!-- 完成/重开备注 -->
    <ElDialog
      v-model="noteVisible"
      :title="noteTitle"
      width="480px"
    >
      <ElInput
        v-model="noteForm.note"
        type="textarea"
        :rows="3"
        maxlength="500"
        show-word-limit
        :placeholder="notePlaceholder"
      />
      <template #footer>
        <ElButton @click="noteVisible = false">取消</ElButton>
        <ElButton
          :type="noteForm.toStatus === 'reopened' ? 'danger' : 'primary'"
          :loading="submitting"
          @click="submitNote"
        >
          确认
        </ElButton>
      </template>
    </ElDialog>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="工单详情" size="560px">
      <div v-if="detail" class="detail-body">
        <div class="block">
          <ElDescriptions :column="2" border size="small">
            <ElDescriptionsItem label="标题" :span="2">
              {{ detail.title }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="来源">
              {{ sourceLabel(detail.source_type) }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="严重度">
              {{ severityLabel(detail.severity) }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="状态">
              <ElTag :type="statusTagType(detail.status)" size="small">
                {{ statusLabel(detail.status) }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="重复触发">
              {{ detail.occurrence_count }} 次
            </ElDescriptionsItem>
            <ElDescriptionsItem label="派单人">
              {{ detail.created_by }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="责任人">
              {{ detail.assignee || '未指派' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="处理人">
              {{ detail.resolved_by || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="验证人">
              {{ detail.verified_by || '—' }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <div v-if="detail.detail" class="block">
          <div class="block-title">来源快照</div>
          <ElInput
            :model-value="JSON.stringify(detail.detail, null, 2)"
            type="textarea"
            :rows="8"
            readonly
          />
        </div>

        <div v-if="detail.resolve_note" class="block">
          <div class="block-title">处理说明</div>
          <ElAlert :closable="false" type="info" show-icon>
            {{ detail.resolve_note }}
          </ElAlert>
        </div>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { ElMessage } from 'element-plus'
  import { Refresh } from '@element-plus/icons-vue'
  import {
    advanceRemediationTicket,
    assignRemediationTicket,
    getRemediationTicket,
    getRemediationTickets,
    type RemediationStatus,
    type RemediationTicketItem
  } from '@/api/asset'
  import { useAuth } from '@/hooks/core/useAuth'

  defineOptions({ name: 'RemediationTickets' })

  const { hasAuth } = useAuth()

  const rows = ref<RemediationTicketItem[]>([])
  const loading = ref(false)
  const statusFilter = ref<RemediationStatus | ''>('')
  const sourceFilter = ref<'reconciliation' | 'compliance' | ''>('')
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const openCount = ref(0)

  const assignVisible = ref(false)
  const assignForm = ref<{ id: string; assignee: string; dueAt: string | null }>({
    id: '',
    assignee: '',
    dueAt: null
  })

  const noteVisible = ref(false)
  const noteForm = ref<{ id: string; toStatus: RemediationStatus; note: string }>({
    id: '',
    toStatus: 'resolved',
    note: ''
  })
  const noteTitle = computed(() =>
    noteForm.value.toStatus === 'resolved' ? '完成整改' : '验证不通过，重开'
  )
  const notePlaceholder = computed(() =>
    noteForm.value.toStatus === 'resolved'
      ? '处理说明（做了什么整改，建议填写）'
      : '重开原因（复测不通过的依据）'
  )

  const detailVisible = ref(false)
  const detail = ref<RemediationTicketItem | null>(null)
  const submitting = ref(false)

  const SOURCE_LABELS: Record<string, string> = {
    reconciliation: '对账差异',
    compliance: '合规问题'
  }
  const SEVERITY_LABELS: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低'
  }
  const STATUS_LABELS: Record<string, string> = {
    open: '待处理',
    in_progress: '处理中',
    resolved: '待验证',
    verified: '已验证',
    reopened: '已重开',
    cancelled: '已取消'
  }

  const sourceLabel = (s: string) => SOURCE_LABELS[s] || s
  const severityLabel = (s: string) => SEVERITY_LABELS[s] || s
  const statusLabel = (s: string) => STATUS_LABELS[s] || s
  const statusTagType = (s: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
    switch (s) {
      case 'verified':
        return 'success'
      case 'resolved':
        return 'warning'
      case 'reopened':
        return 'danger'
      case 'cancelled':
        return 'info'
      default:
        return 'primary'
    }
  }

  const formatTime = (v?: string | null) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime())
      ? String(v)
      : d.toLocaleString('zh-CN', { hour12: false })
  }
  const formatDate = (v?: string | null) => {
    if (!v) return '—'
    const d = new Date(v)
    return Number.isNaN(d.getTime())
      ? String(v)
      : d.toLocaleDateString('zh-CN')
  }
  const isOverdue = (row: RemediationTicketItem) => {
    if (!row.due_at) return false
    if (row.status === 'verified' || row.status === 'cancelled') return false
    return new Date(row.due_at).getTime() < Date.now()
  }
  const canCancel = (row: RemediationTicketItem) =>
    ['open', 'in_progress', 'reopened'].includes(row.status)

  const loadList = async (toPage?: number) => {
    if (toPage) page.value = toPage
    loading.value = true
    try {
      const params: Record<string, any> = {
        page: page.value,
        page_size: pageSize.value
      }
      if (statusFilter.value) params.status = statusFilter.value
      if (sourceFilter.value) params.source_type = sourceFilter.value
      const res = await getRemediationTickets(params)
      rows.value = res?.data?.items || []
      total.value = res?.data?.total || 0
      openCount.value = res?.data?.open_count || 0
    } catch (e: any) {
      ElMessage.error(e?.message || '加载工单列表失败')
    } finally {
      loading.value = false
    }
  }

  const openAssign = (row: RemediationTicketItem) => {
    assignForm.value = {
      id: row.id,
      assignee: row.assignee || '',
      dueAt: row.due_at ? row.due_at : null
    }
    assignVisible.value = true
  }

  const submitAssign = async () => {
    if (!assignForm.value.assignee.trim()) {
      ElMessage.warning('请填写责任人')
      return
    }
    submitting.value = true
    try {
      await assignRemediationTicket(assignForm.value.id, {
        assignee: assignForm.value.assignee.trim(),
        due_at: assignForm.value.dueAt || undefined
      })
      ElMessage.success('指派成功')
      assignVisible.value = false
      await loadList()
    } catch (e: any) {
      ElMessage.error(e?.message || '指派失败')
    } finally {
      submitting.value = false
    }
  }

  const doAdvance = async (
    row: RemediationTicketItem,
    toStatus: RemediationStatus,
    note?: string
  ) => {
    submitting.value = true
    try {
      await advanceRemediationTicket(row.id, { to_status: toStatus, note })
      ElMessage.success('操作成功')
      await loadList()
    } catch (e: any) {
      // 409 非法迁移/已被处理 —— 消息直接展示
      ElMessage.error(e?.message || '操作失败')
    } finally {
      submitting.value = false
    }
  }

  const openResolve = (row: RemediationTicketItem) => {
    noteForm.value = { id: row.id, toStatus: 'resolved', note: '' }
    noteVisible.value = true
  }
  const openReopen = (row: RemediationTicketItem) => {
    noteForm.value = { id: row.id, toStatus: 'reopened', note: '' }
    noteVisible.value = true
  }
  const submitNote = async () => {
    submitting.value = true
    try {
      await advanceRemediationTicket(noteForm.value.id, {
        to_status: noteForm.value.toStatus,
        note: noteForm.value.note || undefined
      })
      ElMessage.success('操作成功')
      noteVisible.value = false
      await loadList()
    } catch (e: any) {
      ElMessage.error(e?.message || '操作失败')
    } finally {
      submitting.value = false
    }
  }

  const openDetail = async (row: RemediationTicketItem) => {
    detail.value = null
    detailVisible.value = true
    try {
      const res = await getRemediationTicket(row.id)
      detail.value = res?.data || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载详情失败')
      detailVisible.value = false
    }
  }

  loadList(1)
</script>

<style lang="scss" scoped>
  .rem-page {
    height: auto;
    min-height: var(--art-full-height);

    .card-head {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
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

    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;

      .toolbar-right {
        display: flex;
        gap: 8px;
        align-items: center;
      }
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

    .chain {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      font-size: 12px;
      color: var(--art-text-gray-500);
    }

    .overdue {
      color: var(--el-color-danger);
    }

    .muted {
      color: var(--art-text-gray-400);
    }

    .pager {
      display: flex;
      justify-content: flex-end;
      margin-top: 12px;
    }

    .detail-body {
      .block {
        margin-bottom: 20px;
      }

      .block-title {
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 600;
      }
    }
  }
</style>
