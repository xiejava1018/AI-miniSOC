<!--
  概览仪表板（Console）
  设计对齐：docs/design/2026-08-16-概览仪表板设计.md（v0.2.2）+ 配套 UI 权威稿
  docs/design/2026-08-16-概览仪表板-UI实现.html

  五区块（§2 信息架构）：
  a. 态势条：今日需关注 N 项 + 数据截至 + 数据源健康药丸 + 时间窗（纯 UI）
  b. KPI 六卡（RBAC 裁剪：kpi 键缺失即不渲染对应卡片，§5.2 隐藏而非置灰）
  c. 趋势与分布三卡：告警簇趋势(echarts) / 漏洞严重度分布 / 事件处置漏斗
  d. 我的待办：夜间摘要 + 今日优先处置清单
  e. AI 洞察：覆盖率小标签 + Top 非噪声簇研判建议

  数据：GET /api/v1/dashboard/summary（单接口驱动五区块）+ /dashboard/trend
  显信任原则：接口失败显示骨架/重试按钮，不白屏；单模块 {"error":...} 降级渲染。
-->
<template>
  <div class="console-page">
    <!-- 整体加载失败兜底（显信任：不白屏） -->
    <ElAlert
      v-if="summaryError"
      :title="`概览数据加载失败：${summaryError}`"
      type="error"
      :closable="false"
      class="console-alert"
    >
      <ElButton size="small" type="primary" plain :loading="summaryLoading" @click="loadSummary">
        重试
      </ElButton>
    </ElAlert>

    <!-- ═══ a. 态势条 Posture Bar ═══ -->
    <div class="posture">
      <div class="need" role="button" tabindex="0" @click="scrollToTodos">
        今日需关注 <b>{{ todoCount }}</b> 项
      </div>
      <div class="fresh">
        数据截至
        <b>{{ generatedAtText }}</b>（北京时间）
      </div>
      <div class="pills">
        <span
          v-for="pill in healthPills"
          :key="pill.label"
          class="pill"
          :class="{ warn: pill.warn, off: !pill.warn && !pill.ok }"
          :title="pill.error || pill.label"
        >
          <span class="dot"></span>{{ pill.label }}
        </span>
        <span class="seg">
          <button type="button" :class="{ on: timeWindow === '24h' }" @click="timeWindow = '24h'">
            近 24h
          </button>
          <button type="button" :class="{ on: timeWindow === '7d' }" @click="timeWindow = '7d'">
            近 7 天
          </button>
        </span>
      </div>
    </div>

    <!-- ═══ b. KPI 六卡 ═══ -->
    <div v-if="summaryLoading && !summary" class="kpis">
      <div v-for="i in 6" :key="i" class="kpi kpi--skeleton">
        <ElSkeleton animated :rows="2" style="padding: 4px 0" />
      </div>
    </div>
    <div v-else-if="kpiCards.length" class="kpis">
      <div
        v-for="card in kpiCards"
        :key="card.key"
        class="kpi"
        :class="{ danger: card.danger }"
        role="button"
        tabindex="0"
        :title="card.tooltip"
        @click="go(card.route)"
        @keydown.enter="go(card.route)"
      >
        <div class="t">
          {{ card.title }}
          <span v-if="card.badge" class="badge-kev">{{ card.badge }}</span>
        </div>
        <div class="n">{{ card.value }}</div>
        <div v-if="card.sub" class="sub">
          {{ card.sub }}
          <i v-if="card.note" class="note-orange">{{ card.note }}</i>
        </div>
        <div v-if="card.delta" class="delta">
          <span :class="card.delta.cls">{{ card.delta.text }}</span>
          <template v-if="card.delta.tail"> {{ card.delta.tail }}</template>
        </div>
        <div v-if="card.danger" class="flag"></div>
      </div>
    </div>

    <!-- ═══ c. 趋势与分布三卡 ═══ -->
    <div class="sec-title">趋势与分布</div>
    <div class="grid-3">
      <!-- 告警簇趋势 -->
      <div class="panel">
        <h4>告警簇趋势（distinct 指纹/日）</h4>
        <div v-if="trendLoading && !trend" class="chart-skeleton">
          <ElSkeleton animated :rows="4" />
        </div>
        <div v-else-if="trendError" class="chart-fallback">
          <span>趋势加载失败：{{ trendError }}</span>
          <ElButton size="small" type="primary" plain :loading="trendLoading" @click="loadTrend">
            重试
          </ElButton>
        </div>
        <div v-else-if="trendDays.length" ref="trendChartRef" class="chart-box"></div>
        <div v-else class="chart-fallback"><span>暂无快照数据（快照始于 8/9）</span></div>
        <div class="legend legend--trend">
          <span><i style="background: var(--soc-primary)"></i>每日活跃簇（去重指纹）</span>
        </div>
        <div class="panel-note">
          数据来自 PG 快照表按 distinct fingerprint 聚合，不受 Loki 7 天限制；口径已修复为去重（同指纹跨多次快照不重复计）。
        </div>
      </div>

      <!-- 漏洞严重度分布 -->
      <div class="panel">
        <h4>漏洞严重度分布（未修复 · open/SCAP）</h4>
        <div v-if="vulnDist.total > 0" class="stack">
          <span
            v-for="seg in vulnDist.segments"
            :key="seg.label"
            :style="{ width: seg.width + '%', background: seg.color }"
          ></span>
        </div>
        <div v-else class="chart-fallback"><span>暂无漏洞统计数据</span></div>
        <div class="legend">
          <span v-for="seg in vulnDist.segments" :key="seg.label">
            <i :style="{ background: seg.color }"></i>{{ seg.label }}
          </span>
        </div>
        <div class="panel-note">
          KEV 命中 {{ vulnKevText }}<template v-if="vulnKevNote">——{{ vulnKevNote }}</template
          >；修复同步后此处 KEV 项标红展示。
        </div>
      </div>

      <!-- 事件处置漏斗 -->
      <div class="panel">
        <h4>事件处置漏斗</h4>
        <div class="funnel">
          <div v-for="row in funnelRows" :key="row.label" class="fn">
            <div
              class="fn-bar"
              :style="{ width: row.width + '%', background: row.color }"
            >
              {{ row.text }}
            </div>
            <div class="fn-lab">{{ row.label }}</div>
          </div>
        </div>
        <div class="panel-note">
          闭环率 {{ funnelClosureText }}——"检测到了但处置不动"，漏斗底部几乎无转化，暴露流程瓶颈。
        </div>
      </div>
    </div>

    <!-- ═══ d/e. 我的待办 + AI 洞察 ═══ -->
    <div class="grid-2">
      <!-- d. 我的待办 -->
      <div ref="todosSectionRef" class="panel">
        <div class="sec-title">我的待办</div>

        <!-- 夜间摘要（昨晚 18:00 → 今晨 09:00），文案照 UI 权威稿 -->
        <div v-if="nightItems.length" class="night">
          <span v-for="item in nightItems" :key="item.label">
            <span class="k">{{ item.prefix }}</span>
            <b>{{ item.text }}</b>
          </span>
        </div>

        <div v-if="summaryLoading && !summary" class="chart-skeleton">
          <ElSkeleton animated :rows="4" />
        </div>
        <div v-else-if="todos.length" class="todo">
          <div
            v-for="todo in todos"
            :key="todo.id"
            class="ti"
            role="button"
            tabindex="0"
            @click="goTodo(todo.id)"
            @keydown.enter="goTodo(todo.id)"
          >
            <div class="pri" :class="`pri--${todo.priority}`">
              {{ TODO_PRIORITY_LABEL[todo.priority] || todo.priority }}
            </div>
            <div class="ti-body">
              <div class="h">{{ todo.title }}</div>
              <div class="d">{{ todo.detail }}</div>
            </div>
            <div class="go">{{ todo.action }} →</div>
          </div>
        </div>
        <div v-else class="chart-fallback"><span>当前无待办事项</span></div>
      </div>

      <!-- e. AI 洞察 -->
      <div class="panel panel--ai">
        <div class="sec-title">AI 洞察</div>
        <template v-if="aiInsight">
          <div>
            <span class="tag tag--ok">群体研判 {{ aiInsight.coverage.group_analyses }} 簇 ✓</span>
            <span class="tag tag--warn">个警研判 {{ aiInsight.coverage.single_analyses }} 条 ⚠</span>
          </div>
          <div class="ai-summary">
            过去 7 天完成 <b>{{ aiInsight.coverage.group_analyses }} 个告警簇</b>的群体 AI
            研判。以下为库内非噪声簇的优先建议（按 priority + 置信度取自研判表）：
          </div>
          <ul v-if="aiInsight.top_groups.length" class="ai-list">
            <li v-for="(g, idx) in aiInsight.top_groups" :key="g.fingerprint || idx">
              <div class="ai-item-head">
                <b>{{ g.rule_description || '未命名告警簇' }}</b>
                <span class="ai-pri" :class="`ai-pri--${priorityClass(g.priority)}`">
                  {{ g.priority }}
                </span>
                <span class="ai-conf">{{ confidenceText(g.confidence) }}</span>
              </div>
              <div class="ai-item-meta">
                agent {{ g.agent_id }}<template v-if="g.agent_ip"> · {{ g.agent_ip }}</template>
              </div>
              <div class="ai-item-action">{{ g.recommended_action || '暂无处置建议' }}</div>
            </li>
          </ul>
          <div v-else class="chart-fallback"><span>暂无非噪声簇研判记录</span></div>
          <div class="panel-note">
            覆盖率小标签如实暴露"群体强、个警弱"，为后续 P3 AI 资产增强指明方向。
          </div>
        </template>
        <div v-else-if="summaryLoading && !summary" class="chart-skeleton">
          <ElSkeleton animated :rows="4" />
        </div>
        <div v-else class="chart-fallback"><span>暂无 AI 洞察数据</span></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, onActivated, nextTick, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { echarts, type EChartsOption } from '@/plugins/echarts'
  import { RoutesAlias } from '@/router/routesAlias'
  import { useSettingStore } from '@/store/modules/setting'
  import {
    getDashboardSummary,
    getDashboardTrend,
    isModuleError,
    type DashboardSummary,
    type DashboardTrendResponse,
    type DashboardTodoPriority,
    type DashboardAiInsight
  } from '@/api/dashboard'

  defineOptions({ name: 'Console' })

  const router = useRouter()

  // ── 语义色（与 UI 权威稿 CSS 变量一致）──────────────
  const COLOR = {
    primary: '#5D87FF',
    critical: '#F5222D',
    high: '#FA8C16',
    medium: '#FAAD14',
    low: '#1890FF',
    success: '#52C41A'
  } as const

  // 深色模式（echarts 轴/提示框配色需跟随，切换时重绘）
  const settingStore = useSettingStore()
  const isDark = computed(() => settingStore.isDark)

  // ── 数据状态 ────────────────────────────────────────
  const summary = ref<DashboardSummary | null>(null)
  const summaryLoading = ref(false)
  const summaryError = ref('')
  const trend = ref<DashboardTrendResponse | null>(null)
  const trendLoading = ref(false)
  const trendError = ref('')
  const timeWindow = ref<'24h' | '7d'>('24h') // 纯 UI 状态，本期不联动数据
  let lastLoadedAt = 0

  // ── a. 态势条 ───────────────────────────────────────
  const todoCount = computed(() => todos.value.length)

  const generatedAtText = computed(() => {
    const iso = summary.value?.generated_at
    if (!iso) return '—'
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  })

  /** 数据源健康药丸；Wazuh 药丸映射 PG（Wazuh 告警经快照落 PG，契约无独立探活） */
  const healthPills = computed(() => {
    const h = summary.value?.sources_health
    if (!h || isModuleError(h)) return []
    const pills: { label: string; ok: boolean; warn?: boolean; error?: string }[] = [
      { label: h.postgres?.online !== false ? 'Wazuh 在线' : 'Wazuh 离线', ok: h.postgres?.online !== false },
      { label: h.loki?.online ? 'Loki 在线' : 'Loki 离线', ok: !!h.loki?.online, error: h.loki?.error },
      {
        label: h.opensearch?.online ? 'OpenSearch 在线' : 'OpenSearch 离线',
        ok: !!h.opensearch?.online,
        error: h.opensearch?.error
      }
    ]
    // 采集器纳管数随资产权限裁剪（RBAC：无 /assets 菜单则键缺失）
    if (h.collector) {
      pills.push({ label: `采集器 ${h.collector.managed}/${h.collector.total} 纳管`, ok: false, warn: true })
    }
    return pills
  })

  // ── b. KPI 六卡 ─────────────────────────────────────

  interface KpiCardDef {
    key: string
    title: string
    badge?: string
    value: string
    sub?: string
    note?: string
    delta?: { text: string; cls: string; tail?: string }
    danger?: boolean
    route: string
    tooltip?: string
  }

  /** Δ 环比行：上升红 / 下降绿 / 持平灰（与 UI 稿 .delta .up/.down 一致） */
  const deltaOf = (diff: number | null, tail?: string) => {
    if (diff === null || diff === undefined) return undefined
    if (diff > 0) return { text: `↑ ${diff}`, cls: 'up', tail }
    if (diff < 0) return { text: `↓ ${-diff}`, cls: 'down', tail }
    return { text: '持平', cls: 'flat', tail }
  }

  const pct = (r: number) => `${Math.round(r * 100)}%`

  // 下钻路由 = 后端菜单(soc_menus)注册的运行时路径（DB 驱动菜单模式）。
  // 注意：RoutesAlias 里的值多为"组件路径"（如 AlertGovernance='/alert/governance/index'）
  // 不可用于 router.push；仅 Incidents('/incidents/list') 恰与运行时路径一致。
  const ROUTE = {
    alertGovernance: '/alerts/governance', // 告警治理
    incidents: RoutesAlias.Incidents, // 事件管理（'/incidents/list'）
    vulnerabilities: '/vulnerabilities/list', // 脆弱性列表
    browsingEvent: '/browsing/event', // 行为异常事件
    assets: '/assets/list' // 资产列表
  } as const

  const kpiCards = computed<KpiCardDef[]>(() => {
    const kpi = summary.value?.kpi
    if (!kpi || isModuleError(kpi)) return []
    const cards: KpiCardDef[] = []

    // 1. 活跃告警簇（RBAC 缺失即隐藏）
    if (kpi.active_alert_groups && !isModuleError(kpi.active_alert_groups)) {
      const k = kpi.active_alert_groups
      cards.push({
        key: 'active_alert_groups',
        title: '活跃告警簇',
        badge: '已降噪',
        value: String(k.value),
        sub: '实时聚合 · 快照 distinct 指纹口径',
        delta: deltaOf(k.delta_vs_yesterday, 'vs 昨日'),
        route: ROUTE.alertGovernance,
        tooltip: '告警治理页'
      })
    }

    // 2. 待处置事件
    if (kpi.open_incidents && !isModuleError(kpi.open_incidents)) {
      const k = kpi.open_incidents
      cards.push({
        key: 'open_incidents',
        title: '待处置事件',
        value: String(k.value),
        sub: `闭环率 ${pct(k.closure_rate)} · open ${k.value} / 处理中 ${k.in_progress} / 关闭 ${k.closed}`,
        route: ROUTE.incidents,
        tooltip: '事件管理页'
      })
    }

    // 3. 高危漏洞（含 KEV）
    if (kpi.high_vulns && !isModuleError(kpi.high_vulns)) {
      const k = kpi.high_vulns
      cards.push({
        key: 'high_vulns',
        title: '高危漏洞（未修复）',
        badge: 'KEV',
        value: String(k.value),
        sub: `critical ${k.critical} + high ${k.high}（open/SCAP）· KEV 命中 ${k.kev_hits}`,
        note: k.kev_note, // 黄色"待修"标注（如"同步丢老CVE，待修"）
        route: ROUTE.vulnerabilities,
        tooltip: '脆弱性管理页'
      })
    }

    // 4. 行为异常（24h）
    if (kpi.browsing_anomalies_24h && !isModuleError(kpi.browsing_anomalies_24h)) {
      const k = kpi.browsing_anomalies_24h
      cards.push({
        key: 'browsing_anomalies_24h',
        title: '行为异常（24h）',
        value: String(k.value),
        sub: `累计 ${k.total} · 全部待研判（status=new）`,
        delta: deltaOf(k.value - k.prev_24h, `vs 前 24h ${k.prev_24h}`),
        route: ROUTE.browsingEvent,
        tooltip: '行为事件页'
      })
    }

    // 5. 资产纳管率（危险红样式——最大风险敞口）
    if (kpi.asset_coverage && !isModuleError(kpi.asset_coverage)) {
      const k = kpi.asset_coverage
      const un = k.unmanaged_by_criticality || {}
      const unmanaged = k.total - k.managed
      cards.push({
        key: 'asset_coverage',
        title: '资产纳管率',
        value: pct(k.rate),
        danger: true,
        sub: `${k.managed}/${k.total} 已装 agent · ${unmanaged} 台失察（high ${un.high || 0} / medium ${un.medium || 0} / normal ${un.normal || 0}）`,
        route: ROUTE.assets,
        tooltip: '未纳管资产清单'
      })
    }

    // 6. 今日新增事件
    if (kpi.incidents_today && !isModuleError(kpi.incidents_today)) {
      const k = kpi.incidents_today
      cards.push({
        key: 'incidents_today',
        title: '今日新增事件',
        value: String(k.value),
        sub: `近 7 天 ${k.last_7d} 起`,
        delta: k.value === 0 ? { text: '今日无新事发', cls: 'down' } : undefined,
        route: ROUTE.incidents,
        tooltip: '事件管理页'
      })
    }

    return cards
  })

  // ── c-2. 漏洞严重度分布 ─────────────────────────────
  // TODO(接口待补)：dashboard/summary 目前仅返回 critical/high（open/SCAP 口径），
  // medium/low 无专接口——本期这两段不画，图例标注"接口待补"；
  // 后端补全后在此接入 kpi.high_vulns 之外的分档数据。
  const vulnDist = computed(() => {
    const kpi = summary.value?.kpi
    const k = kpi && !isModuleError(kpi) ? kpi.high_vulns : undefined
    if (!k || isModuleError(k)) return { total: 0, segments: [] as { label: string; color: string; width: number }[] }
    const total = k.critical + k.high
    const mk = (label: string, color: string, n: number) => ({
      label: `${label} ${n}`,
      color,
      width: total > 0 ? (n / total) * 100 : 0
    })
    return {
      total,
      segments: [
        mk('Critical', COLOR.critical, k.critical),
        mk('High', COLOR.high, k.high)
        // TODO(接口待补)：Medium #FAAD14 / Low #1890FF 两段待后端补 medium/low 分档
      ]
    }
  })

  const vulnKevText = computed(() => {
    const kpi = summary.value?.kpi
    const k = kpi && !isModuleError(kpi) ? kpi.high_vulns : undefined
    return k && !isModuleError(k) ? String(k.kev_hits) : '—'
  })

  const vulnKevNote = computed(() => {
    const kpi = summary.value?.kpi
    const k = kpi && !isModuleError(kpi) ? kpi.high_vulns : undefined
    return k && !isModuleError(k) ? k.kev_note || '' : ''
  })

  // ── c-3. 事件处置漏斗 ───────────────────────────────
  const funnelRows = computed(() => {
    const kpi = summary.value?.kpi
    const k = kpi && !isModuleError(kpi) ? kpi.open_incidents : undefined
    const open = k && !isModuleError(k) ? k.value : 0
    const inProgress = k && !isModuleError(k) ? k.in_progress : 0
    const closed = k && !isModuleError(k) ? k.closed : 0
    const max = Math.max(open, inProgress, closed, 1)
    return [
      { text: `${open} open`, label: '待处置', value: open, color: COLOR.primary, width: (open / max) * 100 },
      { text: `${inProgress}`, label: '处理中', value: inProgress, color: COLOR.high, width: (inProgress / max) * 100 },
      { text: `${closed}`, label: '已关闭', value: closed, color: COLOR.success, width: (closed / max) * 100 }
    ]
  })

  const funnelClosureText = computed(() => {
    const kpi = summary.value?.kpi
    const k = kpi && !isModuleError(kpi) ? kpi.open_incidents : undefined
    return k && !isModuleError(k) ? pct(k.closure_rate) : '—'
  })

  // ── d. 我的待办 ─────────────────────────────────────
  const todosSectionRef = ref<HTMLElement>()
  const scrollToTodos = () =>
    todosSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  const TODO_PRIORITY_LABEL: Record<DashboardTodoPriority, string> = {
    p0: '紧急',
    p1: '高',
    p2: '中'
  }

  const todos = computed(() => {
    const t = summary.value?.todos
    if (!t || isModuleError(t)) return []
    return t
  })

  // 待办 id → 下钻路由（资产列表 / 事件 / 行为事件 / 告警治理）
  const TODO_ROUTES: Record<string, string> = {
    asset_coverage: ROUTE.assets,
    incident_backlog: ROUTE.incidents,
    browsing_review: ROUTE.browsingEvent,
    ai_coverage: ROUTE.alertGovernance
  }
  const goTodo = (id: string) => {
    const route = TODO_ROUTES[id]
    if (route) go(route)
  }

  /** 夜间摘要条目（分项随模块权限裁剪，缺失即不渲染）；文案照 UI 稿 */
  const nightItems = computed(() => {
    const n = summary.value?.night_summary
    if (!n || isModuleError(n)) return []
    const items: { label: string; prefix: string; text: string }[] = []
    if (n.new_alert_groups !== undefined)
      items.push({
        label: 'new_alert_groups',
        prefix: '夜间摘要 18:00→09:00',
        text: `新增告警簇 ${n.new_alert_groups}`
      })
    if (n.new_incidents !== undefined)
      items.push({ label: 'new_incidents', prefix: '新增事件', text: String(n.new_incidents) })
    if (n.browsing_anomalies !== undefined)
      items.push({
        label: 'browsing_anomalies',
        prefix: '高危行为',
        text: String(n.browsing_anomalies)
      })
    if (n.kev_new !== undefined)
      items.push({ label: 'kev_new', prefix: 'KEV 漏洞新增', text: String(n.kev_new) })
    return items
  })

  // ── e. AI 洞察 ──────────────────────────────────────
  const aiInsight = computed<DashboardAiInsight | null>(() => {
    const a = summary.value?.ai_insight
    if (!a || isModuleError(a)) return null
    return a
  })

  const priorityClass = (p: string) => {
    const key = (p || '').toUpperCase()
    if (key === 'P0') return 'p0'
    if (key === 'P1') return 'p1'
    if (key === 'P2') return 'p2'
    return 'p3'
  }

  const confidenceText = (c: number) =>
    typeof c === 'number' ? `${Math.round(c * 100)}%` : '—'

  // ── c-1. 告警簇趋势（echarts）──────────────────────
  const trendChartRef = ref<HTMLElement>()
  let trendChart: any = null

  const trendDays = computed(() => trend.value?.days || [])

  const renderTrendChart = () => {
    if (!trendChartRef.value || !trendDays.value.length) return
    if (trendChart) trendChart.dispose()
    trendChart = echarts.init(trendChartRef.value)
    const days = trendDays.value
    const axisColor = isDark.value ? '#8f8fa3' : '#8C8C8C' // 深色用 art-gray-600
    // 峰值标注：markPoint max（趋势接口仅含 clusters 总量，无分级别数据，
    // 故先画总量柱状 + 峰值标注，图注说明 distinct 指纹口径）
    trendChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: isDark.value ? '#161618' : '#fff',
        borderColor: isDark.value ? '#363843' : '#e8e8e8',
        textStyle: { color: isDark.value ? '#e3e3e8' : '#1f1f1f', fontSize: 12 },
        formatter: (params: any) => {
          const p = Array.isArray(params) ? params[0] : params
          return `${p?.name}<br/>告警簇：<b>${p?.value}</b>（distinct 指纹）`
        }
      },
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: days.map((d) => shortDate(d.date)),
        axisLabel: { fontSize: 11, color: axisColor },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLabel: { fontSize: 11, color: axisColor },
        splitLine: { lineStyle: { color: isDark.value ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)' } }
      },
      series: [
        {
          name: '告警簇',
          type: 'bar',
          data: days.map((d) => d.clusters),
          itemStyle: { color: COLOR.primary, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 34,
          markPoint: {
            data: [{ type: 'max', name: '峰值' }],
            symbolSize: 44,
            itemStyle: { color: COLOR.critical },
            label: { fontSize: 10, color: '#fff' }
          }
        }
      ]
    } as EChartsOption)
  }

  const shortDate = (date: string) => {
    const d = new Date(date)
    if (isNaN(d.getTime())) return date
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  // ── 数据加载 ────────────────────────────────────────
  const loadSummary = async () => {
    summaryLoading.value = true
    summaryError.value = ''
    try {
      const res = await getDashboardSummary()
      summary.value = res.data
      lastLoadedAt = Date.now()
    } catch (e: any) {
      console.error('[Console] summary 加载失败:', e)
      summaryError.value = e?.message || '网络错误'
    } finally {
      summaryLoading.value = false
    }
  }

  const loadTrend = async () => {
    trendLoading.value = true
    trendError.value = ''
    try {
      const res = await getDashboardTrend(14)
      trend.value = res.data
      await nextTick()
      renderTrendChart()
    } catch (e: any) {
      console.error('[Console] trend 加载失败:', e)
      trendError.value = e?.message || '网络错误'
    } finally {
      trendLoading.value = false
    }
  }

  // ── 跳转 ────────────────────────────────────────────
  const go = (route: string) => {
    router.push(route)
  }

  // ── 生命周期（echarts init/resize/dispose，同 vulnerability/overview 范式）──
  const handleResize = () => trendChart?.resize()

  // 深浅色切换时重绘图表（轴/提示框配色跟随主题）
  watch(isDark, () => {
    if (trendDays.value.length) renderTrendChart()
  })

  onMounted(() => {
    loadSummary()
    loadTrend()
    window.addEventListener('resize', handleResize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize)
    trendChart?.dispose()
    trendChart = null
  })

  // keep-alive 缓存页回到前台时，数据超过 60s 则静默刷新（SOC 页首屏价值在"数据截至"）
  onActivated(() => {
    if (lastLoadedAt && Date.now() - lastLoadedAt > 60_000) {
      loadSummary()
      loadTrend()
    }
  })
</script>

<style lang="scss" scoped>
  /* 主题化视觉令牌：语义色固定，结构色全部走 Element Plus / 项目主题变量，
     深浅色模式自动切换（对齐资产概览/脆弱性概览的做法，不硬编码背景） */
  .console-page {
    --soc-primary: var(--el-color-primary);
    --soc-critical: var(--el-color-danger);
    --soc-high: var(--el-color-warning);
    --soc-medium: var(--el-color-warning-light-3);
    --soc-low: var(--el-color-primary);
    --soc-success: var(--el-color-success);

    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    color: var(--el-text-color-primary);
  }

  .console-alert {
    :deep(.el-alert__content) {
      display: flex;
      align-items: center;
      gap: 10px;
    }
  }

  /* ═══ a. 态势条 ═══（主题化卡片：浅色白底 / 深色随 --default-box-color，
     与资产概览 metric-card 同范式；不再用硬编码深蓝） */
  .posture {
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: 12px;
    padding: 14px 20px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 18px;

    .need {
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      color: var(--el-text-color-primary);

      b {
        font-size: 22px;
        color: var(--el-color-danger);
        margin-right: 4px;
      }

      &:hover {
        opacity: 0.85;
      }
    }

    .fresh {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      display: flex;
      flex-direction: column;

      b {
        color: var(--el-text-color-primary);
        font-weight: 600;
        font-size: 13px;
      }
    }

    .pills {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-left: auto;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--art-el-active-color);
      border: 1px solid var(--art-card-border);
      padding: 5px 11px;
      border-radius: 20px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
      cursor: default;

      .dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--soc-success);
        box-shadow: 0 0 0 3px rgba(82, 196, 26, 0.25);
        flex-shrink: 0;
      }

      &.warn .dot {
        background: var(--el-color-warning);
        box-shadow: 0 0 0 3px rgba(230, 162, 60, 0.25);
      }

      &.off .dot {
        background: var(--soc-critical);
        box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.25);
      }
    }

    .seg {
      display: inline-flex;
      background: var(--art-el-active-color);
      border-radius: 8px;
      padding: 3px;

      button {
        border: 0;
        background: transparent;
        color: var(--el-text-color-secondary);
        font-size: 12px;
        padding: 5px 12px;
        border-radius: 6px;
        cursor: pointer;

        &.on {
          background: var(--soc-primary);
          color: #fff;
        }
      }
    }
  }

  /* ═══ b. KPI 卡 ═══ */
  .kpis {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 14px;
  }

  .kpi {
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: 12px;
    padding: 16px;
    position: relative;
    overflow: hidden;
    cursor: pointer;
    transition:
      box-shadow 0.15s,
      border-color 0.15s;

    &:hover {
      border-color: var(--el-color-primary-light-5);
      box-shadow: var(--el-box-shadow-light);
    }

    .t {
      font-size: 12.5px;
      color: var(--el-text-color-secondary);
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .n {
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.5px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }

    .sub {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      margin-top: 8px;
      line-height: 1.5;
    }

    .note-orange {
      font-style: normal;
      color: var(--el-color-warning);
    }

    .delta {
      font-size: 11px;
      margin-top: 6px;
      color: var(--el-text-color-secondary);

      .up {
        color: var(--soc-critical);
        font-weight: 600;
      }

      .down {
        color: var(--soc-success);
        font-weight: 600;
      }

      .flat {
        color: var(--el-text-color-secondary);
      }
    }

    .flag {
      position: absolute;
      top: 0;
      right: 0;
      width: 4px;
      height: 100%;
    }

    &.danger {
      // light-N 变量由 EP dark css-vars 在深色下自动重映射为暗色，无需手动分支
      border-color: var(--el-color-danger-light-7);
      background: var(--el-color-danger-light-9);

      .n {
        color: var(--soc-critical);
      }

      .flag {
        background: var(--soc-critical);
      }
    }

    &--skeleton {
      cursor: default;
      min-height: 128px;
    }
  }

  .badge-kev {
    font-size: 10px;
    background: var(--el-color-primary-light-9);
    color: var(--soc-primary);
    border-radius: 4px;
    padding: 1px 6px;
    font-weight: 600;
    flex-shrink: 0;
  }

  /* ═══ 区块标题 / 通用面板 ═══ */
  .sec-title {
    font-size: 15px;
    font-weight: 600;
    margin: 2px 0 0;
    display: flex;
    align-items: center;
    gap: 8px;

    &::before {
      content: '';
      width: 4px;
      height: 15px;
      background: var(--soc-primary);
      border-radius: 2px;
    }
  }

  .panel {
    background: var(--default-box-color);
    border: 1px solid var(--art-card-border);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;

    h4 {
      font-size: 13px;
      font-weight: 600;
      margin: 0 0 14px;
      color: var(--el-text-color-primary);
    }
  }

  .panel-note {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    margin-top: 10px;
    line-height: 1.7;
  }

  .chart-box {
    width: 100%;
    height: 230px;
  }

  .chart-skeleton {
    padding: 12px 4px;
    flex: 1;
  }

  .chart-fallback {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 40px 0;
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }

  /* ═══ c. 趋势与分布三卡 ═══ */
  .grid-3 {
    display: grid;
    grid-template-columns: 1.3fr 1fr 1fr;
    gap: 14px;
    margin-top: -6px; // 抵消 sec-title 与 grid 间多余空隙（外层已 gap:18px）
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    font-size: 12px;
    color: var(--el-text-color-primary);

    i {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 3px;
      margin-right: 6px;
      vertical-align: middle;
    }

    &--trend {
      margin-top: 10px;
    }
  }

  /* 漏洞分布堆叠条 */
  .stack {
    height: 26px;
    width: 100%;
    border-radius: 6px;
    overflow: hidden;
    display: flex;
    margin: 6px 0 14px;

    span {
      height: 100%;
    }
  }

  /* 事件漏斗 */
  .funnel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 6px;

    .fn {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .fn-bar {
      height: 34px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      padding: 0 12px;
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      min-width: 54px;
      transition: width 0.4s ease;
    }

    .fn-lab {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      flex-shrink: 0;
    }
  }

  /* ═══ d/e. 待办 + AI 洞察 ═══ */
  .grid-2 {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 14px;
    align-items: stretch; // 两卡底部对齐（grid 默认拉伸；此前误设 start 导致不齐）
  }

  /* 夜间摘要：主题化强调卡（浅色=主色浅底 / 深色自动跟随），
     不再用硬编码深蓝横幅，与系统风格一致 */
  .night {
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-8);
    color: var(--el-text-color-primary);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 14px;
    font-size: 12.5px;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;

    b {
      color: var(--soc-primary);
      font-variant-numeric: tabular-nums;
    }

    .k {
      color: var(--el-text-color-secondary);
      margin-right: 5px;
    }
  }

  .todo {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .ti {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 14px;
    border: 1px solid var(--art-card-border);
    border-radius: 10px;
    background: var(--art-el-active-color);
    transition: border-color 0.15s;
    cursor: pointer;

    &:hover {
      border-color: var(--soc-primary);
    }

    .pri {
      flex-shrink: 0;
      font-size: 11px;
      font-weight: 700;
      color: #fff;
      border-radius: 6px;
      padding: 3px 9px;
      margin-top: 2px;

      &--p0 {
        background: var(--soc-critical);
      }

      &--p1 {
        background: var(--el-color-warning);
      }

      &--p2 {
        background: var(--el-color-warning-light-5);
        color: var(--el-text-color-primary);
      }
    }

    .ti-body {
      .h {
        font-size: 13.5px;
        font-weight: 600;
      }

      .d {
        font-size: 12px;
        color: var(--el-text-color-secondary);
        margin-top: 3px;
      }
    }

    .go {
      margin-left: auto;
      font-size: 12px;
      color: var(--soc-primary);
      white-space: nowrap;
      align-self: center;
    }
  }

  .tag {
    display: inline-block;
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 6px;
    margin-right: 6px;
    margin-bottom: 6px;

    &--ok {
      background: var(--el-color-success-light-9);
      color: var(--soc-success);
    }

    &--warn {
      background: var(--el-color-warning-light-9);
      color: var(--el-color-warning);
    }
  }

  .ai-summary {
    font-size: 13px;
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--art-card-border);
    border-radius: 10px;
    padding: 14px;
    margin: 12px 0;
    line-height: 1.7;

    b {
      color: var(--soc-primary);
    }
  }

  .ai-list {
    list-style: none;
    padding: 0;
    margin: 4px 0 0;
    display: flex;
    flex-direction: column;
    gap: 10px;

    li {
      border: 1px solid var(--art-card-border);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 12.5px;
    }

    .ai-item-head {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;

      b {
        font-size: 13px;
      }
    }

    .ai-pri {
      font-size: 10px;
      font-weight: 700;
      color: #fff;
      border-radius: 4px;
      padding: 1px 6px;
      flex-shrink: 0;

      &--p0 {
        background: var(--soc-critical);
      }

      &--p1 {
        background: var(--el-color-warning);
      }

      &--p2 {
        background: var(--el-color-warning-light-5);
        color: var(--el-text-color-primary);
      }

      &--p3 {
        background: var(--el-color-primary-light-5);
        color: var(--el-text-color-primary);
      }
    }

    .ai-conf {
      font-size: 11px;
      color: var(--el-text-color-secondary);
      font-variant-numeric: tabular-nums;
    }

    .ai-item-meta {
      font-size: 11.5px;
      color: var(--el-text-color-secondary);
      margin-top: 3px;
    }

    .ai-item-action {
      font-size: 12px;
      margin-top: 5px;
      color: var(--el-text-color-primary);
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
  }

  /* ═══ 响应式（照 UI 稿断点）═══ */
  @media (max-width: 1080px) {
    .kpis {
      grid-template-columns: repeat(3, 1fr);
    }

    .grid-3 {
      grid-template-columns: 1fr;
    }

    .grid-2 {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 560px) {
    .kpis {
      grid-template-columns: repeat(2, 1fr);
    }

    .posture {
      gap: 12px;

      .pills {
        margin-left: 0;
      }
    }
  }
</style>
