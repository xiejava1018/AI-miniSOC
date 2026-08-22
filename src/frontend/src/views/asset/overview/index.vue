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

    <!-- 2. 分布区:4 个环图并排（类型/状态/重要度/风险），节省 1 行 + 1 gap -->
    <ElRow :gutter="12" class="chart-row">
      <ElCol :sm="12" :md="6">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">资产类型分布</span>
          </template>
          <ArtRingChart
            height="200px"
            :data="typeRingData"
            :show-legend="true"
            legend-position="right"
            center-text="类型"
          />
        </ElCard>
      </ElCol>
      <ElCol :sm="12" :md="6">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">在线状态分布</span>
          </template>
          <ArtRingChart
            height="200px"
            :data="statusRingData"
            :show-legend="true"
            legend-position="right"
            center-text="状态"
          />
        </ElCard>
      </ElCol>
      <ElCol :sm="12" :md="6">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">重要度分布</span>
          </template>
          <ArtRingChart
            height="200px"
            :data="criticalityRingData"
            :show-legend="true"
            legend-position="right"
            center-text="重要度"
          />
        </ElCard>
      </ElCol>
      <ElCol :sm="12" :md="6">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">资产风险分布</span>
            <span class="chart-subtitle">(F1.1 评分口径)</span>
          </template>
          <ArtRingChart
            height="200px"
            :data="riskRingData"
            :show-legend="true"
            legend-position="right"
            center-text="风险"
          />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 3. 近期评分上升最快（独立 1 行，全宽显示更舒服） -->
    <ElRow :gutter="12" class="top-row">
      <ElCol :span="24" class="top-col">
        <ElCard shadow="never" class="top-card">
          <template #header>
            <span class="chart-title">近期评分上升最快</span>
            <span class="chart-subtitle">(与首次评分对比 · Δ ≥ 5)</span>
          </template>
          <div class="top-table-wrap">
            <ElTable
              :data="risingRows"
              size="small"
              class="top-table"
              empty-text="近期无评分异动资产"
              @row-click="goDetailById"
            >
              <ElTableColumn prop="name" label="名称" min-width="150" show-overflow-tooltip>
                <template #default="{ row }">{{ row.name || row.ip }}</template>
              </ElTableColumn>
              <ElTableColumn prop="ip" label="IP" min-width="120" />
              <ElTableColumn label="当前分" width="90" align="right">
                <template #default="{ row }">
                  <ElTag :type="riskTagType(row.risk_score)" size="small" effect="dark">
                    {{ row.risk_score }}
                  </ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn label="Δ vs 首次" width="110" align="right">
                <template #default="{ row }">
                  <span class="text-danger fw-600">+{{ row.delta }}</span>
                </template>
              </ElTableColumn>
            </ElTable>
          </div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 4. Top 10 并列 -->
    <ElRow :gutter="16" class="top-row">
      <ElCol :sm="24" :md="12" class="top-col">
        <ElCard shadow="never" class="top-card">
          <template #header>
            <span class="chart-title">Top 10 高危资产</span>
            <span class="chart-subtitle">(综合风险分，D7 加权和)</span>
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
              <ElTableColumn prop="score" min-width="80" align="right">
                <template #header>
                  <span class="th-with-tip">
                    评分
                    <ElTooltip placement="top" effect="light">
                      <template #content>
                        <div class="d7-tooltip-content">{{ D7_TOOLTIP }}</div>
                      </template>
                      <el-icon class="th-tip-icon" :size="12"><QuestionFilled /></el-icon>
                    </ElTooltip>
                  </span>
                </template>
              </ElTableColumn>
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

    <!-- 5. P3/F3.2：生命周期预警（退役/升级建议列表） -->
    <ElRow :gutter="16" class="top-row">
      <ElCol :span="24" class="top-col">
        <ElCard shadow="never" class="top-card" v-loading="lifecycleLoading">
          <template #header>
            <span class="chart-title">生命周期预警</span>
            <span class="chart-subtitle">(EOL 已超期 / 30 天内 / 90 天内 + 保修临期)</span>
            <span class="lc-actions">
              <span v-if="lifecycle && lifecycle.unmatched_count > 0" class="lc-unmatched">
                {{ lifecycle.unmatched_count }} 台未匹配 EOL
              </span>
              <ElButton size="small" text :icon="Refresh" :loading="lifecycleLoading" @click="handleRefreshEol">
                重新匹配
              </ElButton>
            </span>
          </template>
          <div class="top-table-wrap">
            <ElTable
              :data="lifecycleRows"
              size="small"
              class="top-table"
              empty-text="暂无生命周期预警（EOL 90 天内与保修临期资产会出现在此）"
              :row-class-name="lifecycleRowClass"
              @row-click="goDetail"
            >
              <ElTableColumn label="预警" min-width="110">
                <template #default="{ row }">
                  <ElTag :type="row.tagType" size="small" effect="light">{{ row.tagLabel }}</ElTag>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="ip" label="IP" min-width="120" />
              <ElTableColumn prop="name" label="名称" min-width="150" show-overflow-tooltip />
              <ElTableColumn prop="os" label="操作系统" min-width="170" show-overflow-tooltip />
              <ElTableColumn label="日期" min-width="120">
                <template #default="{ row }">{{ row.dateText || '--' }}</template>
              </ElTableColumn>
              <ElTableColumn label="剩余" min-width="110">
                <template #default="{ row }">
                  <span :class="{ 'text-danger fw-600': row.days < 0 }">{{ row.daysText }}</span>
                </template>
              </ElTableColumn>
              <ElTableColumn label="口径" min-width="190" show-overflow-tooltip>
                <template #default="{ row }">
                  <template v-if="row.kind === 'eol'">
                    <span v-if="row.source === 'manual'">人工指定</span>
                    <span v-else>
                      {{ row.eol_ref || '参考表' }}
                      <ElTooltip v-if="row.eol_unverified" :content="row.eol_note || '该条目为预估口径，待人工核实'">
                        <ElTag type="warning" size="small" effect="plain">预估</ElTag>
                      </ElTooltip>
                    </span>
                  </template>
                  <span v-else>保修期</span>
                </template>
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
  import { Refresh, QuestionFilled } from '@element-plus/icons-vue'
  import {
    getAssetOverview,
    getRiskOverview,
    getLifecycleOverview,
    refreshLifecycleEol,
    type RiskOverview,
    type LifecycleOverview
  } from '@/api/asset'
  import { useDictStore } from '@/store/modules/dict'

  defineOptions({ name: 'AssetOverview' })

  const router = useRouter()
  const dictStore = useDictStore()

  const overview = ref<Api.Asset.AssetOverview | null>(null)
  const loadError = ref<string>('')

  // ---------- P3/F1.1：风险分布 + 上升最快（独立加载，失败静默不影响主区） ----------

  const riskOverview = ref<RiskOverview | null>(null)
  const loadRiskOverview = async () => {
    try {
      const res = await getRiskOverview()
      if (res.code === 200) riskOverview.value = res.data
    } catch {
      /* 静默 */
    }
  }

  const RISK_LABELS: Record<string, string> = {
    critical: '危险(80+)', high: '高危(60+)', medium: '中危(40+)', low: '低危(<40)', na: '未评分'
  }

  // D7 加权和口径说明（列 header tooltip），与后端 AssetOverviewService 一致
  const D7_TOOLTIP =
    '综合风险分（D7 加权和）:\n' +
    '· 关键资产（criticality=critical/core） +100\n' +
    '· 每个高危端口 ×20\n' +
    '· 每个未关闭事件 ×30\n' +
    '· 开放端口 ≥5 +10\n' +
    '· 每条 24h 告警 ×1\n' +
    '注: 与 F1.1 风险评分（Asset.risk_score 0–100）不同；F1.1 由 batch-score 落库快照'

  const riskRingData = computed(() => {
    const d = riskOverview.value?.distribution
    if (!d) return []
    return ['critical', 'high', 'medium', 'low', 'na']
      .filter((k) => d[k] > 0)
      .map((k) => ({ name: RISK_LABELS[k], value: d[k] }))
  })

  const risingRows = computed(() => riskOverview.value?.rising ?? [])

  const riskTagType = (s: number) =>
    s >= 80 ? 'danger' : s >= 60 ? 'warning' : s >= 40 ? 'warning' : 'success'

  const goDetailById = (row: { asset_id?: string; id?: string }) => {
    goDetail({ id: row.asset_id || row.id })
  }

  // ---------- P3/F3.2：生命周期预警（独立加载，失败静默） ----------

  const lifecycle = ref<LifecycleOverview | null>(null)
  const lifecycleLoading = ref(false)

  const loadLifecycle = async () => {
    lifecycleLoading.value = true
    try {
      const res = await getLifecycleOverview()
      if (res.code === 200) lifecycle.value = res.data
    } catch {
      /* 静默 */
    } finally {
      lifecycleLoading.value = false
    }
  }

  /** 手动重新匹配（参考表→资产 EOL 回填；人工覆盖不会被覆盖） */
  const handleRefreshEol = async () => {
    lifecycleLoading.value = true
    try {
      const res = await refreshLifecycleEol()
      if (res.code === 200) {
        const s = res.data?.stats || {}
        ElMessage.success(
          `EOL 匹配完成：命中 ${s.matched ?? 0}，无 OS 信息 ${s.no_os ?? 0}，未匹配 ${s.unmatched ?? 0}` +
            (s.kept_manual ? `，保留人工指定 ${s.kept_manual}` : '')
        )
        await loadLifecycle()
      } else {
        ElMessage.warning(res.msg || 'EOL 匹配失败')
      }
    } catch {
      ElMessage.error('EOL 匹配失败')
    } finally {
      lifecycleLoading.value = false
    }
  }

  /** 三档 EOL + 保修临期合并为一张表，按紧急度排序 */
  const lifecycleRows = computed(() => {
    const v = lifecycle.value
    if (!v) return []
    const rows: any[] = []
    const pushEol = (items: any[], tagLabel: string, tagType: string) => {
      items.forEach((i) =>
        rows.push({
          ...i,
          id: i.asset_id,
          kind: 'eol',
          tagLabel,
          tagType,
          dateText: i.eol_date,
          days: i.days_left,
          daysText: i.days_left < 0 ? `已过 ${Math.abs(i.days_left)} 天` : `${i.days_left} 天`
        })
      )
    }
    pushEol(v.eol_expired, 'EOL 已超期', 'danger')
    pushEol(v.eol_within_30d, 'EOL 30 天内', 'danger')
    pushEol(v.eol_within_90d, 'EOL 90 天内', 'warning')
    const pushWarranty = (items: any[], tagLabel: string, tagType: string) => {
      items.forEach((i) =>
        rows.push({
          ...i,
          id: i.asset_id,
          kind: 'warranty',
          tagLabel,
          tagType,
          dateText: i.warranty_end,
          days: i.warranty_days_left,
          daysText:
            i.warranty_days_left < 0
              ? `已过 ${Math.abs(i.warranty_days_left)} 天`
              : `${i.warranty_days_left} 天`
        })
      )
    }
    pushWarranty(v.warranty_expired, '保修已到期', 'danger')
    pushWarranty(v.warranty_within_30d, '保修 30 天内', 'warning')
    return rows
  })

  const lifecycleRowClass = ({ row }: { row: any }) => (row.days < 0 ? 'lc-row-expired' : '')

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
    loadRiskOverview()
    loadLifecycle()
  })
