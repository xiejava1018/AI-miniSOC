<!--
  资产详情 - 关系图谱 Tab（P5 / G1）

  设计依据：
  - docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.7
  - docs/design/prototype/资产知识图谱界面原型.html（视图② 资产详情 · 关系图谱 Tab）

  布局严格对齐原型：左侧 ego 图（flex:1）+ 右侧固定 320px「关系证据」面板。
  - 浅色风格（与 art-design-pro 整体一致，不用 echarts dark 主题）
  - 点节点：右侧显示节点资料
  - 点边：右侧显示关系证据（置信度 / 数据来源 / 证据时间 / 证据正文），
    确定边提供「查看原始日志」「加入 AI 研判」，推断边显示"不参与攻击路径"警示
-->
<template>
  <div class="relation-graph-tab" v-loading="loading">
    <!-- 顶部工具条 -->
    <div class="rg-toolbar">
      <ElRadioGroup v-model="depth" size="small" @change="loadData">
        <ElRadioButton :value="1">1 跳</ElRadioButton>
        <ElRadioButton :value="2">2 跳</ElRadioButton>
        <ElRadioButton :value="3">3 跳</ElRadioButton>
      </ElRadioGroup>
      <ElCheckbox v-model="includeInferred" @change="loadData">包含推断边</ElCheckbox>
      <ElButton text :icon="Refresh" :loading="loading" @click="loadData">刷新</ElButton>

      <span class="rg-legend">
        <span class="lg-item"><span class="lg-line lg-strong"></span>已验证 (≥90%)</span>
        <span class="lg-item"><span class="lg-line lg-obs"></span>观测 (60–89%)</span>
        <span class="lg-item"><span class="lg-line lg-infer"></span>推断 (&lt;60%)</span>
      </span>
    </div>

    <!-- 主体：左图 + 右证据面板（对齐原型 .detail-main） -->
    <div class="rg-body">
      <div class="rg-ego-area">
        <!-- 图容器始终渲染占位（不用 v-show），保证 ResizeObserver 能随 TabPane
             display:none→block 可靠感知尺寸；空态用绝对定位覆盖层 -->
        <div ref="chartRef" class="rg-chart"></div>
        <div v-if="emptyState" class="rg-empty">
          <ElIcon class="empty-icon"><WarningFilled /></ElIcon>
          <p class="empty-title">该资产暂无关系数据</p>
          <p class="empty-desc">{{ emptyMessage }}</p>
          <p class="empty-tip">可能未纳管 Wazuh agent 或无业务归属，去资产管理补数据后重建边。</p>
        </div>
        <div v-if="!emptyState" class="rg-hint">
          点击图中的连线，查看该关系的置信度、数据来源与原始证据
        </div>
      </div>

      <!-- 右侧：关系证据面板（常驻 320px 分栏，非浮动卡片） -->
      <aside class="rg-evidence-panel">
        <!-- 空态 -->
        <div v-if="!selectedEdge && !selectedNode" class="ev-empty">
          点击图中的连线<br />查看关系证据
        </div>

        <!-- 边证据 -->
        <template v-else-if="selectedEdge">
          <h4 class="ev-panel-title">
            关系证据
            <span class="ev-type" :class="isInferred(selectedEdge) ? 'tag-infer' : 'tag-verified'">
              {{ isInferred(selectedEdge) ? '推断边' : '已验证关系' }}
            </span>
            <ElButton class="ev-close" text :icon="Close" @click="closePanel" />
          </h4>

          <div class="ev-rel-name">{{ relTypeName(selectedEdge.relType) }}</div>
          <div class="ev-flow">
            {{ endpointLabel(selectedEdge.source) }}
            <span class="ev-arrow">──▶</span>
            {{ endpointLabel(selectedEdge.target) }}
          </div>

          <div class="kv">
            <span class="k">置信度</span>
            <span class="v" :style="{ color: confColor(selectedEdge.confidence), fontWeight: 500 }">
              {{ Math.round(selectedEdge.confidence * 100) }} / 100 · {{ confLabel(selectedEdge.confidence) }}
            </span>
          </div>
          <div class="conf-bar">
            <i :style="{ width: Math.round(selectedEdge.confidence * 100) + '%', background: confColor(selectedEdge.confidence) }"></i>
          </div>

          <div class="kv"><span class="k">数据来源</span><span class="v">{{ selectedEdge.sourceLabel || '未知' }}</span></div>
          <div class="kv"><span class="k">证据时间</span><span class="v">{{ formatTime(selectedEdge.lastSeen || selectedEdge.updated) }}</span></div>
          <div class="kv" v-if="selectedEdge.firstSeen">
            <span class="k">首次发现</span><span class="v">{{ formatTime(selectedEdge.firstSeen) }}</span>
          </div>

          <!-- 证据正文 -->
          <div class="ev-evidence" v-if="evidenceLines.length">
            <div v-for="line in evidenceLines" :key="line.k" class="ev-row">
              <b>{{ line.k }}</b>：{{ line.v }}
            </div>
          </div>
          <div class="ev-evidence" v-else>该关系暂无可展示的结构化证据。</div>

          <!-- 推断边：不给操作按钮，只给说明 -->
          <div v-if="isInferred(selectedEdge)" class="inferred-note">
            该边为规则推断生成，仅提供排查线索；按设计约束，推断边不参与攻击路径、影响面与阻塞点计算。
          </div>
          <!-- 确定边：两个操作 -->
          <div v-else class="ev-actions">
            <ElButton size="small" @click="viewRawLog(selectedEdge)">查看原始日志</ElButton>
            <ElButton size="small" type="primary" @click="emitJoinAi(selectedEdge)">加入 AI 研判</ElButton>
          </div>
        </template>

        <!-- 节点资料 -->
        <template v-else-if="selectedNode">
          <h4 class="ev-panel-title">
            节点资料
            <span class="ev-type tag-node">{{ categoryLabel(selectedNode.category) }}</span>
            <ElButton class="ev-close" text :icon="Close" @click="closePanel" />
          </h4>

          <div class="ev-rel-name">{{ selectedNode.label }}</div>

          <div class="kv"><span class="k">节点 ID</span><span class="v ev-node-id">{{ shortId(selectedNode.id) }}</span></div>
          <div class="kv" v-for="(val, k) in selectedNode.rawProps" :key="k">
            <span class="k">{{ k }}</span>
            <span class="v">{{ formatVal(val) }}</span>
          </div>

          <div v-if="selectedNode.category === 'asset'" class="ev-actions">
            <ElButton size="small" type="primary" @click="goAssetDetail(selectedNode.id)">查看资产详情</ElButton>
          </div>
        </template>
      </aside>
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
  let resizeObserver: ResizeObserver | null = null

  const depth = ref(2)
  const includeInferred = ref(true)

  const nodes = ref<GraphNode[]>([])
  const links = ref<GraphLink[]>([])
  const selectedNode = ref<GraphNode | null>(null)
  const selectedEdge = ref<GraphLink | null>(null)

  const emptyState = computed(() => !loading.value && nodes.value.length <= 1)
  const emptyMessage = ref('未找到与该资产相关的关系边。')

  // 推断边：relType 属于 D3 集合，或置信度 < 0.6（虚线灰）
  const INFERRED_RELS = new Set(['same_segment', 'shared_tag', 'co_alerted'])
  function isInferred(edge: GraphLink): boolean {
    return INFERRED_RELS.has(edge.relType) || edge.confidence < 0.6
  }

  // 证据正文按可读行展开（过滤 sample_ids 原始数组，单独处理）
  const evidenceLines = computed(() => {
    const ev = selectedEdge.value?.evidence
    if (!ev || typeof ev !== 'object') return []
    const out: { k: string; v: string }[] = []
    for (const [k, v] of Object.entries(ev)) {
      if (k === 'sample_ids') continue
      if (v === null || v === undefined || v === '') continue
      out.push({ k: evidenceKeyLabel(k), v: typeof v === 'object' ? JSON.stringify(v) : String(v) })
    }
    const sample = (ev as any).sample_ids
    if (Array.isArray(sample) && sample.length) {
      out.push({ k: '样例事件 ID', v: sample.slice(0, 5).join(', ') + (sample.length > 5 ? ' …' : '') })
    }
    return out
  })

  function evidenceKeyLabel(k: string): string {
    const map: Record<string, string> = {
      table: '来源表',
      count: '事件次数',
      success: '成功次数',
      fail: '失败次数',
      segment: '网段',
      system_code: '业务系统编码',
      owner_id: '负责人 ID'
    }
    return map[k] || k
  }

  function relTypeName(rel: string): string {
    const map: Record<string, string> = {
      has_port: '开放端口',
      has_vuln: '存在漏洞',
      port_has_vuln: '端口存在漏洞',
      belongs_to_system: '归属业务系统',
      owned_by: '负责人',
      system_owned_by: '系统负责人',
      runs_on: '运行于',
      login_to: '登录到',
      login_from: '登录来源',
      session_on: '会话访问',
      external_access: '外部访问',
      same_segment: '同网段',
      shared_tag: '共享标签',
      co_alerted: '共同告警',
      depends_on: '依赖',
      alerted_on: '产生告警'
    }
    return map[rel] || rel
  }

  function endpointLabel(nodeKey: string): string {
    const n = nodes.value.find((x) => x.id === nodeKey)
    return n ? n.label : shortId(nodeKey)
  }

  function shortId(key: string): string {
    if (!key) return '--'
    // asset:<uuid> → uuid 前 8 位；其余原样
    if (key.startsWith('asset:')) return key.slice(6, 14)
    return key.length > 24 ? key.slice(0, 24) + '…' : key
  }

  function formatTime(t: string | null | undefined): string {
    if (!t) return '--'
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return t
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }

  function confLabel(c: number): string {
    if (c >= 0.9) return '已验证'
    if (c >= 0.6) return '规则归一化'
    return '低置信'
  }

  function confColor(c: number): string {
    if (c >= 0.9) return '#0F6E56'
    if (c >= 0.6) return '#BA7517'
    return '#B4B2A9'
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
    if (v === null || v === undefined) return '--'
    if (typeof v === 'object') return JSON.stringify(v)
    return String(v)
  }

  // ---- 图表生命周期 ----
  // 统一入口：仅在容器可见且有尺寸时初始化；已初始化则 resize。
  function attemptInitOrResize() {
    const el = chartRef.value
    if (!el) return
    if (el.clientWidth <= 0 || el.clientHeight <= 0) return
    if (!chartInstance) initChart()
    else chartInstance.resize()
  }

  let intersectionObserver: IntersectionObserver | null = null

  onMounted(() => {
    // ResizeObserver：尺寸变化（含 TabPane display:none→block 后获得尺寸）
    if (chartRef.value) {
      resizeObserver = new ResizeObserver(() => attemptInitOrResize())
      resizeObserver.observe(chartRef.value)
      // IntersectionObserver：双保险，祖先 display:none→block 时 RO 在个别
      // 时序下不触发首帧；IO 对可见性变化必回调。
      intersectionObserver = new IntersectionObserver((entries) => {
        for (const en of entries) if (en.isIntersecting) attemptInitOrResize()
      })
      intersectionObserver.observe(chartRef.value)
    }
    attemptInitOrResize()
    window.addEventListener('resize', handleWindowResize)
    loadData() // 异步拉数据，不阻塞 observer 注册；数据回来后在 finally 里 render
  })

  function handleWindowResize() {
    if (chartInstance) chartInstance.resize()
  }

  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleWindowResize)
    if (resizeObserver) {
      resizeObserver.disconnect()
      resizeObserver = null
    }
    if (intersectionObserver) {
      intersectionObserver.disconnect()
      intersectionObserver = null
    }
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
  })

  watch(
    () => props.assetId,
    () => {
      selectedNode.value = null
      selectedEdge.value = null
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
      // 数据回来后若已 init 则重渲染；否则等 ResizeObserver 在可见时 init
      if (chartInstance) renderChart()
      else if (chartRef.value && chartRef.value.clientWidth > 0) initChart()
    }
  }

  function initChart() {
    if (!chartRef.value) return
    if (chartInstance) {
      chartInstance.resize()
      renderChart()
      return
    }
    if (chartRef.value.clientWidth <= 0 || chartRef.value.clientHeight <= 0) return
    // 浅色主题（不传 'dark'），与 art-design-pro 整体浅色 UI 一致
    try {
      chartInstance = echarts.init(chartRef.value, undefined, { renderer: 'canvas' })
      renderChart()
    } catch (err) {
      console.error('[RelationGraph] init/render failed', err)
      throw err
    }
    chartInstance.on('click', 'node', (params: any) => {
      const node = nodes.value.find((n) => n.id === params.data.id)
      if (node) {
        selectedNode.value = node
        selectedEdge.value = null
      }
    })
    chartInstance.on('click', 'edge', (params: any) => {
      // 数据上挂了完整 link（见 renderChart links map）
      const link: GraphLink | undefined = params.data?.edge
      if (link) {
        selectedEdge.value = link
        selectedNode.value = null
      }
    })
  }

  // 原型色板（节点类别）
  const CATEGORY_COLORS: Record<string, string> = {
    asset: '#185FA5',
    business_system: '#534AB7',
    account: '#0F6E56',
    vulnerability: '#A32D2D',
    alert_group: '#BA7517',
    segment: '#888780',
    ip: '#1D9E75',
    external: '#1D9E75',
    port: '#5B6E8C',
    person: '#7A5C99',
    department: '#B0854A'
  }

  function renderChart() {
    if (!chartInstance) return
    const centerKey = `asset:${props.assetId}`

    const option: EChartsOption = {
      backgroundColor: 'transparent',
      tooltip: {
        formatter: (params: any) => {
          if (params.dataType === 'edge') {
            const l = params.data.edge as GraphLink | undefined
            if (l) {
              return (
                `<b>${relTypeName(l.relType)}</b><br/>` +
                `置信度: ${(l.confidence * 100).toFixed(0)}%<br/>` +
                `来源: ${l.sourceLabel || '未知'}`
              )
            }
            return ''
          }
          const n = params.data
          return `<b>${n.name}</b><br/>类型: ${categoryLabel(n.category)}`
        }
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          force: {
            repulsion: 460,
            edgeLength: [70, 150],
            gravity: 0.08,
            layoutAnimation: false
          },
          data: nodes.value.map((n) => {
            const isCenter = n.id === centerKey
            return {
              id: n.id,
              name: n.label,
              category: n.category,
              symbolSize: symbolSizeFor(n),
              itemStyle: {
                color: CATEGORY_COLORS[n.category] || '#888780',
                borderColor: '#fff',
                borderWidth: isCenter ? 3 : 1.5
              },
              label: {
                show: true,
                position: 'bottom',
                fontSize: isCenter ? 12 : 11,
                fontWeight: isCenter ? 600 : 400,
                color: isCenter ? '#185FA5' : '#444441'
              }
            }
          }),
          links: links.value.map((l) => ({
            id: l.id,
            source: l.source,
            target: l.target,
            edge: l, // 点击时取回完整证据
            lineStyle: {
              color: isInferred(l) ? '#B4B2A9' : edgeColor(l.relType),
              width: l.lineStyle?.width ?? 1.5,
              type: isInferred(l) ? 'dashed' : 'solid',
              opacity: isInferred(l) ? 0.7 : 0.85,
              curveness: 0.1
            }
          })),
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 3.5 }
          },
          label: {
            show: true,
            position: 'bottom',
            fontSize: 11,
            color: '#444441'
          }
        }
      ]
    }

    chartInstance.setOption(option, true)
  }

  function edgeColor(rel: string): string {
    if (['has_vuln', 'port_has_vuln'].includes(rel)) return '#A32D2D'
    if (['login_to', 'login_from', 'session_on', 'external_access'].includes(rel)) return '#0F6E56'
    if (['belongs_to_system', 'owned_by', 'system_owned_by', 'runs_on'].includes(rel)) return '#185FA5'
    if (['alerted_on', 'co_alerted'].includes(rel)) return '#BA7517'
    return '#5B6E8C'
  }

  function symbolSizeFor(n: GraphNode): number {
    if (n.category === 'asset' && n.id === `asset:${props.assetId}`) return 52
    if (n.category === 'asset') return 30
    if (n.category === 'business_system') return 42
    if (n.category === 'vulnerability') return 24
    if (n.category === 'port') return 14
    if (n.category === 'alert_group') return 18
    if (n.category === 'account') return 16
    return 18
  }

  function closePanel() {
    selectedEdge.value = null
    selectedNode.value = null
  }

  function goAssetDetail(nodeId: string) {
    const assetId = nodeId.replace('asset:', '')
    router.push(`/assets/detail/${assetId}`)
  }

  // 查看原始日志：依据边类型跳到相应页面，尽量带上过滤线索
  function viewRawLog(edge: GraphLink) {
    const ev = edge.evidence || {}
    const centerIp = (nodes.value.find((n) => n.id === `asset:${props.assetId}`)?.rawProps as any)?.ip
    const rel = edge.relType
    // 认证 / 外联 / 会话类 → 告警列表（Wazuh/OpenSearch 证据）
    if (['login_to', 'login_from', 'session_on', 'external_access', 'alerted_on', 'co_alerted'].includes(rel)) {
      const q = centerIp ? `?keyword=${encodeURIComponent(centerIp)}` : ''
      router.push(`/alert/list/index${q}`)
      ElMessage.info('已跳转告警列表，请按证据时间窗与 IP 过滤查看原始日志')
      return
    }
    // 漏洞类 → 漏洞来源在 Wazuh SCA/漏洞状态，暂无独立原始日志页，提示
    if (['has_vuln', 'port_has_vuln'].includes(rel)) {
      ElMessage.info(`漏洞证据来源表：${ev.table || 'wazuh-states-vulnerabilities'}，可在 OpenSearch 中按资产检索`)
      return
    }
    // 其余为台账/人工关系，无"原始日志"概念
    ElMessage.info(`该关系来源为${edge.sourceLabel || '台账登记'}，无原始日志`)
  }

  function emitJoinAi(edge: GraphLink) {
    emit('join-ai', edge)
    ElMessage.success('已加入 AI 研判上下文')
  }
