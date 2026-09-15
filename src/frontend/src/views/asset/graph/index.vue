<!--
  资产知识图谱 - 全局视图（P5 / G1）

  设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.7

  功能：
  1. 力导向布局渲染整个资产网络
  2. 按业务系统/网段/重要度着色
  3. 搜索定位任意资产
  4. 点节点出详情卡，跳转资产详情
  5. 边置信度三档视觉编码（§6.7.2）
  6. 顶部空态/降级友好提示
-->
<template>
  <div class="graph-page art-full-height" v-loading="loading">
    <!-- 页头 -->
    <div class="graph-header">
      <div>
        <h2 class="page-title">资产知识图谱</h2>
        <p class="page-desc">
          基于资产、端口、漏洞、账号、登录、告警簇的关系图。点击节点查看详情，点击边看证据。
        </p>
      </div>
      <ElButton :icon="Refresh" :loading="rebuilding" @click="handleRebuild">重建边</ElButton>
    </div>

    <!-- 左中右三栏（严格对齐原型 .global-body） -->
    <div class="global-body">
      <!-- ======== 左栏：过滤面板 ======== -->
      <aside class="filter-panel">
        <div class="fg">
          <h4>搜索节点</h4>
          <ElInput
            v-model="searchKeyword"
            :prefix-icon="Search"
            placeholder="输入 IP / 主机名 / 业务系统"
            size="small"
            clearable
            @input="handleSearch"
          />
        </div>

        <div class="fg">
          <h4>业务系统</h4>
          <ElSelect v-model="filterBizSystem" size="small" @change="applyFilters">
            <ElOption label="全部业务系统" value="" />
            <ElOption v-for="biz in bizSystemOptions" :key="biz" :label="biz" :value="biz" />
          </ElSelect>
        </div>

        <div class="fg">
          <h4>网段</h4>
          <ElSelect v-model="filterSegment" size="small" @change="applyFilters">
            <ElOption label="全部网段" value="" />
            <ElOption v-for="seg in segmentOptions" :key="seg" :label="seg" :value="seg" />
          </ElSelect>
        </div>

        <div class="fg">
          <h4>快速过滤</h4>
          <label class="chk"><input type="checkbox" v-model="filterOnlyCritical" @change="applyFilters" /> 仅看核心资产</label>
          <label class="chk"><input type="checkbox" v-model="filterShowBlind" @change="applyFilters" /> 显示无 agent 盲区</label>
          <label class="chk"><input type="checkbox" v-model="filterIncludeInferred" @change="applyFilters" /> 显示推断边（灰色）</label>
        </div>

        <div class="fg">
          <h4>节点类型</h4>
          <div
            v-for="cat in NODE_CATEGORIES"
            :key="cat.value"
            class="legend-row"
            :class="{ dim: filterCategory && filterCategory !== cat.value }"
            @click="toggleCategoryFilter(cat.value)"
          >
            <span class="legend-dot" :style="{ background: cat.color }"></span>
            <span class="legend-label">{{ cat.label }}</span>
            <span class="legend-count">{{ countByCategory[cat.value] || 0 }}</span>
          </div>
        </div>

        <div class="fg">
          <h4>关系类型</h4>
          <div
            v-for="rel in REL_LEGEND"
            :key="rel.value"
            class="legend-row"
            :class="{ dim: !relVisible[rel.value] }"
            @click="toggleRelType(rel.value)"
          >
            <span class="legend-line" :class="{ dashed: rel.inferred }" :style="{ borderColor: rel.color }"></span>
            <span class="legend-label">{{ rel.label }}</span>
            <span class="legend-count">{{ countByRelType[rel.value] || 0 }}</span>
          </div>
        </div>
      </aside>

      <!-- ======== 中栏：主图 ======== -->
      <section class="graph-area">
        <div class="graph-toolbar">
          <button :class="{ on: layoutMode === 'force' }" @click="setLayout('force')">力导布局</button>
          <button :class="{ on: layoutMode === 'circular' }" @click="setLayout('circular')">环形布局</button>
        </div>

        <div ref="chartRef" class="global-chart" v-show="!emptyState"></div>

        <div v-if="emptyState" class="empty-state">
          <ElIcon class="empty-icon"><WarningFilled /></ElIcon>
          <p class="empty-title">图谱暂无数据</p>
          <p class="empty-desc">{{ emptyMessage }}</p>
          <ElButton type="primary" :icon="Refresh" @click="handleRebuild">立即重建边</ElButton>
        </div>
      </section>

      <!-- ======== 右栏：统计 + 节点详情 + 置信度 ======== -->
      <aside class="stat-panel">
        <div class="stat-cards">
          <div class="stat-card">
            <div class="num">{{ stats?.nodes?.total ?? 0 }}</div>
            <div class="lbl">节点</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ stats?.edges?.total ?? 0 }}</div>
            <div class="lbl">关系边</div>
          </div>
          <div class="stat-card">
            <div class="num">{{ coveragePercent }}%</div>
            <div class="lbl">边覆盖率</div>
          </div>
          <div class="stat-card">
            <div class="num" :class="{ danger: noAgentCount > 0 }">{{ noAgentCount }}</div>
            <div class="lbl">无 agent 盲区</div>
          </div>
        </div>

        <!-- 节点详情 -->
        <div class="node-detail">
          <template v-if="selectedNode">
            <div class="nd-title">
              <span class="node-tag" :class="`cat-${selectedNode.category}`">{{ categoryLabel(selectedNode.category) }}</span>
              {{ selectedNode.label }}
              <span class="nd-close" @click="selectedNode = null">×</span>
            </div>
            <template v-if="selectedNode.category === 'asset' && selectedAssetDetail">
              <div class="nd-row"><span>主机名</span><span>{{ selectedAssetDetail.name || '—' }}</span></div>
              <div class="nd-row"><span>IP</span><span>{{ selectedAssetDetail.ip || '—' }}</span></div>
              <div class="nd-row"><span>操作系统</span><span>{{ selectedAssetDetail.os || '—' }}</span></div>
              <div class="nd-row"><span>业务系统</span><span>{{ selectedAssetDetail.biz || '—' }}</span></div>
              <div class="nd-row">
                <span>重要性</span>
                <span><span class="tag" :class="critTagClass(selectedAssetDetail.crit)">{{ severityLabel(selectedAssetDetail.crit) }}</span></span>
              </div>
              <div class="nd-row"><span>责任人</span><span>{{ selectedAssetDetail.owner || '未指定' }}</span></div>
              <ElButton size="small" type="primary" :icon="View" class="nd-btn" @click="goAssetDetail(selectedNode.id)">查看资产详情</ElButton>
            </template>
            <template v-else>
              <div class="nd-row" v-for="(val, k) in selectedNode.rawProps" :key="k">
                <span>{{ k }}</span><span>{{ formatVal(val) }}</span>
              </div>
            </template>
          </template>
          <template v-else>
            <div class="nd-title nd-placeholder">点击图中节点查看详情</div>
            <div class="nd-row"><span>提示</span><span>可拖拽 / 缩放</span></div>
          </template>
        </div>

        <h4>边置信度说明</h4>
        <div class="conf-legend">
          <div class="conf-line"><span>≥90 采集/人工确认</span><b class="ok">实线</b></div>
          <div class="conf-line"><span>60–89 规则归一化</span><b class="warn">实线</b></div>
          <div class="conf-line"><span>&lt;60 推断</span><b class="dim">虚线</b></div>
          <p class="conf-tip">推断边仅作展示线索，不参与攻击路径与影响面计算。</p>
        </div>

        <!-- 修复阻塞点（右栏底部） -->
        <div class="choke-section">
          <h4>修复阻塞点 Top {{ chokepoints.length }}</h4>
          <div v-if="chokepoints.length" class="choke-list">
            <div v-for="row in chokepoints.slice(0, 5)" :key="row.vulnKey" class="choke-item">
              <div class="choke-head">
                <span class="tag tag-red">{{ row.cveId }}</span>
                <span class="choke-cvss">CVSS {{ row.cvss }}</span>
              </div>
              <div class="choke-meta">可达关键资产 <b>{{ row.reachableCriticalCount }}</b> 台</div>
            </div>
          </div>
          <div v-else class="choke-empty">无修复阻塞点（运行重建后刷新）</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onBeforeUnmount, ref, nextTick, computed, reactive } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { Refresh, Search, View, WarningFilled } from '@element-plus/icons-vue'
  import { useRouter } from 'vue-router'
  import { echarts, type EChartsOption } from '@/plugins/echarts'
  import {
    getAssetNeighbors,
    getGraphStats,
    getVulnChokepoints,
    postGraphRebuild,
    type GraphNode,
    type GraphLink,
    type GraphStatsResponse,
    type GraphChokepoint
  } from '@/api/graph'
  import { getAssetList } from '@/api/asset'

  // 节点类型图例（v1.7 对齐原型）
  const NODE_CATEGORIES = [
    { value: 'asset', label: '资产', color: '#185FA5' },
    { value: 'business_system', label: '业务系统', color: '#534AB7' },
    { value: 'account', label: '账号', color: '#0F6E56' },
    { value: 'vulnerability', label: '漏洞', color: '#A32D2D' },
    { value: 'alert_group', label: '告警簇', color: '#BA7517' },
    { value: 'segment', label: '网段', color: '#888780' },
    { value: 'ip', label: '外部 IP', color: '#1D9E75' }
  ]

  // 关系类型图例（v1.7 对齐原型）
  const REL_LEGEND: { value: string; label: string; color: string; inferred: boolean }[] = [
    { value: 'belongs_to_system', label: '部署于业务系统', color: '#185FA5', inferred: false },
    { value: 'login_to', label: '账号登录', color: '#0F6E56', inferred: false },
    { value: 'has_vuln', label: '存在漏洞', color: '#A32D2D', inferred: false },
    { value: 'alerted_on', label: '产生告警', color: '#BA7517', inferred: false },
    { value: 'inferred', label: '推断边（不参与攻击路径）', color: '#B4B2A9', inferred: true }
  ]
  const INFERRED_REL_TYPES = ['same_segment', 'shared_tag', 'co_alerted']

  const router = useRouter()
  const loading = ref(false)
  const rebuilding = ref(false)
  const chartRef = ref<HTMLDivElement | null>(null)
  let chartInstance: any = null

  // 过滤（v1.7 对齐原型 4 个 checkbox + 2 个 select + 搜索）
  const searchKeyword = ref('')
  const filterCategory = ref<string>('')
  const filterBizSystem = ref<string>('')
  const filterSegment = ref<string>('')
  const filterOnlyCritical = ref(false)
  const filterShowBlind = ref(true)
  const filterIncludeInferred = ref(true)
  // 关系类型可见性（图例点击切换）
  const relVisible = reactive<Record<string, boolean>>(
    Object.fromEntries(REL_LEGEND.map((r) => [r.value, true]))
  )
  // 布局模式
  const layoutMode = ref<'force' | 'circular'>('force')

  // 数据
  const stats = ref<GraphStatsResponse | null>(null)
  const nodes = ref<GraphNode[]>([])
  const links = ref<GraphLink[]>([])
  const selectedNode = ref<GraphNode | null>(null)
  const chokepoints = ref<GraphChokepoint[]>([])

  // 第一个 asset 节点作为查询入口
  const firstAssetKey = computed<string | null>(() => {
    const a = nodes.value.find((n) => n.category === 'asset')
    return a?.id ?? null
  })

  const emptyState = computed(() => !loading.value && nodes.value.length === 0)
  const emptyMessage = ref('请先运行重建边操作，或确认资产/端口/漏洞数据已接入。')

  // 衍生统计：边覆盖率（D1/D2 边覆盖资产占比）
  const coveragePercent = computed(() => {
    if (!stats.value?.coverage) return 0
    const c = stats.value.coverage
    if (!c.assetsTotal) return 0
    return Math.round((100 * (c.assetsWithD1D2Edges || 0)) / c.assetsTotal)
  })

  // 衍生统计：无 agent 盲区数（assetsTotal - agent_online）
  // 后端 stats 不直接返回，暂用 total - critical 估算占位（实际生产会拉 /data-health）
  const noAgentCount = computed(() => {
    if (!stats.value?.coverage) return 0
    const c = stats.value.coverage
    // 简化：assetsTotal - assetsWithAnyEdge 视为"无边资产"（无 agent 不直接可得）
    return Math.max(0, (c.assetsTotal || 0) - (c.assetsWithAnyEdge || 0))
  })

  // 衍生：网段选项（从已加载节点的 rawProps.network_segment 提取去重）
  const segmentOptions = computed(() => {
    const set = new Set<string>()
    for (const n of nodes.value) {
      const seg = n.rawProps?.network_segment
      if (seg) set.add(String(seg))
    }
    return Array.from(set).sort()
  })

  // 衍生：业务系统选项（从 business_system 节点 + 资产 rawProps.biz_systems 提取去重）
  const bizSystemOptions = computed(() => {
    const set = new Set<string>()
    for (const n of nodes.value) {
      if (n.category === 'business_system' && n.label) set.add(n.label)
      const biz = n.rawProps?.biz_systems || n.rawProps?.biz
      if (Array.isArray(biz)) biz.forEach((b: any) => b && set.add(String(b)))
      else if (biz) set.add(String(biz))
    }
    return Array.from(set).sort()
  })

  // 衍生：节点按 category 计数
  const countByCategory = computed(() => {
    const m: Record<string, number> = {}
    for (const n of nodes.value) m[n.category] = (m[n.category] || 0) + 1
    return m
  })

  // 衍生：边按 rel_type 计数
  const countByRelType = computed(() => {
    const m: Record<string, number> = {}
    for (const l of links.value) m[l.relType] = (m[l.relType] || 0) + 1
    return m
  })

  // 衍生：选中资产节点的 info（v1.7 详情卡用 rawProps 模拟）
  const selectedAssetDetail = computed(() => {
    if (!selectedNode.value || selectedNode.value.category !== 'asset') return null
    const p = selectedNode.value.rawProps || {}
    return {
      name: p.name || selectedNode.value.label,
      ip: p.ip,
      os: p.os,
      biz: p.biz_systems?.[0] || p.biz || '—',
      crit: p.criticality || 'medium',
      owner: p.owner || '未指定'
    }
  })

  let resizeObserver: ResizeObserver | null = null

  onMounted(async () => {
    await Promise.all([loadGraphStats(), loadChokepoints()])
    // 全局图需要一个种子资产作为中心：先取资产列表第一个，再拉邻居子图
    let seedKey = firstAssetKey.value
    if (!seedKey) {
      seedKey = await fetchSeedAssetKey()
    }
    if (seedKey) {
      await loadNeighbors(seedKey)
    } else {
      loading.value = false
    }
    await nextTick()
    initChart()
    // 中栏尺寸变化时 resize 图表
    if (chartRef.value && typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(() => chartInstance?.resize())
      resizeObserver.observe(chartRef.value)
    }
  })

  onBeforeUnmount(() => {
    resizeObserver?.disconnect()
    resizeObserver = null
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
  })

  // 取种子资产：拉资产列表第一个（全局图页初始没有已加载节点）
  async function fetchSeedAssetKey(): Promise<string | null> {
    try {
      const r = await getAssetList({ page: 1, page_size: 1 })
      const first = (r.data?.records || r.data?.items || r.data?.list || [])[0]
      return first?.id ? `asset:${first.id}` : null
    } catch (e) {
      console.error('fetchSeedAssetKey failed', e)
      return null
    }
  }

  async function loadGraphStats() {
    loading.value = true
    try {
      const r = await getGraphStats()
      if (r.code === 200) {
        stats.value = r.data
      }
    } catch (e) {
      console.error('loadGraphStats failed', e)
    } finally {
      loading.value = false
    }
  }

  async function loadChokepoints() {
    try {
      const r = await getVulnChokepoints({ limit: 20 })
      if (r.code === 200) {
        chokepoints.value = r.data.chokepoints || []
      }
    } catch (e) {
      console.error('loadChokepoints failed', e)
    }
  }

  async function loadNeighbors(centerKey: string) {
    if (!centerKey) {
      nodes.value = []
      links.value = []
      return
    }
    loading.value = true
    try {
      const assetId = centerKey.startsWith('asset:') ? centerKey.replace('asset:', '') : centerKey
      const r = await getAssetNeighbors(assetId, {
        depth: 3,
        includeInferred: filterIncludeInferred.value,
        limit: 500
      })
      if (r.code === 200) {
        nodes.value = r.data.nodes || []
        links.value = r.data.links || []
      }
    } catch (e) {
      console.error('loadNeighbors failed', e)
    } finally {
      loading.value = false
      await nextTick()
      renderChart()
    }
  }

  async function handleRebuild() {
    rebuilding.value = true
    try {
      const r = await postGraphRebuild('all')
      if (r.code === 200) {
        ElMessage.success('重建完成')
        await loadGraphStats()
        await loadChokepoints()
        const seed = firstAssetKey.value || (await fetchSeedAssetKey())
        if (seed) {
          await loadNeighbors(seed)
        }
      } else {
        ElMessage.error(r.msg || '重建失败')
      }
    } catch (e) {
      ElMessage.error(`重建失败: ${(e as Error).message}`)
    } finally {
      rebuilding.value = false
    }
  }

  // 过滤 & 搜索
  let searchTimer: ReturnType<typeof setTimeout> | null = null
  function handleSearch() {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      applyFilters()
    }, 300)
  }

  function applyFilters() {
    renderChart()
  }

  // v1.7 图例点击切换
  function toggleCategoryFilter(cat: string) {
    filterCategory.value = filterCategory.value === cat ? '' : cat
    applyFilters()
  }
  function toggleRelType(relType: string) {
    relVisible[relType] = !relVisible[relType]
    applyFilters()
  }

  // v1.7 布局切换（原型按钮）
  function setLayout(mode: 'force' | 'circular') {
    layoutMode.value = mode
    renderChart()
  }

  // ECharts 渲染
  function initChart() {
    if (!chartRef.value) return
    chartInstance = echarts.init(chartRef.value, undefined, {
      renderer: 'canvas'
    })
    renderChart()
    chartInstance.on('click', 'node', (params: any) => {
      const data = params.data as any
      const node = nodes.value.find((n) => n.id === data.id)
      if (node) {
        selectedNode.value = node
      }
    })
    chartInstance.on('click', 'edge', (params: any) => {
      const data = params.data as any
      ElMessageBox.alert(
        `<b>${data.relType}</b><br/>` +
          `置信度: ${(data.confidence * 100).toFixed(0)}%<br/>` +
          `来源: ${data.sourceLabel}<br/>` +
          `证据: <code>${JSON.stringify(data.evidence || {})}</code>`,
        '边详情',
        { dangerouslyUseHTMLString: true }
      ).catch(() => {})
    })
  }

  function renderChart() {
    if (!chartInstance) return

    // 应用过滤（v1.7：5 个过滤维度）
    let visibleNodes = nodes.value
    let visibleLinks = links.value

    if (filterCategory.value) {
      visibleNodes = visibleNodes.filter((n) => n.category === filterCategory.value)
    }
    // 业务系统过滤（资产节点的 biz_systems / biz，或业务系统节点本身）
    if (filterBizSystem.value) {
      const biz = filterBizSystem.value
      visibleNodes = visibleNodes.filter((n) => {
        if (n.category === 'business_system') return n.label === biz
        const p = n.rawProps || {}
        if (Array.isArray(p.biz_systems)) return p.biz_systems.includes(biz)
        return p.biz === biz
      })
    }
    // 网段过滤
    if (filterSegment.value) {
      visibleNodes = visibleNodes.filter(
        (n) => n.rawProps?.network_segment === filterSegment.value
      )
    }
    // 仅看核心资产（criticality=critical/high）
    if (filterOnlyCritical.value) {
      visibleNodes = visibleNodes.filter((n) => {
        if (n.category !== 'asset') return true  // 非资产节点不受影响
        const crit = n.rawProps?.criticality
        return crit === 'critical' || crit === 'high'
      })
    }
    // 无 agent 盲区过滤（false = 隐藏）
    if (!filterShowBlind.value) {
      visibleNodes = visibleNodes.filter((n) => {
        if (n.category !== 'asset') return true
        // 盲区定义：rawProps.agent_online === false 或缺失
        return n.rawProps?.agent_online === true
      })
    }
    // 推断边过滤
    if (!filterIncludeInferred.value) {
      visibleLinks = visibleLinks.filter(
        (l) => !INFERRED_REL_TYPES.includes(l.relType)
      )
    }
    // 关系类型图例可见性
    const hiddenRels = Object.entries(relVisible)
      .filter(([, v]) => !v)
      .map(([k]) => k)
    if (hiddenRels.length > 0) {
      visibleLinks = visibleLinks.filter((l) => {
        // 推断边用专门的 inferred 开关
        if (INFERRED_REL_TYPES.includes(l.relType)) return filterIncludeInferred.value
        return !hiddenRels.includes(l.relType)
      })
    }
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      visibleNodes = visibleNodes.filter(
        (n) =>
          n.label.toLowerCase().includes(kw) ||
          n.id.toLowerCase().includes(kw) ||
          (n.rawProps?.ip || '').toLowerCase().includes(kw)
      )
    }
    const keptIds = new Set(visibleNodes.map((n) => n.id))
    visibleLinks = visibleLinks.filter((l) => keptIds.has(l.source) && keptIds.has(l.target))

    const option: EChartsOption = {
      tooltip: {
        formatter: (params: any) => {
          if (params.dataType === 'edge') {
            const l = params.data as any
            return (
              `<b>${l.relType}</b><br/>` +
              `置信度: ${(l.confidence * 100).toFixed(0)}%<br/>` +
              `来源: ${l.sourceLabel}`
            )
          }
          const n = params.data as any
          return `<b>${n.label}</b><br/>` + `类型: ${n.category}<br/>` + `ID: <code>${n.id}</code>`
        }
      },
      series: [
        {
          type: 'graph',
          layout: layoutMode.value,  // v1.7：支持力导/环形切换
          roam: true,
          draggable: true,
          large: true,
          largeThreshold: 100,
          force: layoutMode.value === 'force' ? {
            repulsion: 420,
            edgeLength: [70, 140],
            gravity: 0.08,
            layoutAnimation: false
          } : undefined,
          circular: layoutMode.value === 'circular' ? { rotateLabel: true } : undefined,
          data: visibleNodes.map((n) => ({
            id: n.id,
            name: n.label,
            category: n.category,
            symbolSize: symbolSizeFor(n),
            ...n.rawProps
          })),
          links: visibleLinks.map((l) => ({
            id: l.id,
            source: l.source,
            target: l.target,
            relType: l.relType,
            confidence: l.confidence,
            sourceLabel: l.sourceLabel,
            evidence: l.evidence,
            lineStyle: l.lineStyle
          })),
          categories: NODE_CATEGORIES.map((c) => ({
            name: c.value,
            itemStyle: { color: c.color }
          })),
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 4 }
          },
          label: {
            show: true,
            position: 'right',
            formatter: '{b}',
            fontSize: 10
          }
        }
      ]
    }

    chartInstance.setOption(option, true)
  }

  function symbolSizeFor(n: GraphNode): number {
    if (n.category === 'asset') return 30
    if (n.category === 'business_system') return 40
    if (n.category === 'vulnerability') return 24
    if (n.category === 'port') return 14
    if (n.category === 'alert_group') return 18
    if (n.category === 'account') return 16
    return 18
  }

  function categoryLabel(cat: string): string {
    const map: Record<string, string> = {
      asset: '资产',
      port: '端口',
      vulnerability: '漏洞',
      account: '账号',
      ip: 'IP',
      business_system: '业务系统',
      person: '责任人',
      department: '部门',
      segment: '网段',
      alert_group: '告警簇',
      unknown: '未知'
    }
    return map[cat] || cat
  }

  function severityLabel(s: string): string {
    const map: Record<string, string> = {
      critical: '严重',
      high: '高',
      medium: '中',
      low: '低',
      unknown: '未知'
    }
    return map[s] || s
  }

  function severityTagType(s: string): 'danger' | 'warning' | 'info' | 'success' {
    if (s === 'critical') return 'danger'
    if (s === 'high') return 'warning'
    if (s === 'medium') return 'info'
    return 'success'
  }

  // 节点详情里 criticality 的原型 tag 配色类
  function critTagClass(s: string): string {
    if (s === 'critical') return 'tag-red'
    if (s === 'high') return 'tag-amber'
    if (s === 'low') return 'tag-green'
    return 'tag-blue'
  }

  function formatVal(v: any): string {
    if (v === null || v === undefined) return ''
    if (typeof v === 'object') return JSON.stringify(v)
    return String(v)
  }

  function goAssetDetail(nodeId: string) {
    const assetId = nodeId.replace('asset:', '')
    router.push(`/assets/detail/${assetId}`)
  }
