<!--
  资产概览页面
  设计文档: docs/design/2026-06-03-asset-overview-design.md

  1 次请求拿到全量数据,展示:
  - 顶部 4 个 KPI(总资产/高危/24h 告警/未关闭事件)
  - 中部 3 张环图(类型/在线状态/重要度)
  - 底部 2 张 Top 表并列(高危资产 + 告警资产)
  - 行可点 → /assets/detail/{id}
-->
<template>
  <div class="asset-overview-page art-full-height">
    <!-- 顶部加载/错误态 -->
    <ElAlert
      v-if="loadError"
      :title="`数据加载失败: ${loadError}`"
      type="error"
      :closable="false"
      class="overview-alert"
    />

    <!-- 1. KPI 区 -->
    <ElRow :gutter="16" class="kpi-row">
      <ElCol :sm="12" :md="6" v-for="kpi in kpiCards" :key="kpi.label">
        <div
          class="metric-card"
          :class="[`metric-card--${kpi.type}`, { 'metric-card--muted': kpi.value === 0 && kpi.mutedWhenZero }]"
        >
          <div class="metric-card__label">{{ kpi.label }}</div>
          <div class="metric-card__value">
            <span class="metric-card__number">{{ kpi.value }}</span>
            <span v-if="kpi.suffix" class="metric-card__suffix">{{ kpi.suffix }}</span>
          </div>
          <div v-if="kpi.subLabel" class="metric-card__sub">{{ kpi.subLabel }}</div>
        </div>
      </ElCol>
    </ElRow>

    <!-- 2. 分布区:类型 + 状态 + 重要度 -->
    <ElRow :gutter="16" class="chart-row">
      <ElCol :sm="24" :md="8">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">资产类型分布</span>
          </template>
          <ArtRingChart
            height="280px"
            :data="typeRingData"
            :show-legend="true"
            legend-position="right"
            center-text="类型"
          />
        </ElCard>
      </ElCol>
      <ElCol :sm="24" :md="8">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">在线状态分布</span>
          </template>
          <ArtRingChart
            height="280px"
            :data="statusRingData"
            :show-legend="true"
            legend-position="right"
            center-text="状态"
          />
        </ElCard>
      </ElCol>
      <ElCol :sm="24" :md="8">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">重要度分布</span>
          </template>
          <ArtRingChart
            height="280px"
            :data="criticalityRingData"
            :show-legend="true"
            legend-position="right"
            center-text="重要度"
          />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 3. Top 10 并列 -->
    <ElRow :gutter="16" class="top-row">
      <ElCol :sm="24" :md="12" class="top-col">
        <ElCard shadow="never" class="top-card">
          <template #header>
            <span class="chart-title">Top 10 高危资产</span>
            <span class="chart-subtitle">(按风险评分排序)</span>
          </template>
          <div class="top-table-wrap">
            <ElTable
              :data="topRisky"
              v-loading="false"
              stripe
              size="small"
              class="top-table"
              empty-text="暂无高危资产"
              @row-click="goDetail"
            >
              <ElTableColumn prop="ip" label="IP" min-width="120" />
              <ElTableColumn prop="name" label="名称" min-width="140" show-overflow-tooltip />
              <ElTableColumn label="类型" min-width="100">
                <template #default="{ row }">{{ typeLabel(row.asset_type) }}</template>
              </ElTableColumn>
              <ElTableColumn label="重要度" min-width="90">
                <template #default="{ row }">
                  <ElTag
                    v-if="row.criticality"
                    :type="criticalityTagType(row.criticality)"
                    size="small"
                  >
                    {{ criticalityLabel(row.criticality) }}
                  </ElTag>
                  <span v-else>-</span>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="score" label="评分" min-width="80" align="right" />
              <ElTableColumn label="风险因子" min-width="280">
                <template #default="{ row }">
                  <ElTag
                    v-for="f in row.factors"
                    :key="f"
                    type="danger"
                    effect="plain"
                    size="small"
                    class="factor-tag"
                  >
                    {{ f }}
                  </ElTag>
                </template>
              </ElTableColumn>
            </ElTable>
          </div>
        </ElCard>
      </ElCol>

      <ElCol :sm="24" :md="12" class="top-col">
        <ElCard shadow="never" class="top-card">
          <template #header>
            <span class="chart-title">Top 10 告警资产</span>
            <span class="chart-subtitle">(按 24h 告警数排序)</span>
          </template>
          <div class="top-table-wrap">
            <ElTable
              :data="topAlert"
              size="small"
              class="top-table"
              empty-text="暂无告警数据"
              @row-click="goDetail"
            >
              <ElTableColumn prop="ip" label="IP" min-width="120" />
              <ElTableColumn prop="name" label="名称" min-width="140" show-overflow-tooltip />
              <ElTableColumn label="类型" min-width="100">
                <template #default="{ row }">{{ typeLabel(row.asset_type) }}</template>
              </ElTableColumn>
              <ElTableColumn prop="alert_24h" label="24h 告警" min-width="100" align="right" />
              <ElTableColumn prop="alert_critical_24h" label="高危告警" min-width="100" align="right">
                <template #default="{ row }">
                  <span :class="{ 'text-danger fw-600': row.alert_critical_24h > 0 }">
                    {{ row.alert_critical_24h }}
                  </span>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="last_alert_at" label="最近告警时间" min-width="160">
                <template #default="{ row }">{{ formatTime(row.last_alert_at) }}</template>
              </ElTableColumn>
            </ElTable>
          </div>
        </ElCard>
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
  import { ref, onMounted, computed } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import { getAssetOverview } from '@/api/asset'
  import { useDictStore } from '@/store/modules/dict'

  defineOptions({ name: 'AssetOverview' })

  const router = useRouter()
  const dictStore = useDictStore()

  const overview = ref<Api.Asset.AssetOverview | null>(null)
  const loadError = ref<string>('')

  // ---------- KPI 卡 ----------

  const kpiCards = computed(() => {
    const k = overview.value?.kpi
    return [
      {
        label: '总资产',
        value: k?.total_assets ?? 0,
        suffix: '个',
        type: 'info' as const,
        subLabel: '纳管资产总数',
        mutedWhenZero: false
      },
      {
        label: '高危资产',
        value: k?.high_risk_assets ?? 0,
        suffix: '个',
        type: 'danger' as const,
        subLabel: '命中 D6 任意条件',
        mutedWhenZero: true
      },
      {
        label: '24h 告警',
        value: k?.alerts_24h ?? 0,
        suffix: '条',
        type: 'danger' as const,
        subLabel: 'Wazuh/OpenSearch',
        mutedWhenZero: true
      },
      {
        label: '未关闭事件',
        value: k?.open_incidents ?? 0,
        suffix: '个',
        type: 'warning' as const,
        subLabel: '需 SOC 跟进',
        mutedWhenZero: true
      }
    ]
  })

  // ---------- 分布图(环图) ----------

  const typeRingData = computed(() => ringDataFrom(overview.value?.distribution.by_type))
  const statusRingData = computed(() =>
    ringDataFrom(overview.value?.distribution.by_status, mapStatusLabel)
  )
  const criticalityRingData = computed(() =>
    ringDataFrom(overview.value?.distribution.by_criticality, (k) =>
      criticalityLabel(k)
    )
  )

  function ringDataFrom(
    items: Api.Asset.AssetDistributionItem[] | undefined,
    labelMap?: (key: string) => string
  ): { name: string; value: number }[] {
    if (!items || items.length === 0) {
      return [{ name: '暂无数据', value: 1 }]
    }
    return items.map((it) => ({
      name: labelMap ? labelMap(it.key) : it.key,
      value: it.count
    }))
  }

  // ---------- Top 表 ----------

  const topRisky = computed(() => overview.value?.top_risky_assets ?? [])
  const topAlert = computed(() => overview.value?.top_alert_assets ?? [])

  // ---------- 字典 / 标签 ----------

  const typeLabel = (key: string | null | undefined): string => {
    if (!key) return '-'
    const map = dictStore.getLabelMap('asset_type')
    return map[key] || key
  }

  const criticalityLabel = (key: string): string => {
    const map = dictStore.getLabelMap('asset_criticality')
    return map[key] || key
  }

  const criticalityTagType = (key: string): 'danger' | 'warning' | 'info' | 'success' => {
    if (key === 'core') return 'danger'
    if (key === 'important') return 'warning'
    if (key === 'normal') return 'info'
    return 'info'
  }

  const mapStatusLabel = (key: string): string => {
    const map = dictStore.getLabelMap('asset_status')
    return map[key] || key
  }

  // ---------- 跳转详情 ----------

  const goDetail = (row: { id?: string | null }) => {
    if (!row?.id) {
      ElMessage.warning('该资产不在资产管理范围内,无法查看详情')
      return
    }
    // 路由路径: /assets → detail/:id(参照 src/views/asset/list/index.vue:497)
    router.push(`/assets/detail/${row.id}`)
  }

  // ---------- 工具 ----------

  const formatTime = (iso: string | null | undefined): string => {
    if (!iso) return '-'
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }

  // ---------- 数据加载 ----------

  const fetchOverview = async () => {
    try {
      const res = await getAssetOverview()
      if (res.code === 200 && res.data) {
        overview.value = res.data
        loadError.value = ''
      } else {
        loadError.value = res.msg || '后端返回异常'
        overview.value = null
      }
    } catch (err: any) {
      console.error('[AssetOverview] 加载失败:', err)
      loadError.value = err?.message || '网络错误'
      overview.value = null
    }
  }

  onMounted(() => {
    fetchOverview()
  })
