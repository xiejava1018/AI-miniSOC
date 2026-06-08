<template>
  <div class="alert-list-page art-full-height">
    <!-- 统计卡片 -->
    <ElRow :gutter="16" class="stats-row">
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card">
          <div class="stat-value">{{ statsTotal }}</div>
          <div class="stat-label">总告警(24h)</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card stat-critical">
          <div class="stat-value text-danger">{{ statsCritical }}</div>
          <div class="stat-label">高危(≥12)</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card stat-warning">
          <div class="stat-value text-warning">{{ statsMedium }}</div>
          <div class="stat-label">中危(8-11)</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card stat-info">
          <div class="stat-value text-info">{{ statsLow }}</div>
          <div class="stat-label">低危(≤7)</div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchState"
      :items="searchItems"
      @reset="resetSearch"
      @search="searchData"
    />

    <ElCard shadow="never" class="art-table-card">
      <!-- 表格头部 -->
      <ArtTableHeader
        :columnList="columnOptions"
        v-model:columns="columnChecks"
        @refresh="handleRefresh"
      >
        <template #left>
          <span class="total-info">共 {{ paginationState.total }} 条告警</span>
        </template>
      </ArtTableHeader>

      <!-- 表格 -->
      <ArtTable
        :data="tableData"
        :columns="columns"
        :pagination="paginationState"
        :loading="isLoading"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="onPageSizeChange"
        @pagination:current-change="onCurrentPageChange"
      />
    </ElCard>

    <!-- 详情弹窗 -->
    <ElDialog
      v-model="detailVisible"
      title="告警详情"
      width="800px"
      align-center
      :close-on-click-modal="false"
    >
      <template v-if="detailData">
        <ElDescriptions :column="2" border>
          <ElDescriptionsItem label="时间">
            {{ formatTime(detailData.timestamp) }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="等级">
            <ElTag :type="getLevelType(detailData.rule?.level)">
              {{ detailData.rule?.level }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="规则ID">{{ detailData.rule?.id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="规则描述" :span="2">
            {{ detailData.rule?.description }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="Agent名称">{{ detailData.agent?.name }}</ElDescriptionsItem>
          <ElDescriptionsItem label="Agent IP">{{ detailData.agent?.ip }}</ElDescriptionsItem>
          <ElDescriptionsItem label="来源位置" :span="2">{{ detailData.location }}</ElDescriptionsItem>
          <ElDescriptionsItem label="完整日志" :span="2">
            <pre class="full-log">{{ detailData.full_log || '无' }}</pre>
          </ElDescriptionsItem>
        </ElDescriptions>
      </template>
      <template #footer>
        <ElButton @click="detailVisible = false">关闭</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, h, resolveComponent, onMounted } from 'vue'
  import {
    getAlertList,
    getAlertStatistics,
    type AlertItem,
  } from '@/api/alert'
  import { ElMessage } from 'element-plus'
  import { useTable } from '@/composables/useTable'
  import type { SearchFormItem } from '@/types'
  import { ElTag } from 'element-plus'

  defineOptions({ name: 'AlertListPage' })

  // ── 统计 ────────────────────────────────────────────
  const statsTotal = ref(0)
  const statsCritical = ref(0)
  const statsMedium = ref(0)
  const statsLow = ref(0)

  const loadStatistics = async () => {
    try {
      const res: any = await getAlertStatistics({ hours: 24 })
      const data = res?.data || res
      let total = 0
      let critical = 0
      let medium = 0
      let low = 0
      for (const b of data?.by_level || []) {
        const lv = parseInt(b.level || b.key)
        const cnt = b.count || b.doc_count || 0
        total += cnt
        if (lv >= 12) critical += cnt
        else if (lv >= 8) medium += cnt
        else low += cnt
      }
      statsTotal.value = total
      statsCritical.value = critical
      statsMedium.value = medium
      statsLow.value = low
    } catch {
      // stat load failed, non-blocking
    }
  }

  // ── useTable ────────────────────────────────────────
  const tableApi = useTable<any>({
    core: {
      apiFn: getAlertList,
      apiParams: { limit: 20, skip: 0 },
      columnsFactory: () => [
        {
          prop: 'timestamp',
          label: '时间',
          align: 'center',
          minWidth: 170,
          formatter: (row: any) => formatTime(row.timestamp)
        },
        {
          prop: 'rule.level',
          label: '等级',
          align: 'center',
          width: 80,
          formatter: (row: any) => {
            const lv = row.rule?.level
            return h(
              resolveComponent('ElTag'),
              { type: getLevelType(lv), effect: 'light' },
              { default: () => String(lv ?? '?') }
            )
          }
        },
        {
          prop: 'rule.description',
          label: '规则描述',
          align: 'left',
          minWidth: 280,
          showOverflowTooltip: true,
          formatter: (row: any) => row.rule?.description || '--'
        },
        {
          prop: 'agent.name',
          label: 'Agent',
          align: 'center',
          minWidth: 140,
          formatter: (row: any) => row.agent?.name || '--'
        },
        {
          prop: 'agent.ip',
          label: 'IP',
          align: 'center',
          width: 140,
          formatter: (row: any) => row.agent?.ip || '--'
        },
        {
          prop: 'location',
          label: '来源',
          align: 'left',
          minWidth: 180,
          showOverflowTooltip: true,
          formatter: (row: any) => row.location || '--'
        },
        {
          prop: 'rule.id',
          label: '规则ID',
          align: 'center',
          width: 90,
          formatter: (row: any) => row.rule?.id || '--'
        },
        {
          prop: 'operation',
          label: '操作',
          align: 'center',
          width: 80,
          fixed: 'right',
          formatter: (row: any) =>
            h('span',
              {
                style: 'cursor: pointer; color: var(--el-color-primary);',
                onClick: () => showDetail(row)
              },
              '详情'
            )
        }
      ]
    },
    hooks: {
      onError: (error) => ElMessage.error(error.message)
    }
  })

  const {
    data: tableData,
    loading: isLoading,
    columns,
    columnChecks,
    pagination: paginationState,
    searchParams: searchState,
    getData: searchData,
    resetSearchParams: resetSearch,
    handleSizeChange: onPageSizeChange,
    handleCurrentChange: onCurrentPageChange,
    refreshAll
  } = tableApi as any

  // ── 搜索配置 ────────────────────────────────────────
  const searchItems: SearchFormItem[] = [
    {
      label: '等级',
      key: 'level',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择等级',
      options: [
        { label: '≥3 所有', value: 3 },
        { label: '≥5', value: 5 },
        { label: '≥8 中危', value: 8 },
        { label: '≥12 高危', value: 12 },
        { label: '≥15 严重', value: 15 }
      ]
    },
    {
      label: 'IP地址',
      key: 'ip',
      type: 'input',
      span: 6,
      clearable: true,
      placeholder: '请输入Agent IP'
    },
    {
      label: '时间范围',
      key: 'hours',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '最近时间',
      options: [
        { label: '最近1小时', value: 1 },
        { label: '最近6小时', value: 6 },
        { label: '最近24小时', value: 24 },
        { label: '最近3天', value: 72 },
        { label: '最近7天', value: 168 }
      ]
    }
  ]

  const columnOptions = [
    { label: '时间', prop: 'timestamp' },
    { label: '等级', prop: 'rule.level' },
    { label: '规则描述', prop: 'rule.description' },
    { label: 'Agent', prop: 'agent.name' },
    { label: 'IP', prop: 'agent.ip' },
    { label: '来源', prop: 'location' },
    { label: '规则ID', prop: 'rule.id' },
    { label: '操作', prop: 'operation' }
  ]

  // ── 详情弹窗 ────────────────────────────────────────
  const detailVisible = ref(false)
  const detailData = ref<AlertItem | null>(null)

  const showDetail = (row: AlertItem) => {
    detailData.value = row
    detailVisible.value = true
  }

  // ── 工具函数 ────────────────────────────────────────
  const formatTime = (ts?: string) => {
    if (!ts) return '--'
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { hour12: false })
  }

  const getLevelType = (level?: number): 'danger' | 'warning' | 'info' | '' => {
    if (!level && level !== 0) return ''
    if (level >= 12) return 'danger'
    if (level >= 8) return 'warning'
    return 'info'
  }

  const handleRefresh = () => {
    loadStatistics()
    refreshAll()
  }

  onMounted(() => {
    loadStatistics()
  })
</script>

<style lang="scss" scoped>
  .alert-list-page {
    .stats-row {
      margin-bottom: 16px;
    }

    .stat-card {
      text-align: center;
      .stat-value {
        font-size: 28px;
        font-weight: 700;
      }
      .stat-label {
        margin-top: 4px;
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
    }

    .stat-critical .stat-value {
      color: var(--el-color-danger);
    }
    .stat-warning .stat-value {
      color: var(--el-color-warning);
    }
    .stat-info .stat-value {
      color: var(--el-color-info);
    }

    .total-info {
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }

    .full-log {
      max-height: 200px;
      overflow-y: auto;
      margin: 0;
      padding: 8px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-all;
    }
  }
</style>