</script>

<style lang="scss" scoped>
  .relation-graph-tab {
    display: flex;
    flex-direction: column;
    height: 620px;
    border: 0.5px solid var(--el-border-color-lighter, #ebeef5);
    border-radius: 8px;
    background: var(--el-bg-color, #fff);
    overflow: hidden;

    .rg-toolbar {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 10px 14px;
      border-bottom: 0.5px solid var(--el-border-color-lighter, #ebeef5);
      flex-shrink: 0;
      flex-wrap: wrap;

      .rg-legend {
        margin-left: auto;
        display: flex;
        gap: 14px;
        font-size: 12px;
        color: var(--el-text-color-secondary, #909399);

        .lg-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .lg-line {
          width: 18px;
          height: 3px;
          border-radius: 1px;
          display: inline-block;
        }
        .lg-strong {
          background: #a32d2d;
        }
        .lg-obs {
          background: #5b6e8c;
        }
        .lg-infer {
          background: repeating-linear-gradient(90deg, #b4b2a9 0 4px, transparent 4px 7px);
        }
      }
    }

    // 主体：左图右证据（对应原型 .detail-main）
    // 父级详情页是自然滚动长页（非固定高度 flex 容器），故 body 用 height:100%
    // 填满 .relation-graph-tab 的固定高，而不是 flex:1（后者在 auto 高度父级里无基准）。
    .rg-body {
      flex: 1 1 auto;
      display: flex;
      min-height: 0;
      height: 0;
    }

    .rg-ego-area {
      flex: 1 1 auto;
      position: relative;
      min-width: 0;
      min-height: 0;
      background: var(--el-fill-color-blank, #fff);
    }

    .rg-chart {
      width: 100%;
      height: 100%;
    }

    .rg-hint {
      position: absolute;
      bottom: 12px;
      left: 16px;
      font-size: 11px;
      color: var(--el-text-color-placeholder, #a8abb2);
      background: var(--el-bg-color, rgba(255, 255, 255, 0.92));
      padding: 4px 10px;
      border-radius: 6px;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
      pointer-events: none;
    }

    .rg-empty {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--el-text-color-secondary, #909399);
      padding: 0 24px;
      text-align: center;
      background: var(--el-bg-color, #fff);

      .empty-icon {
        font-size: 48px;
        color: var(--el-text-color-disabled, #c0c4cc);
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
        color: var(--el-text-color-placeholder, #a8abb2);
      }
    }

    // 右侧证据面板（固定 320px 分栏）
    .rg-evidence-panel {
      width: 320px;
      flex-shrink: 0;
      border-left: 0.5px solid var(--el-border-color-lighter, #ebeef5);
      padding: 16px;
      overflow-y: auto;
      background: var(--el-bg-color, #fff);

      .ev-empty {
        color: var(--el-text-color-placeholder, #a8abb2);
        text-align: center;
        padding: 48px 0;
        font-size: 13px;
        line-height: 1.9;
      }

      .ev-panel-title {
        font-size: 13px;
        font-weight: 600;
        margin: 0 0 12px;
        display: flex;
        align-items: center;
        gap: 8px;

        .ev-close {
          margin-left: auto;
          padding: 0;
          height: auto;
        }
      }

      .ev-type {
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 500;

        &.tag-verified {
          background: #e1f5ee;
          color: #0f6e56;
        }
        &.tag-infer {
          background: #f1efe8;
          color: #5f5e5a;
        }
        &.tag-node {
          background: var(--el-fill-color, #f0f2f5);
          color: var(--el-text-color-regular, #606266);
        }
      }

      .ev-rel-name {
        font-weight: 500;
        font-size: 13px;
        margin-bottom: 6px;
      }
      .ev-flow {
        font-size: 12px;
        color: var(--el-text-color-secondary, #909399);
        margin-bottom: 10px;
        word-break: break-all;

        .ev-arrow {
          color: var(--el-text-color-placeholder, #a8abb2);
          margin: 0 4px;
        }
      }

      .kv {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 8px 0;
        border-bottom: 0.5px solid var(--el-border-color-lighter, #f0f0f0);
        font-size: 12px;

        .k {
          color: var(--el-text-color-placeholder, #a8abb2);
          flex-shrink: 0;
        }
        .v {
          color: var(--el-text-color-primary, #303133);
          text-align: right;
          max-width: 200px;
          word-break: break-all;
        }
        .ev-node-id {
          font-family: var(--el-font-family-mono, monospace);
          font-size: 11px;
        }
      }

      .conf-bar {
        height: 6px;
        background: var(--el-fill-color, #f0f2f5);
        border-radius: 3px;
        margin: 6px 0 2px;
        overflow: hidden;

        i {
          display: block;
          height: 100%;
          border-radius: 3px;
          transition: width 0.3s;
        }
      }

      .ev-evidence {
        background: var(--el-fill-color-light, #f7f8fa);
        border-radius: 8px;
        padding: 12px;
        font-size: 12px;
        color: var(--el-text-color-regular, #606266);
        line-height: 1.7;
        margin: 12px 0;

        .ev-row b {
          color: var(--el-text-color-primary, #303133);
          font-weight: 500;
        }
      }

      .inferred-note {
        background: var(--el-color-warning-light-9, #fdf6ec);
        color: var(--el-color-warning-dark-2, #b88230);
        border-radius: 8px;
        padding: 10px 12px;
        font-size: 11px;
        line-height: 1.6;
        margin-top: 12px;
      }

      .ev-actions {
        display: flex;
        gap: 8px;
        margin-top: 14px;
      }
    }
  }

  // 窄屏：证据面板改为底部，避免挤压（断点 1100px，覆盖详情页侧栏收起后的宽度）
  @media (max-width: 1100px) {
    .relation-graph-tab {
      height: auto;

      .rg-body {
        flex-direction: column;
        height: auto;
      }
      .rg-ego-area {
        flex: none;
        height: 440px;
      }
      .rg-evidence-panel {
        width: 100%;
        border-left: none;
        border-top: 0.5px solid var(--el-border-color-lighter, #ebeef5);
        max-height: 340px;
      }
    }
  }
</style>