</script>

<style lang="scss" scoped>
  .asset-overview-page {
    padding: 16px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .overview-alert {
    margin-bottom: 8px;
  }

  .kpi-row {
    flex-shrink: 0;
  }

  .chart-row,
  .top-row {
    flex-shrink: 0;
  }

  // 显式给 Top 行一个最小高度,让两列等高(10 行表格 ~ 420px)
  .top-row {
    min-height: 480px;
  }

  .chart-card,
  .top-card {
    margin-bottom: 0;
  }

  // 让两列 Top 卡片等高
  .top-col {
    display: flex;
  }

  .top-card {
    width: 100%;
    display: flex;
    flex-direction: column;

    :deep(.el-card__body) {
      flex: 1 1 0;
      min-height: 0;
      display: flex;
      flex-direction: column;
      padding: 12px;
    }
  }

  .top-table-wrap {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .top-table {
    flex: 1 1 0;

    :deep(.el-table__body-wrapper) {
      flex: 1 1 0;
      min-height: 0;
      overflow: auto;
    }
  }

  .chart-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--el-text-color-primary, #303133);
  }

  .chart-subtitle {
    margin-left: 8px;
    font-size: 12px;
    color: var(--el-text-color-secondary, #909399);
  }

  .top-table {
    cursor: pointer;

    :deep(tbody tr):hover {
      background-color: var(--el-color-primary-light-9, #ecf5ff);
    }
  }

  .factor-tag {
    margin-right: 4px;
    margin-bottom: 2px;
  }

  // 复用 MetricCard 的视觉风格
  .metric-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 14px 16px;
    background: var(--el-fill-color-blank, #fff);
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    border-left-width: 3px;
    border-radius: 4px;
    min-height: 92px;
    margin-bottom: 16px;

    &--info {
      border-left-color: var(--el-color-primary, #409eff);
      .metric-card__number {
        color: var(--el-color-primary, #409eff);
      }
    }

    &--danger {
      border-left-color: var(--el-color-danger, #f56c6c);
      .metric-card__number {
        color: var(--el-color-danger, #f56c6c);
      }
    }

    &--warning {
      border-left-color: var(--el-color-warning, #e6a23c);
      .metric-card__number {
        color: var(--el-color-warning, #e6a23c);
      }
    }

    &--muted .metric-card__number {
      color: var(--el-text-color-placeholder, #c0c4cc);
    }

    &__label {
      font-size: 13px;
      color: var(--el-text-color-secondary, #606266);
    }

    &__value {
      display: flex;
      align-items: baseline;
      gap: 4px;
    }

    &__number {
      font-size: 26px;
      font-weight: 600;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
    }

    &__suffix {
      font-size: 13px;
      color: var(--el-text-color-secondary, #606266);
    }

    &__sub {
      font-size: 12px;
      color: var(--el-text-color-placeholder, #909399);
    }
  }

  .text-danger {
    color: var(--el-color-danger, #f56c6c);
  }
  .fw-600 {
    font-weight: 600;
  }
</style>
