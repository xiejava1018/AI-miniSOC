<!--
  资产详情 - 关系图谱 Tab（P5 / G1）

  设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.7

  嵌在资产详情页内，作为第 7 个 Tab：
  - ego 图（中心 = 当前资产）
  - 点节点跳资产详情，点边看证据 + 来源
  - 推断边强制虚线灰色 + "不参与攻击路径" 警示
-->
<template>
  <div class="relation-graph-tab" v-loading="loading">
    <!-- 顶部工具条 -->
    <div class="tab-toolbar">
      <ElRadioGroup v-model="depth" size="small" @change="loadData">
        <ElRadioButton :value="1">1 跳</ElRadioButton>
        <ElRadioButton :value="2">2 跳</ElRadioButton>
        <ElRadioButton :value="3">3 跳</ElRadioButton>
      </ElRadioGroup>
      <ElCheckbox v-model="includeInferred" @change="loadData"> 包含推断边 </ElCheckbox>
      <ElButton text :icon="Refresh" :loading="loading" @click="loadData">刷新</ElButton>

      <span class="legend">
        <span class="legend-item">
          <span class="legend-line" style="background: #a32d2d"></span>已验证 (≥90%)
        </span>
        <span class="legend-item">
          <span class="legend-line" style="background: #5b6e8c"></span>观测 (60-89%)
        </span>
        <span class="legend-item">
          <span
            class="legend-line"
            style="background: #9ca3af; border-top: 1px dashed #9ca3af"
          ></span
          >推断 (&lt;60%)
        </span>
      </span>
    </div>

    <!-- 主图 -->
    <div ref="chartRef" class="chart-box" v-show="!emptyState"></div>

    <div v-if="emptyState" class="empty-state">
      <ElIcon class="empty-icon"><WarningFilled /></ElIcon>
      <p class="empty-title">该资产暂无关系数据</p>
      <p class="empty-desc">{{ emptyMessage }}</p>
      <p class="empty-tip">可能未纳管 Wazuh agent 或无业务归属，去资产管理补数据后重建边。</p>
    </div>

    <!-- 详情面板 -->
    <div v-if="selectedEdge || selectedNode" class="side-panel">
      <ElCard shadow="always" class="panel-card">
        <template #header>
          <span class="panel-title">
            <template v-if="selectedEdge">
              边：{{ selectedEdge.sourceLabel }}
              <ElTag size="small" effect="plain">{{ selectedEdge.relType }}</ElTag>
            </template>
            <template v-else>
              节点：{{ selectedNode!.label }}
              <ElTag size="small" effect="plain">{{ categoryLabel(selectedNode!.category) }}</ElTag>
            </template>
          </span>
          <ElButton text :icon="Close" @click="closePanel" />
        </template>

        <!-- 边详情 -->
        <div v-if="selectedEdge" class="evidence-body">
          <div class="evidence-bar">
            <span class="bar-label">置信度</span>
            <ElProgress
              :percentage="Math.round(selectedEdge.confidence * 100)"
              :color="confColor(selectedEdge.confidence)"
              :stroke-width="14"
            />
          </div>
          <ElDescriptions :column="1" border size="small">
            <ElDescriptionsItem label="来源">
              {{ selectedEdge.sourceLabel }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="证据">
              <pre class="evidence-pre">{{ JSON.stringify(selectedEdge.evidence, null, 2) }}</pre>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="最近更新">
              {{ selectedEdge.updated || '--' }}
            </ElDescriptionsItem>
          </ElDescriptions>
          <div class="evidence-actions">
            <ElButton size="small" type="primary" @click="emitJoinAi(selectedEdge)">
              加入 AI 研判
            </ElButton>
          </div>
        </div>

        <!-- 节点详情 -->
        <div v-else class="evidence-body">
          <ElDescriptions :column="1" border size="small">
            <ElDescriptionsItem label="节点 ID">
              <ElText copyable>{{ selectedNode!.id }}</ElText>
            </ElDescriptionsItem>
            <ElDescriptionsItem v-for="(val, k) in selectedNode!.rawProps" :key="k" :label="k">
              <code>{{ formatVal(val) }}</code>
            </ElDescriptionsItem>
          </ElDescriptions>
          <div v-if="selectedNode!.category === 'asset'" class="evidence-actions">
            <ElButton size="small" type="primary" @click="goAssetDetail(selectedNode!.id)">
              查看资产详情
            </ElButton>
          </div>
        </div>
      </ElCard>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import { Refresh, Close, WarningFilled } from '@element-plus/icons-vue'
  import { echarts, type EChartsOption } from '@/plugins/echarts'
  import { getAssetNeighbors, type GraphLink, type GraphNode } from '@/api/graph'

  const props = defineProps<{ assetId: string }>()
  const emit = defineEmits<{
    (e: 'join-ai', edge: GraphLink): void
  }>()

  const router = useRouter()
  const loading = ref(false)
  const chartRef = ref<HTMLDivElement | null>(null)
  let chartInstance: any = null

  const depth = ref(2)
  const includeInferred = ref(true)

  const nodes = ref<GraphNode[]>([])
  const links = ref<GraphLink[]>([])
  const selectedNode = ref<GraphNode | null>(null)
  const selectedEdge = ref<GraphLink | null>(null)

  const emptyState = computed(() => !loading.value && nodes.value.length <= 1)
  const emptyMessage = ref('未找到与该资产相关的关系边。')

  onMounted(async () => {
    await loadData()
    await nextTick()
    initChart()
  })

  onBeforeUnmount(() => {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
  })

  watch(
    () => props.assetId,
    () => {
      loadData()
    }
  )

  async function loadData() {
    if (!props.assetId) return
    loading.value = true
    try {
      const r = await getAssetNeighbors(props.assetId, {
        depth: depth.value,
        includeInferred: includeInferred.value,
        limit: 500
      })
      if (r.code === 200) {
        nodes.value = r.data.nodes || []
        links.value = r.data.links || []
        if (r.data.message) emptyMessage.value = r.data.message
      }
    } catch (e) {
      console.error('loadData failed', e)
      ElMessage.error('关系图加载失败')
    } finally {
      loading.value = false
      await nextTick()
      renderChart()
    }
  }

  function initChart() {
    if (!chartRef.value) return
    chartInstance = echarts.init(chartRef.value, 'dark', { renderer: 'canvas' })
    renderChart()
    chartInstance.on('click', 'node', (params: any) => {
      const node = nodes.value.find((n) => n.id === params.data.id)
      if (node) {
        selectedNode.value = node
        selectedEdge.value = null
      }
    })
    chartInstance.on('click', 'edge', (params: any) => {
      const link = links.value.find((l) => l.id === params.data.id)
      if (link) {
        selectedEdge.value = link
        selectedNode.value = null
      }
    })
  }

  function renderChart() {
    if (!chartInstance) return

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
          return `<b>${n.name}</b><br/>` + `类型: ${n.category}<br/>` + `ID: <code>${n.id}</code>`
        }
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          force: {
            repulsion: 420,
            edgeLength: [70, 140],
            gravity: 0.08,
            layoutAnimation: false
          },
          data: nodes.value.map((n) => ({
            id: n.id,
            name: n.label,
            category: n.category,
            symbolSize: symbolSizeFor(n),
            ...n.rawProps
          })),
          links: links.value.map((l) => ({
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
    if (n.category === 'asset' && n.id === `asset:${props.assetId}`) return 50
    if (n.category === 'asset') return 28
    if (n.category === 'business_system') return 40
    if (n.category === 'vulnerability') return 22
    if (n.category === 'port') return 12
    if (n.category === 'alert_group') return 16
    if (n.category === 'account') return 14
    return 16
  }

  function closePanel() {
    selectedEdge.value = null
    selectedNode.value = null
  }

  function confColor(c: number): string {
    if (c >= 0.9) return '#A32D2D'
    if (c >= 0.6) return '#5B6E8C'
    return '#9CA3AF'
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
      alert_group: '告警簇'
    }
    return map[cat] || cat
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

  function emitJoinAi(edge: GraphLink) {
    emit('join-ai', edge)
    ElMessage.success('已加入 AI 研判上下文')
  }
</script>

<style lang="scss" scoped>
  .relation-graph-tab {
    position: relative;

    .tab-toolbar {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 12px;

      .legend {
        margin-left: auto;
        display: flex;
        gap: 12px;
        font-size: 12px;
        color: #888;

        .legend-item {
          display: flex;
          align-items: center;
          gap: 4px;

          .legend-line {
            width: 18px;
            height: 3px;
            border-radius: 1px;
          }
        }
      }
    }

    .chart-box {
      width: 100%;
      height: 600px;
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
        margin-bottom: 4px;
      }
      .empty-tip {
        font-size: 12px;
        color: #aaa;
      }
    }

    .side-panel {
      position: absolute;
      top: 60px;
      right: 16px;
      width: 360px;
      z-index: 10;

      .panel-card {
        max-height: 70vh;
        overflow-y: auto;
      }
      .panel-title {
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .evidence-body {
        .evidence-bar {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;

          .bar-label {
            font-size: 12px;
            color: #888;
            white-space: nowrap;
          }
        }

        .evidence-pre {
          background: #f5f7fa;
          padding: 8px;
          border-radius: 4px;
          font-size: 12px;
          max-height: 200px;
          overflow-y: auto;
          margin: 0;
        }

        .evidence-actions {
          margin-top: 12px;
          display: flex;
          gap: 8px;
        }
      }
    }
  }
</style>