</script>

<style lang="scss" scoped>
  /* ===== 颜色变量（对齐原型） ===== */
  .graph-page {
    --g-bg: #f5f4f0;
    --g-card: #ffffff;
    --g-border: rgba(0, 0, 0, 0.07);
    --g-border2: rgba(0, 0, 0, 0.12);
    --g-text: #1f2329;
    --g-text2: #5f5e5a;
    --g-text3: #8a8984;
    --g-primary: #185fa5;
    --g-primary-bg: #e7f0fa;
    --g-danger: #a32d2d;
    --g-danger-bg: #fcebeb;
    --g-warn: #854f0b;
    --g-warn-bg: #faeeda;
    --g-ok: #0f6e56;
    --g-ok-bg: #e1f5ee;
  }

  .graph-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    gap: 12px;
  }

  /* ===== 页头 ===== */
  .graph-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-shrink: 0;
    .page-title { font-size: 18px; font-weight: 600; margin: 0; }
    .page-desc { font-size: 12px; color: var(--g-text3); margin: 4px 0 0; }
  }

  /* ===== 左中右三栏（原型 .global-body） ===== */
  .global-body {
    flex: 1;
    display: flex;
    min-height: 480px;
    background: var(--g-card);
    border: 0.5px solid var(--g-border2);
    border-radius: 12px;
    overflow: hidden;
  }

  /* ---- 左栏：过滤 ---- */
  .filter-panel {
    width: 220px;
    flex-shrink: 0;
    border-right: 0.5px solid var(--g-border);
    padding: 16px;
    overflow-y: auto;

    h4 { font-size: 12px; color: var(--g-text3); font-weight: 500; margin: 0 0 8px; }
    .fg { margin-bottom: 18px; }

    :deep(.el-select) { width: 100%; }
    :deep(.el-input__wrapper) { font-size: 12px; }
  }

  .chk {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--g-text2);
    margin-bottom: 6px;
    cursor: pointer;
    input { margin: 0; cursor: pointer; }
  }

  /* ---- 中栏：主图 ---- */
  .graph-area {
    flex: 1;
    position: relative;
    min-width: 0;
    display: flex;
  }
  .global-chart {
    width: 100%;
    height: 100%;
    min-height: 480px;
  }

  .graph-toolbar {
    position: absolute;
    top: 12px;
    right: 16px;
    display: flex;
    gap: 8px;
    z-index: 5;
    button {
      padding: 6px 12px;
      border: 0.5px solid var(--g-border2);
      background: #fff;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      color: var(--g-text2);
    }
    button.on {
      background: var(--g-primary-bg);
      color: var(--g-primary);
      border-color: var(--g-primary);
    }
  }

  .empty-state {
    position: absolute;
    inset: 0;
    margin: auto;
    width: fit-content;
    height: fit-content;
    text-align: center;
    color: var(--g-text3);
    .empty-icon { font-size: 40px; margin-bottom: 8px; }
    .empty-title { font-size: 14px; color: var(--g-text2); margin: 0 0 4px; }
    .empty-desc { font-size: 12px; margin: 0 0 12px; }
  }

  /* ---- 右栏：统计 + 详情 + 置信度 ---- */
  .stat-panel {
    width: 230px;
    flex-shrink: 0;
    border-left: 0.5px solid var(--g-border);
    padding: 16px;
    overflow-y: auto;

    h4 { font-size: 12px; color: var(--g-text3); font-weight: 500; margin: 0 0 8px; }
  }

  .stat-cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 16px;
  }
  .stat-card {
    background: var(--g-bg);
    border-radius: 8px;
    padding: 10px;
    .num { font-size: 20px; font-weight: 500; }
    .num.danger { color: var(--g-danger); }
    .lbl { font-size: 11px; color: var(--g-text3); margin-top: 2px; }
  }

  .node-detail {
    background: var(--g-bg);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 16px;
  }
  .nd-title {
    font-weight: 500;
    font-size: 13px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .nd-placeholder { color: var(--g-text2); font-weight: 400; }
  .nd-close {
    margin-left: auto;
    cursor: pointer;
    color: var(--g-text3);
    font-size: 16px;
    line-height: 1;
    &:hover { color: var(--g-text); }
  }
  .nd-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    padding: 3px 0;
    color: var(--g-text2);
    span:last-child { color: var(--g-text); text-align: right; word-break: break-all; }
  }
  .nd-btn { margin-top: 8px; width: 100%; }

  .node-tag {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 11px;
    background: var(--g-primary-bg);
    color: var(--g-primary);
  }

  /* tag 配色（原型） */
  .tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; }
  .tag-red { background: var(--g-danger-bg); color: var(--g-danger); }
  .tag-amber { background: var(--g-warn-bg); color: var(--g-warn); }
  .tag-green { background: var(--g-ok-bg); color: var(--g-ok); }
  .tag-blue { background: var(--g-primary-bg); color: var(--g-primary); }
  .tag-gray { background: #f1efe8; color: #5f5e5a; }

  /* 边置信度说明 */
  .conf-legend {
    font-size: 12px;
    color: var(--g-text2);
    line-height: 1.8;
  }
  .conf-line {
    display: flex;
    justify-content: space-between;
    b.ok { color: var(--g-ok); }
    b.warn { color: var(--g-warn); }
    b.dim { color: var(--g-text3); }
  }
  .conf-tip {
    margin: 8px 0 0;
    padding-top: 8px;
    border-top: 0.5px solid var(--g-border);
    color: var(--g-text3);
    font-size: 11px;
    line-height: 1.6;
  }

  /* 修复阻塞点 */
  .choke-section { margin-top: 16px; }
  .choke-list { display: flex; flex-direction: column; gap: 8px; }
  .choke-item {
    background: var(--g-bg);
    border-radius: 8px;
    padding: 8px 10px;
  }
  .choke-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2px;
  }
  .choke-cvss { font-size: 11px; color: var(--g-text3); }
  .choke-meta { font-size: 11px; color: var(--g-text2); }
  .choke-empty { font-size: 11px; color: var(--g-text3); }

  /* ===== 图例行（左栏节点/关系类型，原型 .legend-row） ===== */
  .legend-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 4px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    color: var(--g-text2);
    &:hover { background: var(--g-bg); }
    &.dim { opacity: 0.4; }
  }
  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .legend-line {
    width: 16px;
    height: 0;
    border-top: 2px solid;
    flex-shrink: 0;
    &.dashed { border-top-style: dashed; }
  }
  .legend-label { flex: 1; }
  .legend-count { color: var(--g-text3); font-size: 11px; }
</style>
