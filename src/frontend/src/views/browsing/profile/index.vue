<template>
  <div class="bp-ov-page art-full-height" v-loading="loading">
    <!-- 群体 KPI（§4.1 #1） -->
    <ElRow :gutter="12" class="ov-kpis">
      <ElCol :span="6">
        <ElCard shadow="never" :body-style="{ padding: '14px 16px' }">
          <div class="kpi-v">{{ overview?.subject_total ?? '—' }}</div>
          <div class="kpi-l">画像主体总数</div>
          <div class="kpi-s">有上网行为快照的 IP / 设备</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" :body-style="{ padding: '14px 16px' }">
          <div class="kpi-v">{{ overview?.traffic_type?.human ?? '—' }}</div>
          <div class="kpi-l">人类主体</div>
          <div class="kpi-s">
            机器 {{ overview?.traffic_type?.machine ?? 0 }} · 混合
            {{ overview?.traffic_type?.mixed ?? 0 }}
          </div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" :body-style="{ padding: '14px 16px' }">
          <div class="kpi-v" :class="{ warn: (overview?.data_freshness?.snapshot_days ?? 0) < 4 }">
            {{ overview?.data_freshness?.snapshot_days ?? '—' }} 天
          </div>
          <div class="kpi-l">快照积累</div>
          <div class="kpi-s">
            最新 {{ overview?.data_freshness?.latest_date || '—' }} · ≥4 天方可判异常
          </div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" :body-style="{ padding: '14px 16px' }">
          <div
            class="kpi-v"
            :class="{
              dang: (overview?.confidence_dist?.low ?? 0) > (overview?.subject_total ?? 0) / 2
            }"
          >
            {{ overview?.confidence_dist?.low ?? '—' }}
          </div>
          <div class="kpi-l">低置信度主体</div>
          <div class="kpi-s">数据量不足，画像结论仅作存在性证据</div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 人设分布 + 兴趣构成 + 时段占比（§4.1 #2 #3 #4） -->
    <ElRow :gutter="12">
      <ElCol :span="8">
        <ElCard shadow="never" class="ov-card">
          <template #header>
            <span class="card-title">人设群体分布</span>
            <span class="card-sub">全网画像标签命中数（每主体取最近快照）</span>
          </template>
          <div v-if="tagRows.length" class="tag-bars">
            <div v-for="t in tagRows" :key="t.name" class="tb-row" @click="filterByTag(t.name)">
              <span class="tb-name">{{ t.name }}</span>
              <div class="tb-track">
                <div
                  class="tb-fill"
                  :style="{ width: tagPct(t.count), background: tagColor(t.name) }"
                />
              </div>
              <span class="tb-v">{{ t.count }} 个</span>
            </div>
          </div>
          <ElEmpty v-else description="暂无标签命中（等待快照积累）" :image-size="60" />
        </ElCard>
      </ElCol>
      <ElCol :span="8">
        <ElCard shadow="never" class="ov-card">
          <template #header><span class="card-title">全网兴趣构成</span></template>
          <div ref="catRef" class="chart-box" style="height: 224px"></div>
        </ElCard>
      </ElCol>
      <ElCol :span="8">
        <ElCard shadow="never" class="ov-card">
          <template #header>
            <span class="card-title">时段占比</span>
            <span class="card-sub">7 时段</span>
          </template>
          <div ref="blockRef" class="chart-box" style="height: 224px"></div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 画像主体列表（§4.1 #6，L1 → L2 主入口） -->
    <ElCard shadow="never" class="ov-card">
      <template #header>
        <div class="list-head">
          <div>
            <span class="card-title">画像主体列表</span>
            <span class="card-sub"
              >共 {{ filteredSubjects.length }} 个主体 · 点击任意行进入单 IP 画像详情</span
            >
          </div>
          <div class="list-filters">
            <ElRadioGroup v-model="trafficFilter" size="small" @change="applyFilter">
              <ElRadioButton value="">全部</ElRadioButton>
              <ElRadioButton value="human">人类</ElRadioButton>
              <ElRadioButton value="machine">机器</ElRadioButton>
            </ElRadioGroup>
            <ElSelect
              v-model="confFilter"
              size="small"
              style="width: 110px"
              placeholder="置信度"
              @change="applyFilter"
            >
              <ElOption value="" label="置信度全部" />
              <ElOption value="high" label="≥60" />
              <ElOption value="low" label="<60" />
            </ElSelect>
            <ElInput
              v-model="search"
              size="small"
              style="width: 180px"
              placeholder="IP / 主机名模糊搜索"
              clearable
              @input="applyFilter"
            />
          </div>
        </div>
      </template>
      <ElTable
        :data="pagedSubjects"
        size="small"
        @row-click="(row: any) => goDetail(row.ip)"
        @sort-change="onSortChange"
      >
        <template #empty>
          <ElEmpty
            :description="
              subjects.length
                ? '当前筛选条件下无匹配主体'
                : '暂无画像快照（等待快照任务运行，或检查接口权限 admin/auditor）'
            "
            :image-size="70"
          />
        </template>
        <ElTableColumn prop="ip" label="IP" width="140" sortable="custom">
          <template #default="{ row }">
            <span class="cell-ip">{{ row.ip }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="hostname" label="主机名 / 资产名" min-width="150">
          <template #default="{ row }">{{ row.hostname || '未命名' }}</template>
        </ElTableColumn>
        <ElTableColumn prop="profile_date" label="快照日" width="100" />
        <ElTableColumn prop="total" label="访问量" width="100" sortable="custom">
          <template #default="{ row }">{{ formatNumber(row.total) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="traffic_type" label="流量类型" width="90">
          <template #default="{ row }">
            <ElTag
              size="small"
              :type="
                row.traffic_type === 'machine'
                  ? 'info'
                  : row.traffic_type === 'mixed'
                    ? 'warning'
                    : 'success'
              "
              effect="plain"
            >
              {{
                row.traffic_type === 'machine'
                  ? '机器'
                  : row.traffic_type === 'mixed'
                    ? '混合'
                    : '人类'
              }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="confidence" label="置信度" width="90" sortable="custom">
          <template #default="{ row }">
            <b
              :style="{
                color:
                  row.confidence >= 60 ? '#40c057' : row.confidence >= 20 ? '#f59f00' : '#adb5bd'
              }"
            >
              {{ row.confidence }}
            </b>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="night_share" label="深夜占比" width="90" sortable="custom">
          <template #default="{ row }">{{ row.night_share }}%</template>
        </ElTableColumn>
        <ElTableColumn label="画像标签" min-width="200">
          <template #default="{ row }">
            <template v-if="row.traffic_type !== 'machine'">
              <ElTag
                v-for="t in row.tags || []"
                :key="t.name"
                size="small"
                effect="plain"
                :color="t.color"
                class="tag-chip"
              >
                {{ t.alias || t.name }}
              </ElTag>
            </template>
            <span v-else class="dim">机器流量（标签已折叠）</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="" width="110">
          <template #default>
            <ElLink type="primary">查看画像 →</ElLink>
          </template>
        </ElTableColumn>
      </ElTable>
      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="filteredSubjects.length"
          layout="total, prev, pager, next"
          size="small"
        />
      </div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { echarts } from '@/plugins/echarts'
  import { getBehaviorOverview, getBehaviorProfiles } from '@/api/behaviorProfile'

  const route = useRoute()
  const router = useRouter()

  const loading = ref(false)
  const overview = ref<any>(null)
  const subjects = ref<any[]>([])
  const trafficFilter = ref('')
  const confFilter = ref('')
  const search = ref('')
  const tagFilter = ref('')
  const sortProp = ref('total')
  const sortOrder = ref('descending')
  const page = ref(1)
  const pageSize = 15

  const catRef = ref<HTMLElement>()
  const blockRef = ref<HTMLElement>()

  const BLOCK_ORDER = ['深夜', '早晨', '上午', '午间', '下午', '傍晚', '夜间']
  const BLOCK_COLORS: Record<string, string> = {
    深夜: '#4c6ef5',
    早晨: '#22b8cf',
    上午: '#51cf66',
    午间: '#fcc419',
    下午: '#ff922b',
    傍晚: '#ff6b6b',
    夜间: '#845ef7'
  }
  const TAG_COLORS: Record<string, string> = {
    夜猫子: '#4c6ef5',
    作息极规律: '#2f9e44',
    早起鸟: '#22b8cf',
    轻度熬夜: '#748ffc',
    作息发散: '#f59f00',
    间歇上线型: '#868e96',
    夜间活跃型: '#845ef7',
    周末战士: '#e8590c',
    典型打工人: '#1971c2',
    码农: '#1971c2',
    下载机: '#5c7cfa',
    追剧党: '#e64980',
    学生党: '#51cf66',
    兴趣广泛: '#2f9e44',
    'AI 重度用户': '#7048e8',
    'AI 尝鲜者': '#7048e8'
  }

  let charts: echarts.ECharts[] = []

  const formatNumber = (n: number) => Number(n || 0).toLocaleString('en-US')

  const tagRows = computed(() => (overview.value?.tag_distribution || []).slice(0, 12))
  const tagMax = computed(() => Math.max(1, ...tagRows.value.map((t: any) => t.count)))
  const tagPct = (c: number) => `${Math.max((c / tagMax.value) * 100, 3).toFixed(1)}%`
  const tagColor = (name: string) => TAG_COLORS[name] || '#868e96'

  // ── 列表筛选（§4.2） ──────────────────────────────

  const filteredSubjects = computed(() => {
    let rows = [...subjects.value]
    if (trafficFilter.value) rows = rows.filter((r) => r.traffic_type === trafficFilter.value)
    if (confFilter.value === 'high') rows = rows.filter((r) => r.confidence >= 60)
    else if (confFilter.value === 'low') rows = rows.filter((r) => r.confidence < 60)
    if (tagFilter.value) {
      rows = rows.filter((r) =>
        (r.tags || []).some((t: any) => t.name === tagFilter.value || t.alias === tagFilter.value)
      )
    }
    if (search.value) {
      const q = search.value.toLowerCase()
      rows = rows.filter(
        (r) => r.ip?.toLowerCase().includes(q) || (r.hostname || '').toLowerCase().includes(q)
      )
    }
    const prop = sortProp.value as any
    const dir = sortOrder.value === 'ascending' ? 1 : -1
    rows.sort((a, b) => ((a[prop] ?? 0) > (b[prop] ?? 0) ? dir : -dir))
    return rows
  })

  const pagedSubjects = computed(() =>
    filteredSubjects.value.slice((page.value - 1) * pageSize, page.value * pageSize)
  )

  const applyFilter = () => {
    page.value = 1
  }

  const onSortChange = ({ prop, order }: { prop: string; order: string | null }) => {
    if (order) {
      sortProp.value = prop
      sortOrder.value = order
    }
  }

  const filterByTag = (name: string) => {
    tagFilter.value = tagFilter.value === name ? '' : name
    search.value = ''
    trafficFilter.value = ''
    confFilter.value = ''
    page.value = 1
  }

  // ── 导航 ──────────────────────────────

  const goDetail = (ip: string) => {
    router.push(`/browsing/profile/detail/${encodeURIComponent(ip)}`)
  }

  // ── 图表 ──────────────────────────────

  const disposeCharts = () => {
    charts.forEach((c) => c.dispose())
    charts = []
  }

  const makeChart = (el: HTMLElement | undefined | null, option: any, retry = 5) => {
    if (!el) return
    if (!el.clientWidth || !el.clientHeight) {
      if (retry > 0) setTimeout(() => makeChart(el, option, retry - 1), 120)
      return
    }
    const inst = echarts.init(el)
    inst.setOption(option)
    charts.push(inst)
  }

  const renderCharts = () => {
    disposeCharts()
    const o = overview.value
    if (!o) return

    // 兴趣构成饼
    makeChart(catRef.value, {
      tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10 } },
      series: [
        {
          type: 'pie',
          radius: ['38%', '68%'],
          data: Object.entries(o.global_cat_share || {}).map(([k, v]) => ({ name: k, value: v })),
          label: { show: false }
        }
      ]
    })

    // 时段占比
    makeChart(blockRef.value, {
      tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
      series: [
        {
          type: 'pie',
          radius: ['38%', '68%'],
          data: BLOCK_ORDER.map((b) => ({
            name: b,
            value: o.global_by_block?.[b] ?? 0,
            itemStyle: { color: BLOCK_COLORS[b] }
          })),
          label: { show: false }
        }
      ]
    })
  }

  const onResize = () => charts.forEach((c) => c.resize())

  onMounted(async () => {
    // ?ip= 入口兼容（§3.2）：重定向到 L2 详情路由
    const qip = (route.query.ip || route.query.agent_ip) as string | undefined
    if (qip) {
      router.replace(`/browsing/profile/detail/${encodeURIComponent(qip)}`)
      return
    }
    loading.value = true
    try {
      const [ov, list] = await Promise.all([
        getBehaviorOverview({ days: 7 }).catch(() => null),
        getBehaviorProfiles({ limit: 500 }).catch(() => null)
      ])
      overview.value = ov?.data || null
      subjects.value = list?.data?.items || []
      await nextTick()
      renderCharts()
    } finally {
      loading.value = false
    }
    window.addEventListener('resize', onResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    disposeCharts()
  })
</script>

<script lang="ts">
  export default {
    name: 'BehaviorProfileOverview'
  }
</script>

<style scoped lang="scss">
  .bp-ov-page {
    // 单一滚动容器：.art-full-height 的固定 height + flex column 会把多行
    // ElCard 当 flex 项挤压（主体列表被压成一条线，缩放 50% 才恢复）。
    // 改成随内容伸展，滚动交给外层文档——与 asset/overview/reconciliation
    // /compliance/detail 同款处理。
    height: auto;
    min-height: var(--art-full-height);
    position: relative;
    padding: 12px;

    .ov-kpis {
      margin-bottom: 12px;
    }

    .kpi-v {
      font-size: 24px;
      font-weight: 700;
      font-family: ui-monospace, monospace;
      color: var(--el-color-primary);

      &.warn {
        color: #e8590c;
      }

      &.dang {
        color: #c92a2a;
      }
    }

    .kpi-l {
      margin-top: 4px;
      font-size: 13px;
    }

    .kpi-s {
      margin-top: 2px;
      font-size: 11px;
      color: var(--el-text-color-secondary);
    }

    .ov-card {
      margin-bottom: 12px;
    }

    .card-title {
      font-weight: 600;
      font-size: 14px;
    }

    .card-sub {
      margin-left: 8px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }

    .chart-box {
      width: 100%;
    }

    // 人设分布条形
    .tag-bars {
      // 人设分布区固定高度，与同排兴趣/时段饼图的 chart-box 同高
      // 饼图卡与人设卡 body 总高均为 264px（chart-box 224px + ElCard body 上下 padding 20px）
      height: 224px;
      overflow-y: auto;

      .tb-row {
        display: flex;
        gap: 10px;
        align-items: center;
        margin-bottom: 7px;
        cursor: pointer;

        &:hover .tb-name {
          color: var(--el-color-primary);
        }
      }

      .tb-name {
        width: 88px;
        flex-shrink: 0;
        font-size: 12px;
        text-align: right;
        color: var(--el-text-color-regular);
      }

      .tb-track {
        flex: 1;
        height: 16px;
        min-width: 40px;
        overflow: hidden;
        background: var(--el-fill-color-light);
        border-radius: 3px;
      }

      .tb-fill {
        height: 100%;
        border-radius: 3px;
      }

      .tb-v {
        width: 48px;
        flex-shrink: 0;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }

    .list-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;

      .list-filters {
        display: flex;
        gap: 8px;
        align-items: center;
      }
    }

    .cell-ip {
      font-family: ui-monospace, monospace;
      font-weight: 600;
    }

    .tag-chip {
      margin-right: 3px;
      border: none;
      color: #fff !important;
    }

    .dim {
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }

    :deep(.el-table__row) {
      cursor: pointer;
    }

    .pager {
      display: flex;
      justify-content: flex-end;
      margin-top: 10px;
    }

  }
</style>
