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
    <ElCard shadow="never" class="header-card">
      <div class="page-header">
        <div>
          <h2 class="page-title">资产知识图谱</h2>
          <p class="page-desc">
            基于资产、端口、漏洞、账号、登录、告警簇的关系图。点击节点跳资产详情，点击边看证据。
          </p>
        </div>
        <div class="header-actions">
          <ElButton :icon="Refresh" :loading="rebuilding" @click="handleRebuild">重建边</ElButton>
        </div>
      </div>
    </ElCard>

    <!-- 状态卡：节点/边/覆盖率 + 过滤 -->
    <ElCard shadow="never" class="stats-bar">
      <ElRow :gutter="16">
        <ElCol :xs="12" :sm="6">
          <div class="stat-cell">
            <span class="stat-label">节点数</span>
            <span class="stat-value">{{ stats?.nodes?.total ?? 0 }}</span>
          </div>
        </ElCol>
        <ElCol :xs="12" :sm="6">
          <div class="stat-cell">
            <span class="stat-label">边数</span>
            <span class="stat-value">{{ stats?.edges?.total ?? 0 }}</span>
          </div>
        </ElCol>
        <ElCol :xs="12" :sm="6">
          <div class="stat-cell">
            <span class="stat-label">核心资产责任人覆盖率</span>
            <span class="stat-value">
              {{
                stats?.coverage?.criticalAssetsTotal
                  ? Math.round(
                      (100 * (stats.coverage.criticalAssetsWithOwner || 0)) /
                        stats.coverage.criticalAssetsTotal
                    )
                  : 0
              }}%
            </span>
          </div>
        </ElCol>
        <ElCol :xs="12" :sm="6">
          <div class="stat-cell">
            <span class="stat-label">业务系统归属</span>
            <span class="stat-value">
              {{
                stats?.coverage?.assetsTotal
                  ? Math.round(
                      (100 * (stats.coverage.assetsWithBusinessSystem || 0)) /
                        stats.coverage.assetsTotal
                    )
                  : 0
              }}%
            </span>
          </div>
        </ElCol>
      </ElRow>
    </ElCard>

    <!-- 工具条 -->
    <ElCard shadow="never" class="filter-bar">
      <ElRow :gutter="12" align="middle">
        <ElCol :xs="24" :md="8">
          <ElInput
            v-model="searchKeyword"
            :prefix-icon="Search"
            placeholder="搜索节点（资产名/IP/CVE/账号）"
            clearable
            @input="handleSearch"
          />
        </ElCol>
        <ElCol :xs="12" :md="5">
          <ElSelect
            v-model="filterCategory"
            placeholder="节点类型"
            clearable
            @change="applyFilters"
          >
            <ElOption label="全部" :value="''" />
            <ElOption label="资产" value="asset" />
            <ElOption label="端口" value="port" />
            <ElOption label="漏洞" value="vulnerability" />
            <ElOption label="账号" value="account" />
            <ElOption label="IP" value="ip" />
            <ElOption label="业务系统" value="business_system" />
            <ElOption label="告警簇" value="alert_group" />
          </ElSelect>
        </ElCol>
        <ElCol :xs="12" :md="5">
          <ElCheckbox v-model="filterIncludeInferred" @change="applyFilters">
            包含推断边
          </ElCheckbox>
        </ElCol>
        <ElCol :xs="24" :md="6">
          <ElButton :icon="Refresh" @click="loadGraphStats">刷新统计</ElButton>
        </ElCol>
      </ElRow>
    </ElCard>

    <!-- 主图 -->
    <ElCard shadow="never" class="chart-card">
      <template #header>
        <span class="card-title">关系网络（力导向布局）</span>
        <span class="card-sub">实线深色 = 已验证 / 实线浅色 = 观测 / 虚线灰色 = 推断</span>
      </template>

      <div ref="chartRef" class="chart-box" v-show="!emptyState"></div>

      <div v-if="emptyState" class="empty-state">
        <ElIcon class="empty-icon"><WarningFilled /></ElIcon>
        <p class="empty-title">图谱暂无数据</p>
        <p class="empty-desc">{{ emptyMessage }}</p>
        <ElButton type="primary" :icon="Refresh" @click="handleRebuild">立即重建边</ElButton>
      </div>

      <!-- 节点详情侧栏 -->
      <div v-if="selectedNode" class="node-detail-panel">
        <ElCard shadow="always" class="detail-card">
          <template #header>
            <span class="detail-title">
              <span class="node-category" :class="`cat-${selectedNode.category}`">
                {{ categoryLabel(selectedNode.category) }}
              </span>
              {{ selectedNode.label }}
            </span>
            <ElButton text :icon="Close" @click="selectedNode = null" />
          </template>
          <div class="detail-body">
            <ElDescriptions :column="1" border size="small">
              <ElDescriptionsItem label="节点 ID">
                <ElText copyable>{{ selectedNode.id }}</ElText>
              </ElDescriptionsItem>
              <ElDescriptionsItem v-for="(val, k) in selectedNode.rawProps" :key="k" :label="k">
                <code>{{ formatVal(val) }}</code>
              </ElDescriptionsItem>
            </ElDescriptions>
            <div class="detail-actions" v-if="selectedNode.category === 'asset'">
              <ElButton type="primary" :icon="View" @click="goAssetDetail(selectedNode.id)">
                查看详情
              </ElButton>
            </div>
          </div>
        </ElCard>
      </div>
    </ElCard>

    <!-- 修复阻塞点 -->
    <ElCard shadow="never" class="chokepoints-card">
      <template #header>
        <span class="card-title">修复阻塞点 Top {{ chokepoints.length }}</span>
        <span class="card-sub">修一个 CVE 可切断多条攻击路径（按可达关键资产数排序）</span>
      </template>
      <ElTable :data="chokepoints" stripe size="small" empty-text="无修复阻塞点（运行重建后刷新）">
        <ElTableColumn label="CVE" prop="cveId" min-width="160">
          <template #default="{ row }">
            <ElTag effect="plain" :type="severityTagType(row.severity)">{{ row.cveId }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="CVSS" prop="cvss" width="80" sortable />
        <ElTableColumn label="严重度" prop="severity" width="100">
          <template #default="{ row }">
            <ElTag :type="severityTagType(row.severity)" effect="dark" size="small">
              {{ severityLabel(row.severity) }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="可达关键资产数" prop="reachableCriticalCount" width="160" sortable />
        <ElTableColumn label="可达资产">
          <template #default="{ row }">
            <ElText truncated>{{ row.reachableAssets?.slice(0, 3).join(', ') }}</ElText>
          </template>
        </ElTableColumn>
      </ElTable>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onBeforeUnmount, ref, nextTick, computed } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { Refresh, Search, View, Close, WarningFilled } from '@element-plus/icons-vue'
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

  const router = useRouter()
  const loading = ref(false)
  const rebuilding = ref(false)
  const chartRef = ref<HTMLDivElement | null>(null)
  let chartInstance: any = null

  // 过滤
  const searchKeyword = ref('')
  const filterCategory = ref<string>('')
  const filterIncludeInferred = ref(true)

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

  onMounted(async () => {
    await Promise.all([loadGraphStats(), loadChokepoints()])
    // 选第一个资产作为中心点拉子图
    if (firstAssetKey.value) {
      await loadNeighbors(firstAssetKey.value)
    } else {
      await loadNeighbors('') // 空态：尝试调一次看后端返回
    }
    await nextTick()
    initChart()
  })

  onBeforeUnmount(() => {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
  })

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
        if (firstAssetKey.value) {
          await loadNeighbors(firstAssetKey.value)
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

  // ECharts 渲染
  function initChart() {
    if (!chartRef.value) return
    chartInstance = echarts.init(chartRef.value, 'dark', {
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

    // 应用过滤
    let visibleNodes = nodes.value
    let visibleLinks = links.value

    if (filterCategory.value) {
      visibleNodes = visibleNodes.filter((n) => n.category === filterCategory.value)
    }
    if (!filterIncludeInferred.value) {
      visibleLinks = visibleLinks.filter(
        (l) => !['same_segment', 'shared_tag', 'co_alerted'].includes(l.relType)
      )
    }
    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      visibleNodes = visibleNodes.filter(
        (n) => n.label.toLowerCase().includes(kw) || n.id.toLowerCase().includes(kw)
      )
      const keptIds = new Set(visibleNodes.map((n) => n.id))
      visibleLinks = visibleLinks.filter((l) => keptIds.has(l.source) && keptIds.has(l.target))
    }

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
      legend: [
        {
          data: ['asset', 'port', 'vulnerability', 'account', 'business_system', 'ip'],
          orient: 'vertical',
          right: 10,
          top: 20,
          textStyle: { color: '#aaa' }
        }
      ],
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          large: true,
          largeThreshold: 100,
          force: {
            repulsion: 420,
            edgeLength: [70, 140],
            gravity: 0.08,
            layoutAnimation: false
          },
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
          categories: [
            { name: 'asset', itemStyle: { color: '#A32D2D' } },
            { name: 'port', itemStyle: { color: '#5470c6' } },
            { name: 'vulnerability', itemStyle: { color: '#ee6666' } },
            { name: 'account', itemStyle: { color: '#fac858' } },
            { name: 'ip', itemStyle: { color: '#73c0de' } },
            { name: 'business_system', itemStyle: { color: '#3ba272' } },
            { name: 'alert_group', itemStyle: { color: '#fc8452' } },
            { name: 'segment', itemStyle: { color: '#9a60b4' } },
            { name: 'person', itemStyle: { color: '#ea7ccc' } },
            { name: 'department', itemStyle: { color: '#bda29a' } }
          ],
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
  .graph-page {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;

    .header-card {
      .page-header {
        display: flex;
        justify-content: space-between;
        align-items: center;

        .page-title {
          font-size: 20px;
          font-weight: 600;
          margin: 0;
        }
        .page-desc {
          color: #888;
          margin: 4px 0 0;
          font-size: 13px;
        }
      }
    }

    .stats-bar {
      .stat-cell {
        display: flex;
        flex-direction: column;
        align-items: flex-start;

        .stat-label {
          font-size: 12px;
          color: #888;
        }
        .stat-value {
          font-size: 22px;
          font-weight: 600;
          color: #409eff;
        }
      }
    }

    .filter-bar {
      :deep(.el-row) {
        align-items: center;
      }
    }

    .chart-card {
      position: relative;

      .chart-box {
        width: 100%;
        height: 600px;
      }

      .card-title {
        font-weight: 600;
      }
      .card-sub {
        margin-left: 12px;
        font-size: 12px;
        color: #888;
      }

      .empty-state {
        height: 400px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #888;

        .empty-icon {
          font-size: 48px;
          color: #c0c4cc;
          margin-bottom: 16px;
        }
        .empty-title {
          font-size: 16px;
          font-weight: 600;
          margin-bottom: 8px;
        }
        .empty-desc {
          font-size: 13px;
          margin-bottom: 16px;
        }
      }

      .node-detail-panel {
        position: absolute;
        top: 16px;
        right: 16px;
        width: 320px;
        z-index: 10;

        .detail-card {
          max-height: 70vh;
          overflow-y: auto;
        }
        .detail-title {
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 6px;

          .node-category {
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 3px;
            background: #f0f0f0;
            color: #666;
          }
        }
        .detail-actions {
          margin-top: 12px;
          display: flex;
          gap: 8px;
        }
      }
    }

    .chokepoints-card {
      .card-title {
        font-weight: 600;
      }
      .card-sub {
        margin-left: 12px;
        font-size: 12px;
        color: #888;
      }
    }
  }
</style>
