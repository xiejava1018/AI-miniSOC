<template>
  <div class="browsing-stat-page art-full-height" v-loading="loading">
    <!-- 顶部：时间范围切换 -->
    <div class="top-bar">
      <span class="title">行为统计概览</span>
      <ElRadioGroup v-model="hours" size="small" @change="loadData">
        <ElRadioButton :value="1">最近1小时</ElRadioButton>
        <ElRadioButton :value="24">最近24小时</ElRadioButton>
        <ElRadioButton :value="48">最近2天</ElRadioButton>
      </ElRadioGroup>
      <span class="range-tip">受 Loki 查询限制，单次最多统计2天</span>
    </div>

    <!-- 概览卡片 -->
    <ElRow :gutter="12" class="summary-row">
      <ElCol :span="4" v-for="card in summaryCards" :key="card.label">
        <ElCard shadow="never" class="stat-card" :body-style="{ padding: '12px' }">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 访问域名 Top10 + 应用类型分布 + IP 日志量 Top10 -->
    <ElRow :gutter="12">
      <ElCol :span="8">
        <ElCard shadow="never" class="chart-card">
          <template #header><span class="card-title">访问域名 Top10</span></template>
          <div ref="domainRef" class="chart-box" style="height: 230px"></div>
        </ElCard>
      </ElCol>
      <ElCol :span="8">
        <ElCard shadow="never" class="chart-card">
          <template #header><span class="card-title">应用类型分布</span></template>
          <div ref="apptypeRef" class="chart-box" style="height: 230px"></div>
        </ElCard>
      </ElCol>
      <ElCol :span="8">
        <ElCard shadow="never" class="chart-card">
          <template #header><span class="card-title">IP 日志量 Top10</span></template>
          <div ref="ipRef" class="chart-box" style="height: 230px"></div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 24h 时段热力图 + 凌晨活跃IP -->
    <ElRow :gutter="12">
      <ElCol :span="15">
        <ElCard shadow="never" class="chart-card">
          <template #header>
            <span class="card-title">24小时时段分布热力图（最近2天）</span>
            <span class="card-sub">颜色越深=日志量越大，凌晨列(2-5点)深色为异常</span>
          </template>
          <div ref="heatRef" class="chart-box" style="height: 220px"></div>
        </ElCard>
      </ElCol>
      <ElCol :span="9">
        <ElCard shadow="never" class="chart-card">
          <template #header><span class="card-title">凌晨活跃 IP Top（2-5点/2天）</span></template>
          <div ref="nightRef" class="chart-box" style="height: 220px"></div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 日志量趋势（每小时）-->
    <ElCard shadow="never" class="chart-card">
      <template #header><span class="card-title">日志量趋势（每小时）</span></template>
      <div ref="trendRef" class="chart-box" style="height: 180px"></div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
  import { ElMessage } from 'element-plus'
  import { echarts, type EChartsOption } from '@/plugins/echarts'
  import { getBrowsingStatistics } from '@/api/browsing'

  const loading = ref(false)
  const hours = ref(24)
  const data = ref<any>({})

  // 图表实例
  let trendChart: any = null
  let ipChart: any = null
  let domainChart: any = null
  let apptypeChart: any = null
  let heatChart: any = null
  let nightChart: any = null
  const trendRef = ref<HTMLElement>()
  const ipRef = ref<HTMLElement>()
  const domainRef = ref<HTMLElement>()
  const apptypeRef = ref<HTMLElement>()
  const heatRef = ref<HTMLElement>()
  const nightRef = ref<HTMLElement>()

  // 概览卡片
  const summaryCards = computed(() => {
    const s = data.value?.summary || {}
    const fmt = (n: number) => (n >= 10000 ? `${(n / 10000).toFixed(1)}万` : `${n || 0}`)
    return [
      { label: '日志总量', value: fmt(s.total || 0), color: 'var(--el-color-primary)' },
      { label: '活跃 IP', value: s.ip_count || 0, color: '#67C23A' },
      { label: '访问域名', value: s.domain_count || 0, color: '#E6A23C' },
      { label: '隧道/穿透', value: s.tunnel_count || 0, color: '#F56C6C' },
      { label: '异常事件', value: s.event_count || 0, color: '#F56C6C' },
      { label: '时间范围', value: `${hours.value}h`, color: '#909399' }
    ]
  })

  const loadData = async () => {
    loading.value = true
    try {
      const res = await getBrowsingStatistics(hours.value)
      if (res.code === 200 || res.code === 201) {
        data.value = res.data
        await nextTick()
        renderCharts()
      } else {
        ElMessage.error(res.message || '加载失败')
      }
    } catch (e) {
      console.error(e)
      ElMessage.error('加载统计数据失败')
    } finally {
      loading.value = false
    }
  }

  const renderCharts = () => {
    renderTrend()
    renderBar(ipRef.value, ipChart, data.value.top_ips, '#409EFF', (v: number) => v.toLocaleString())
    renderBar(domainRef.value, domainChart, data.value.top_domains, '#67C23A', (v: number) => v.toLocaleString())
    renderApptype()
    renderHeatmap()
    renderNight()
  }

  const renderTrend = () => {
    if (!trendRef.value) return
    if (trendChart) trendChart.dispose()
    trendChart = echarts.init(trendRef.value)
    const trend = data.value.trend || []
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: trend.map((p: any) => p.ts), axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value', name: '条数' },
      series: [{
        type: 'line', data: trend.map((p: any) => p.count), smooth: true,
        areaStyle: { opacity: 0.2 }, itemStyle: { color: '#409EFF' }
      }]
    } as EChartsOption)
  }

  const renderBar = (el: any, chart: any, items: any[], color: string, fmt: Function) => {
    if (!el) return
    if (chart) chart.dispose()
    chart = echarts.init(el)
    const rows = (items || []).slice().reverse()  // 横向柱状倒序
    chart.setOption({
      tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>${fmt(p[0].value)} 次` },
      grid: { left: 10, right: 30, top: 10, bottom: 10, containLabel: true },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: rows.map((r: any) => r.key), axisLabel: { fontSize: 11 } },
      series: [{ type: 'bar', data: rows.map((r: any) => r.count), itemStyle: { color } }]
    } as EChartsOption)
    // 保存引用（横向柱状用同一变量）
    if (el === ipRef.value) ipChart = chart
    if (el === domainRef.value) domainChart = chart
  }

  const renderApptype = () => {
    if (!apptypeRef.value) return
    if (apptypeChart) apptypeChart.dispose()
    apptypeChart = echarts.init(apptypeRef.value)
    const dist = (data.value.apptype_dist || []).map((d: any) => ({ name: d.name, value: d.value }))
    apptypeChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 11 } },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['35%', '50%'],
        data: dist, label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } }
      }]
    } as EChartsOption)
  }

  const renderHeatmap = () => {
    if (!heatRef.value) return
    if (heatChart) heatChart.dispose()
    heatChart = echarts.init(heatRef.value)
    const hm = data.value.heatmap || { dates: [], hours: [], data: [] }
    const hours = hm.hours || []
    const dates = hm.dates || []
    const maxVal = hm.data.length ? Math.max(...hm.data.map((d: any) => d[2])) : 100
    heatChart.setOption({
      tooltip: { position: 'top', formatter: (p: any) => `${dates[p.value[1]]} ${p.value[0]}点<br/>${p.value[2]} 条` },
      grid: { left: 50, right: 30, top: 30, bottom: 70 },
      xAxis: { type: 'category', data: hours.map((h: number) => `${h}`), name: '小时', splitArea: { show: true }, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'category', data: dates, name: '日期', splitArea: { show: true } },
      visualMap: {
        min: 0, max: maxVal, calculable: true, orient: 'horizontal', left: 'center', bottom: 5,
        inRange: { color: ['#e0f3f8', '#abd9e9', '#74add1', '#4575b4', '#d73027'] }
      },
      series: [{
        type: 'heatmap', data: hm.data,
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } }
      }]
    } as EChartsOption)
  }

  const renderNight = () => {
    if (!nightRef.value) return
    if (nightChart) nightChart.dispose()
    nightChart = echarts.init(nightRef.value)
    const rows = (data.value.night_ips || []).slice().reverse()
    nightChart.setOption({
      tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}<br/>${p[0].value} 条` },
      grid: { left: 10, right: 30, top: 10, bottom: 10, containLabel: true },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: rows.map((r: any) => r.ip), axisLabel: { fontSize: 11 } },
      series: [{ type: 'bar', data: rows.map((r: any) => r.count), itemStyle: { color: '#F56C6C' } }]
    } as EChartsOption)
  }

  // 窗口缩放自适应
  const handleResize = () => {
    trendChart?.resize(); ipChart?.resize(); domainChart?.resize(); apptypeChart?.resize()
    heatChart?.resize(); nightChart?.resize()
  }

  onMounted(() => {
    loadData()
    window.addEventListener('resize', handleResize)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    trendChart?.dispose(); ipChart?.dispose(); domainChart?.dispose(); apptypeChart?.dispose()
    heatChart?.dispose(); nightChart?.dispose()
  })
</script>

<style lang="scss" scoped>
  .browsing-stat-page {
    display: flex;
    flex-direction: column;
    gap: 10px;
    height: auto;
    overflow: visible;

    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      .title { font-size: 16px; font-weight: 600; }
      .range-tip { font-size: 12px; color: var(--el-text-color-secondary); }
    }

    .summary-row { margin: 0 !important; }
    .stat-card {
      text-align: center;
      .stat-label { font-size: 13px; color: var(--el-text-color-secondary); }
      .stat-value { font-size: 22px; font-weight: 700; margin-top: 2px; }
    }

    .chart-card {
      .card-title { font-weight: 600; }
      .card-sub { font-size: 12px; color: var(--el-text-color-secondary); margin-left: 8px; font-weight: normal; }
      .chart-box { width: 100%; }
    }
  }
</style>