</script>

<style lang="scss" scoped>
  .asset-overview-page {
    padding: 10px 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .overview-alert {
    margin-bottom: 4px;
  }

  .kpi-row {
    flex-shrink: 0;
  }

  .chart-row,
  .top-row {
    flex-shrink: 0;
  }

  // 显式给 Top 行一个最小高度,让两列等高(8 行表格 ~ 300px，紧凑布局)
  .top-row {
    min-height: 320px;
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
      padding: 8px 10px;
    }

    :deep(.el-card__header) {
      padding: 8px 10px;
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
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary, #303133);
  }

  .th-with-tip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    cursor: help;
  }
  .th-tip-icon {
    color: var(--el-text-color-secondary, #909399);
    cursor: help;
  }
  :deep(.d7-tooltip-content) {
    white-space: pre-line;
    max-width: 320px;
    line-height: 1.6;
    text-align: left;
  }

  .chart-subtitle {
    margin-left: 6px;
    font-size: 11px;
    color: var(--el-text-color-secondary, #909399);
  }

  /* P3/F3.2 生命周期预警 */
  .lc-actions {
    float: right;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .lc-unmatched {
    font-size: 12px;
    color: var(--el-text-color-secondary, #909399);
  }

  :deep(.lc-row-expired) {
    background-color: var(--el-color-danger-light-9, #fef0f0);
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
    gap: 4px;
    padding: 10px 12px;
    background: var(--el-fill-color-blank, #fff);
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    border-left-width: 3px;
    border-radius: 4px;
    min-height: 78px;
    margin-bottom: 0;

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
