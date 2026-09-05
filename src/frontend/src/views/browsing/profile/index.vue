<template>
  <div class="bp-page art-full-height" v-loading="loading">
    <ElRow :gutter="12" class="bp-layout">
      <!-- 左栏：主体列表 -->
      <ElCol :span="6">
        <ElCard shadow="never" class="bp-subjects" :body-style="{ padding: '8px' }">
          <template #header>
            <div class="card-head">
              <span class="card-title">画像主体</span>
              <ElRadioGroup v-model="trafficFilter" size="small" @change="loadList">
                <ElRadioButton value="">全部</ElRadioButton>
                <ElRadioButton value="human">人类</ElRadioButton>
                <ElRadioButton value="machine">机器</ElRadioButton>
              </ElRadioGroup>
            </div>
          </template>
          <div
            v-for="item in subjects"
            :key="item.ip"
            class="subj"
            :class="{ on: item.ip === currentIp }"
            @click="selectSubject(item.ip)"
          >
            <div class="subj-ip">
              {{ item.ip }}
              <ElTag v-if="item.traffic_type === 'machine'" size="small" type="info" effect="plain">
                机器流量
              </ElTag>
              <ElTag v-else-if="item.traffic_type === 'mixed'" size="small" type="warning" effect="plain">
                混合
              </ElTag>
            </div>
            <div class="subj-meta">
              <span>{{ item.hostname || '未命名' }}</span>
              <span>{{ formatNumber(item.total) }} 次</span>
            </div>
            <div class="subj-tags">
              <ElTag
                v-for="t in item.tags || []"
                :key="t.name"
                size="small"
                effect="plain"
                :color="t.color"
                class="tag-chip"
              >
                {{ t.alias || t.name }}
              </ElTag>
            </div>
          </div>
          <ElEmpty v-if="!subjects.length && !loading" description="暂无画像数据（等待快照任务运行）" :image-size="60" />
        </ElCard>
      </ElCol>

      <!-- 右栏：画像详情 -->
      <ElCol :span="18">
        <template v-if="profile">
          <!-- 标识条 -->
          <ElCard shadow="never" class="bp-idbar" :body-style="{ padding: '12px 16px' }">
            <div class="idbar">
              <div>
                <div class="idbar-ip">{{ profile.ip }}</div>
                <div class="idbar-name">
                  {{ profile.asset?.name || profile.daily?.[0]?.hostname || '未知设备' }}
                  <span class="idbar-sub">
                    {{ profile.asset?.asset_type || '' }}
                    {{ profile.asset?.os_name || '' }}
                  </span>
                </div>
              </div>
              <div class="idbar-right">
                <ElTag effect="plain" type="info">窗口 {{ profile.days }} 天</ElTag>
                <ElTag effect="plain">访问 {{ formatNumber(profile.total) }}</ElTag>
                <ElTooltip content="置信度由数据量与查询截断情况计算（§9.7 偏差说明）">
                  <ElTag effect="plain" :type="profile.confidence >= 60 ? 'success' : 'warning'">
                    置信度 {{ profile.confidence }}
                  </ElTag>
                </ElTooltip>
                <ElTag v-if="profile.gap_days" effect="plain" type="danger">
                  {{ profile.gap_days }} 天数据缺失
                </ElTag>
                <ElButton
                  v-if="hasAuth('refresh')"
                  size="small"
                  :loading="refreshing"
                  @click="onRefresh"
                >
                  实时刷新
                </ElButton>
              </div>
            </div>
            <div class="idbar-watermark">本数据仅用于安全审计</div>
          </ElCard>

          <!-- 画像标签 -->
          <ElCard shadow="never" class="bp-card">
            <template #header>
              <span class="card-title">画像标签</span>
              <span class="card-sub">规则判定，每项附证据；机器流量主体已自动降权</span>
            </template>
            <div v-if="profile.tags?.length" class="tag-grid">
              <div v-for="t in profile.tags" :key="t.name" class="ptag" :style="{ '--tc': t.color }">
                <div class="ptag-name">
                  {{ t.name }}
                  <span v-if="t.alias" class="ptag-alias">→ {{ t.alias }}</span>
                </div>
                <div class="ptag-desc">{{ t.desc }}</div>
                <div class="ptag-evidence">{{ t.evidence }}</div>
              </div>
            </div>
            <ElEmpty v-else description="标签规则未命中 —— 行为强度或多样性不足" :image-size="60" />
          </ElCard>

          <!-- 24h 曲线 + 时段分布 -->
          <ElRow :gutter="12">
            <ElCol :span="14">
              <ElCard shadow="never" class="bp-card">
                <template #header><span class="card-title">24 小时活跃曲线</span></template>
                <div ref="hourRef" class="chart-box" style="height: 220px"></div>
              </ElCard>
            </ElCol>
            <ElCol :span="10">
              <ElCard shadow="never" class="bp-card">
                <template #header><span class="card-title">时段分布</span></template>
                <div ref="blockRef" class="chart-box" style="height: 220px"></div>
              </ElCard>
            </ElCol>
          </ElRow>

          <!-- 星期×小时热力图 -->
          <ElCard shadow="never" class="bp-card">
            <template #header>
              <span class="card-title">星期 × 小时 行为热力图</span>
              <span class="card-sub">颜色越深访问越密集（UTC+8）—— 行为节律核心视图</span>
            </template>
            <div ref="heatRef" class="chart-box" style="height: 240px"></div>
          </ElCard>

          <!-- 兴趣分类 + 趋势 -->
          <ElRow :gutter="12">
            <ElCol :span="10">
              <ElCard shadow="never" class="bp-card">
                <template #header><span class="card-title">访问习惯构成</span></template>
                <div ref="catRef" class="chart-box" style="height: 220px"></div>
              </ElCard>
            </ElCol>
            <ElCol :span="14">
              <ElCard shadow="never" class="bp-card">
                <template #header>
                  <span class="card-title">多日趋势</span>
                  <span class="card-sub">灰色段 = 数据缺失（Loki 窗口外，非零流量）</span>
                </template>
                <div ref="trendRef" class="chart-box" style="height: 220px"></div>
              </ElCard>
            </ElCol>
          </ElRow>

          <!-- 域名 TOP -->
          <ElCard shadow="never" class="bp-card">
            <template #header><span class="card-title">访问域名 TOP 20</span></template>
            <ElTable :data="profile.top_domains || []" size="small" max-height="360">
              <ElTableColumn prop="domain" label="域名" min-width="220" show-overflow-tooltip />
              <ElTableColumn prop="category" label="分类" width="110" />
              <ElTableColumn prop="visits" label="访问量" width="100">
                <template #default="{ row }">{{ formatNumber(row.visits) }}</template>
              </ElTableColumn>
              <ElTableColumn prop="share" label="占比" width="90">
                <template #default="{ row }">{{ row.share }}%</template>
              </ElTableColumn>
            </ElTable>
          </ElCard>
        </template>
        <ElCard v-else shadow="never" class="bp-card">
          <ElEmpty description="选择左侧主体查看画像，或等待快照任务生成数据" />
        </ElCard>
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
  import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
  import { ElMessage } from 'element-plus'
  import { echarts } from '@/plugins/echarts'
  import { useAuth } from '@/hooks/core/useAuth'
  import {
    getBehaviorProfiles,
    getBehaviorProfile,
    getBehaviorTrend,
    refreshBehaviorProfile
  } from '@/api/behaviorProfile'

  const { hasAuth } = useAuth()

  const loading = ref(false)
  const refreshing = ref(false)
  const trafficFilter = ref('')
  const subjects = ref<any[]>([])
  const currentIp = ref('')
  const profile = ref<any>(null)
  const trend = ref<any[]>([])

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
  const WD = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

  let charts: echarts.ECharts[] = []

  const formatNumber = (n: number) => Number(n || 0).toLocaleString('en-US')

  // ── 数据加载 ──────────────────────────────

  const loadList = async () => {
    loading.value = true
    try {
      const res = await getBehaviorProfiles(
        trafficFilter.value ? { traffic_type: trafficFilter.value } : undefined
      )
      subjects.value = res?.data?.items || []
      if (!currentIp.value && subjects.value.length) {
        await selectSubject(subjects.value[0].ip)
      }
    } finally {
      loading.value = false
    }
  }

  const selectSubject = async (ip: string) => {
    currentIp.value = ip
    loading.value = true
    try {
      const [p, t] = await Promise.all([
        getBehaviorProfile(ip, { days: 7 }),
        getBehaviorTrend(ip, { days: 30 })
      ])
      profile.value = p?.data || null
      trend.value = t?.data?.items || []
      await nextTick()
      renderCharts()
    } finally {
      loading.value = false
    }
  }

  const onRefresh = async () => {
    refreshing.value = true
    try {
      await refreshBehaviorProfile(currentIp.value)
      ElMessage.success('已触发当日实时重算')
      await selectSubject(currentIp.value)
    } catch {
      ElMessage.warning('实时重算失败（可能无当日数据）')
    } finally {
      refreshing.value = false
    }
  }

  // ── 图表渲染 ──────────────────────────────

  const disposeCharts = () => {
    charts.forEach((c) => c.dispose())
    charts = []
  }

  const makeChart = (ref: any, option: any) => {
    if (!ref) return
    const inst = echarts.init(ref)
    inst.setOption(option)
    charts.push(inst)
  }

  const renderCharts = () => {
    disposeCharts()
    if (!profile.value) return
    const p = profile.value

    // 24h 曲线
    makeChart(document.querySelector('.bp-page .chart-box') as any, null) // noop guard
    const hourEl = document.querySelectorAll('.bp-page .chart-box')[0] as HTMLElement
    makeChart(hourEl, {
      grid: { left: 40, right: 12, top: 20, bottom: 24 },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')),
        axisLabel: { fontSize: 10 }
      },
      yAxis: { type: 'value' },
      tooltip: { trigger: 'axis' },
      series: [
        {
          type: 'bar',
          data: p.by_hour.map((v: number, h: number) => ({
            value: v,
            itemStyle: { color: BLOCK_COLORS[BLOCK_ORDER[blockIndexOf(h)]] }
          }))
        }
      ]
    })

    // 时段分布（7 段）
    const blockEl = document.querySelectorAll('.bp-page .chart-box')[1] as HTMLElement
    const blockData = BLOCK_ORDER.map((b) => ({
      name: b,
      value: p.by_block?.[b] ?? 0,
      itemStyle: { color: BLOCK_COLORS[b] }
    }))
    makeChart(blockEl, {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['38%', '68%'], data: blockData, label: { show: false } }]
    })

    // 星期×小时热力图
    const heatEl = document.querySelectorAll('.bp-page .chart-box')[2] as HTMLElement
    const heatData: [number, number, number][] = []
    let hMax = 1
    ;(p.wd_hour || []).forEach((row: number[], i: number) =>
      row.forEach((v, h) => {
        heatData.push([h, i, v])
        if (v > hMax) hMax = v
      })
    )
    makeChart(heatEl, {
      grid: { left: 44, right: 12, top: 10, bottom: 40 },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')),
        axisLabel: { fontSize: 9 }
      },
      yAxis: { type: 'category', data: WD, axisLabel: { fontSize: 10 } },
      tooltip: {
        formatter: (pr: any) => `${WD[pr.value[1]]} ${String(pr.value[0]).padStart(2, '0')}:00 — ${pr.value[2]} 次`
      },
      visualMap: {
        min: 0,
        max: hMax,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemWidth: 10,
        itemHeight: 60,
        inRange: { color: ['#f1f3f5', '#1971c4'] },
        textStyle: { fontSize: 9 }
      },
      series: [
        {
          type: 'heatmap',
          data: heatData,
          label: { show: false }
        }
      ]
    })

    // 兴趣分类
    const catEl = document.querySelectorAll('.bp-page .chart-box')[3] as HTMLElement
    const catData = Object.entries(p.cat_share || {}).map(([k, v]) => ({ name: k, value: v }))
    makeChart(catEl, {
      tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['38%', '68%'], data: catData, label: { show: false } }]
    })

    // 多日趋势（gap 日 = null → 断线）
    const trendEl = document.querySelectorAll('.bp-page .chart-box')[4] as HTMLElement
    makeChart(trendEl, {
      grid: { left: 44, right: 12, top: 20, bottom: 24 },
      xAxis: {
        type: 'category',
        data: trend.value.map((i) => i.profile_date?.slice(5) || ''),
        axisLabel: { fontSize: 9 }
      },
      yAxis: { type: 'value' },
      tooltip: {
        trigger: 'axis',
        formatter: (params: any) => {
          const idx = params[0]?.dataIndex
          const item = trend.value[idx]
          if (!item) return ''
          if (item.status === 'gap') return `${item.profile_date}<br/>数据缺失（Loki 窗口外）`
          return `${item.profile_date}<br/>访问 ${formatNumber(item.total)} · 主动行为 ${item.act_ratio}%`
        }
      },
      series: [
        {
          type: 'bar',
          data: trend.value.map((i) => (i.status === 'gap' ? null : i.total)),
          itemStyle: { color: '#1971c4' }
        }
      ]
    })
  }

  const blockIndexOf = (hour: number) => {
    if (hour < 6) return 0
    if (hour < 9) return 1
    if (hour < 12) return 2
    if (hour < 14) return 3
    if (hour < 18) return 4
    if (hour < 21) return 5
    return 6
  }

  const onResize = () => charts.forEach((c) => c.resize())

  onMounted(async () => {
    await loadList()
    window.addEventListener('resize', onResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    disposeCharts()
  })
</script>

<script lang="ts">
  export default {
    name: 'BehaviorProfile'
  }
</script>

<style scoped lang="scss">
  .bp-page {
    padding: 12px;

    .bp-layout {
      height: 100%;
    }

    .bp-card {
      margin-bottom: 12px;
    }

    .card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
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

    // 主体列表
    .subj {
      padding: 10px;
      margin-bottom: 6px;
      cursor: pointer;
      border: 1px solid transparent;
      border-radius: 8px;

      &:hover {
        background: var(--el-fill-color-light);
      }

      &.on {
        background: var(--el-color-primary-light-9);
        border-color: var(--el-color-primary-light-7);
      }

      .subj-ip {
        display: flex;
        gap: 6px;
        align-items: center;
        font-family: ui-monospace, monospace;
        font-weight: 600;
        font-size: 13px;
      }

      .subj-meta {
        display: flex;
        justify-content: space-between;
        margin-top: 2px;
        font-size: 11px;
        color: var(--el-text-color-secondary);
      }

      .subj-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 6px;
      }
    }

    .tag-chip {
      border: none;
      color: #fff !important;
    }

    // 标识条
    .idbar {
      position: relative;
      display: flex;
      justify-content: space-between;
      align-items: center;

      .idbar-ip {
        font-family: ui-monospace, monospace;
        font-size: 18px;
        font-weight: 700;
        color: var(--el-color-primary);
      }

      .idbar-name {
        font-size: 13px;

        .idbar-sub {
          margin-left: 6px;
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }

      .idbar-right {
        display: flex;
        gap: 8px;
        align-items: center;
      }

      .idbar-watermark {
        position: absolute;
        top: -4px;
        right: 0;
        font-size: 10px;
        color: var(--el-text-color-placeholder);
        transform: rotate(0deg);
      }
    }

    // 标签网格
    .tag-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 10px;
    }

    .ptag {
      padding: 10px 12px;
      cursor: default;
      background: color-mix(in srgb, var(--tc) 8%, transparent);
      border-left: 3px solid var(--tc);
      border-radius: 6px;

      .ptag-name {
        font-weight: 600;
        font-size: 13px;
        color: var(--tc);
      }

      .ptag-alias {
        font-size: 12px;
        color: var(--el-text-color-regular);
      }

      .ptag-desc {
        margin-top: 2px;
        font-size: 12px;
      }

      .ptag-evidence {
        margin-top: 4px;
        font-size: 11px;
        color: var(--el-text-color-secondary);
      }
    }
  }
</style>
