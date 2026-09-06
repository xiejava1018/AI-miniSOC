<template>
  <div class="bp-page art-full-height" v-loading="loading">
    <ElRow :gutter="12" class="bp-layout">
      <!-- 左栏：主体列表 -->
      <ElCol :span="6">
        <ElCard shadow="never" class="bp-subjects" :body-style="{ padding: '8px' }">
          <template #header>
            <div class="card-head">
              <span class="card-title">画像主体</span>
              <ElButton size="small" text @click="compareVisible = true">对比</ElButton>
            </div>
            <ElRadioGroup v-model="trafficFilter" size="small" @change="loadList" class="mt8">
              <ElRadioButton value="">全部</ElRadioButton>
              <ElRadioButton value="human">人类</ElRadioButton>
              <ElRadioButton value="machine">机器</ElRadioButton>
            </ElRadioGroup>
          </template>
          <div
            v-for="item in sortedSubjects"
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
            <div class="subj-tags" v-if="item.traffic_type !== 'machine'">
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

      <!-- 右栏：画像详情（四 Tab，§3.0） -->
      <ElCol :span="18">
        <template v-if="profile">
          <!-- 异常横幅（层5，有信号才显示） -->
          <ElAlert
            v-if="anomalies?.banner"
            type="warning"
            :closable="false"
            class="bp-banner"
            @click="activeTab = 'anomaly'"
          >
            <template #title>
              ⚠ 异常信号：{{ anomalies.banner.name }} —— {{ anomalies.banner.desc }}
              <ElLink type="primary" @click.stop="activeTab = 'anomaly'">查看全部 →</ElLink>
            </template>
          </ElAlert>

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
                    {{ profile.asset?.owner ? ` · owner: ${profile.asset.owner}` : ' · 未登记责任人' }}
                  </span>
                </div>
              </div>
              <div class="idbar-right">
                <ElSelect v-model="days" size="small" style="width: 110px" @change="reload">
                  <ElOption :value="7" label="近 7 天" />
                  <ElOption :value="14" label="近 14 天" />
                  <ElOption :value="30" label="近 30 天" />
                </ElSelect>
                <ElTag effect="plain">访问 {{ formatNumber(profile.total) }}</ElTag>
                <ElTooltip content="置信度由数据量与查询截断情况计算（§9.7 偏差说明）">
                  <ElTag effect="plain" :type="profile.confidence >= 60 ? 'success' : 'warning'">
                    置信度 {{ profile.confidence }}
                  </ElTag>
                </ElTooltip>
                <ElTag v-if="profile.gap_days" effect="plain" type="danger">
                  {{ profile.gap_days }} 天数据缺失
                </ElTag>
                <ElButton v-if="hasAuth('refresh')" size="small" :loading="refreshing" @click="onRefresh">
                  实时刷新
                </ElButton>
                <ElButton size="small" type="primary" plain :loading="aiLoading" @click="onAiSummary">
                  AI 解读
                </ElButton>
                <ElButton size="small" @click="onExport">导出</ElButton>
              </div>
            </div>
            <div class="idbar-watermark">本数据仅用于安全审计</div>
          </ElCard>

          <!-- Tab 切换 -->
          <ElTabs v-model="activeTab" class="bp-tabs">
            <!-- ═══ Tab 1: 行为画像（层2） ═══ -->
            <ElTabPane label="行为画像" name="behavior">
              <ElCard v-if="aiResult" shadow="never" class="bp-card">
                <ElAlert :type="aiResult.source === 'glm' ? 'success' : 'warning'" :closable="false">
                  <template #title>
                    AI 解读（{{ aiResult.source === 'glm' ? 'GLM 生成' : '规则模板（AI 不可用降级）' }}）
                    · 仅输出信号不定性，须人工复核 · 仅用于安全审计
                  </template>
                  <div class="ai-body">
                    <div class="ai-sec"><b>摘要</b><pre>{{ aiResult.summary }}</pre></div>
                    <div class="ai-sec"><b>异常解读</b><pre>{{ aiResult.anomaly_interpretation }}</pre></div>
                    <div class="ai-sec"><b>建议动作</b><pre>{{ aiResult.recommendations }}</pre></div>
                  </div>
                </ElAlert>
              </ElCard>

              <ElCard shadow="never" class="bp-card">
                <template #header>
                  <span class="card-title">画像标签</span>
                  <span class="card-sub">规则判定，每项附证据；人设别名见箭头</span>
                </template>
                <div v-if="behaviorVisibleTags.length" class="tag-grid">
                  <div v-for="t in behaviorVisibleTags" :key="t.name" class="ptag" :style="{ '--tc': t.color }">
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

              <ElRow :gutter="12">
                <ElCol :span="14">
                  <ElCard shadow="never" class="bp-card">
                    <template #header><span class="card-title">24 小时活跃曲线</span></template>
                    <div ref="hourRef" class="chart-box" style="height: 210px"></div>
                  </ElCard>
                </ElCol>
                <ElCol :span="10">
                  <ElCard shadow="never" class="bp-card">
                    <template #header>
                      <span class="card-title">时段分布</span>
                      <span class="card-sub">工作日 {{ workdayShare }}% · 周末 {{ weekendShare }}%</span>
                    </template>
                    <div ref="blockRef" class="chart-box" style="height: 210px"></div>
                  </ElCard>
                </ElCol>
              </ElRow>

              <ElCard shadow="never" class="bp-card">
                <template #header>
                  <span class="card-title">星期 × 小时 行为热力图</span>
                  <span class="card-sub">颜色越深访问越密集（UTC+8）—— 行为节律核心视图</span>
                </template>
                <div ref="heatRef" class="chart-box" style="height: 230px"></div>
              </ElCard>

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
                      <span class="card-title">各时段在干什么</span>
                      <span class="card-sub">分类 × 时段堆叠 —— 一眼看"半夜在刷什么"</span>
                    </template>
                    <div ref="stackRef" class="chart-box" style="height: 220px"></div>
                  </ElCard>
                </ElCol>
              </ElRow>

              <ElCard shadow="never" class="bp-card">
                <template #header><span class="card-title">多日趋势</span>
                  <span class="card-sub">灰色段 = 数据缺失（Loki 窗口外）</span>
                </template>
                <div ref="trendRef" class="chart-box" style="height: 200px"></div>
              </ElCard>

              <ElCard shadow="never" class="bp-card">
                <template #header><span class="card-title">访问域名 TOP 20</span>
                  <span class="card-sub">点域名查看逐日明细</span>
                </template>
                <ElTable :data="profile.top_domains || []" size="small" max-height="360">
                  <ElTableColumn prop="domain" label="域名" min-width="220">
                    <template #default="{ row }">
                      <ElLink type="primary" @click="openDomainDrill(row.domain)">{{ row.domain }}</ElLink>
                    </template>
                  </ElTableColumn>
                  <ElTableColumn prop="category" label="分类" width="110" />
                  <ElTableColumn prop="visits" label="访问量" width="100">
                    <template #default="{ row }">{{ formatNumber(row.visits) }}</template>
                  </ElTableColumn>
                  <ElTableColumn prop="share" label="占比" width="90">
                    <template #default="{ row }">{{ row.share }}%</template>
                  </ElTableColumn>
                </ElTable>
              </ElCard>
            </ElTabPane>

            <!-- ═══ Tab 2: 风险画像（层3） ═══ -->
            <ElTabPane label="风险画像" name="risk">
              <template v-if="risk">
                <ElAlert v-if="risk.note" type="info" :closable="false" class="bp-banner" :title="risk.note" />
                <ElRow :gutter="12">
                  <ElCol :span="6" v-for="k in riskKpis" :key="k.l">
                    <ElCard shadow="never" class="bp-card kpi-card" :body-style="{ padding: '12px' }">
                      <div class="kpi-v" :style="{ color: k.c }">{{ k.v }}</div>
                      <div class="kpi-l">{{ k.l }}</div>
                    </ElCard>
                  </ElCol>
                </ElRow>
                <ElRow :gutter="12">
                  <ElCol :span="14">
                    <ElCard shadow="never" class="bp-card">
                      <template #header>
                        <span class="card-title">告警规则榜</span>
                        <span class="card-sub">real = AI 去噪后计数（ai_is_noise=false）</span>
                      </template>
                      <ElTable :data="risk.top_rules" size="small" max-height="300">
                        <ElTableColumn label="级别" width="70">
                          <template #default="{ row }">
                            <ElTag size="small" effect="plain" :type="levelType(row.level)">L{{ row.level }}</ElTag>
                          </template>
                        </ElTableColumn>
                        <ElTableColumn prop="description" label="规则" min-width="200" show-overflow-tooltip />
                        <ElTableColumn prop="count" label="总条数" width="90" />
                        <ElTableColumn prop="real_count" label="去噪后" width="90" />
                      </ElTable>
                    </ElCard>
                  </ElCol>
                  <ElCol :span="10">
                    <ElCard shadow="never" class="bp-card">
                      <template #header><span class="card-title">漏洞严重度分布</span></template>
                      <div ref="vulnRef" class="chart-box" style="height: 180px"></div>
                      <div v-if="risk.vulns.kev?.length" class="kev">
                        <ElTag v-for="k in risk.vulns.kev" :key="k.cve_id" size="small" type="danger" effect="plain" class="kev-tag">
                          🔥 {{ k.cve_id }}
                        </ElTag>
                      </div>
                    </ElCard>
                  </ElCol>
                </ElRow>
                <ElRow :gutter="12">
                  <ElCol :span="12">
                    <ElCard shadow="never" class="bp-card">
                      <template #header><span class="card-title">暴露端口</span></template>
                      <div class="ports">
                        <span v-for="p in risk.ports.items" :key="p.port + p.protocol"
                              class="port" :class="{ danger: p.danger }">
                          {{ p.port }}/{{ p.protocol }}
                          <small v-if="p.service">{{ p.service }}</small>
                        </span>
                        <span v-if="!risk.ports.items?.length" class="dim">无开放端口记录</span>
                      </div>
                    </ElCard>
                  </ElCol>
                  <ElCol :span="12">
                    <ElCard shadow="never" class="bp-card">
                      <template #header>
                        <span class="card-title">风险评分趋势</span>
                        <span class="card-sub">
                          {{ risk.risk_trend_days >= 5 ? '' : '数据不足 5 天，趋势仅供参考' }}
                        </span>
                      </template>
                      <div ref="riskTrendRef" class="chart-box" style="height: 180px"></div>
                    </ElCard>
                  </ElCol>
                </ElRow>
              </template>
              <ElCard v-else shadow="never" class="bp-card"><ElEmpty description="加载中…" /></ElCard>
            </ElTabPane>

            <!-- ═══ Tab 3: 关系画像（层4，身份管道已上线） ═══ -->
            <ElTabPane label="关系画像" name="rel">
              <template v-if="relations">
                <ElAlert v-if="relations.note" type="info" :closable="false" class="bp-banner" :title="relations.note" />
                <ElRow :gutter="12">
                  <ElCol :span="8">
                    <ElCard shadow="never" class="bp-card">
                      <template #header><span class="card-title">设备共享度</span></template>
                      <div class="rel-stat">
                        <div class="kpi-v">{{ relations.device_shared_by }}</div>
                        <div class="kpi-l">个账号在用本机</div>
                      </div>
                      <div class="rel-accounts">
                        <ElTag v-for="a in relations.accounts_on_host" :key="a" size="small" effect="plain" class="acc-tag">
                          {{ a }}
                        </ElTag>
                      </div>
                      <div class="rel-fail" v-if="relations.inbound_fail_total">
                        失败登录 {{ relations.inbound_fail_total }} 次
                      </div>
                    </ElCard>
                    <ElCard shadow="never" class="bp-card" v-if="relations.external_attackers?.length">
                      <template #header><span class="card-title">外部攻击源</span></template>
                      <div class="ports">
                        <span v-for="x in relations.external_attackers" :key="x.ip" class="port danger">
                          {{ x.ip }} <small>{{ x.count }} 次失败</small>
                        </span>
                      </div>
                    </ElCard>
                  </ElCol>
                  <ElCol :span="8">
                    <ElCard shadow="never" class="bp-card">
                      <template #header><span class="card-title">入站登录（谁登了本机）</span></template>
                      <ElTable :data="relations.inbound" size="small" max-height="320">
                        <ElTableColumn prop="account" label="账号" width="100" />
                        <ElTableColumn prop="ip" label="来源 IP" width="130" />
                        <ElTableColumn prop="count" label="次数" width="70" />
                      </ElTable>
                      <ElEmpty v-if="!relations.inbound?.length" description="无入站登录记录" :image-size="50" />
                    </ElCard>
                  </ElCol>
                  <ElCol :span="8">
                    <ElCard shadow="never" class="bp-card">
                      <template #header><span class="card-title">出站登录（本机登了谁）</span></template>
                      <ElTable :data="relations.outbound" size="small" max-height="320">
                        <ElTableColumn prop="account" label="账号" width="100" />
                        <ElTableColumn label="目标" width="130">
                          <template #default="{ row }">
                            <ElLink type="primary" @click="selectSubject(row.ip)">{{ row.ip }}</ElLink>
                          </template>
                        </ElTableColumn>
                        <ElTableColumn prop="count" label="次数" width="70" />
                      </ElTable>
                      <ElEmpty v-if="!relations.outbound?.length" description="无出站登录记录" :image-size="50" />
                    </ElCard>
                  </ElCol>
                </ElRow>
              </template>
              <ElCard v-else shadow="never" class="bp-card"><ElEmpty description="加载中…" /></ElCard>
            </ElTabPane>

            <!-- ═══ Tab 4: 异常判定（层5） ═══ -->
            <ElTabPane :label="`异常判定${anomalies?.has_anomaly ? ' ⚠' : ''}`" name="anomaly">
              <ElCard shadow="never" class="bp-card">
                <template #header>
                  <span class="card-title">异常信号清单</span>
                  <span class="card-sub">{{ anomalies?.disclaimer }}</span>
                </template>
                <ElTable :data="anomalies?.signals || []" size="default">
                  <ElTableColumn label="级别" width="80">
                    <template #default="{ row }">
                      <ElTag size="small" :type="row.severity === 'mid' ? 'warning' : 'info'">
                        {{ row.severity === 'mid' ? '中' : '提示' }}
                      </ElTag>
                    </template>
                  </ElTableColumn>
                  <ElTableColumn prop="name" label="信号" width="160" />
                  <ElTableColumn prop="desc" label="描述" min-width="180" />
                  <ElTableColumn prop="evidence" label="证据" min-width="240" />
                </ElTable>
                <ElEmpty v-if="!anomalies?.signals?.length" description="未命中任何异常信号" :image-size="60" />
              </ElCard>
            </ElTabPane>
          </ElTabs>
        </template>
        <ElCard v-else shadow="never" class="bp-card">
          <ElEmpty description="选择左侧主体查看画像，或等待快照任务生成数据" />
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 域名下钻 -->
    <ElDialog v-model="drillVisible" :title="`域名明细 — ${drillDomain}`" width="520px">
      <ElTable :data="drillData" size="small" max-height="380" v-loading="drillLoading">
        <ElTableColumn prop="date" label="日期" width="120" />
        <ElTableColumn prop="visits" label="访问次数" />
        <ElTableColumn prop="category" label="分类" width="120" />
      </ElTable>
      <ElEmpty v-if="!drillData.length && !drillLoading" description="窗口内无该域名记录" :image-size="50" />
    </ElDialog>

    <!-- 双 IP 对比 -->
    <ElDialog v-model="compareVisible" title="双 IP 画像对比" width="480px">
      <ElForm label-width="80px">
        <ElFormItem label="IP A">
          <ElSelect v-model="cmpA" filterable allow-create placeholder="选择或输入 IP">
            <ElOption v-for="s in subjects" :key="s.ip" :value="s.ip" :label="s.ip" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="IP B">
          <ElSelect v-model="cmpB" filterable allow-create placeholder="选择或输入 IP">
            <ElOption v-for="s in subjects" :key="s.ip" :value="s.ip" :label="s.ip" />
          </ElSelect>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="compareVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="compareLoading" @click="onCompare">对比</ElButton>
      </template>
      <div v-if="compareResult" class="cmp-result">
        <ElDescriptions :column="1" border size="small">
          <ElDescriptionsItem label="时段相似度">{{ compareResult.block_similarity }}</ElDescriptionsItem>
          <ElDescriptionsItem label="分类相似度">{{ compareResult.category_similarity }}</ElDescriptionsItem>
          <ElDescriptionsItem label="结论">{{ compareResult.verdict }}</ElDescriptionsItem>
          <ElDescriptionsItem label="备注">{{ compareResult.note }}</ElDescriptionsItem>
        </ElDescriptions>
      </div>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import { echarts } from '@/plugins/echarts'
  import { useAuth } from '@/hooks/core/useAuth'
  import {
    getBehaviorProfiles,
    getBehaviorProfile,
    getBehaviorTrend,
    refreshBehaviorProfile,
    getBehaviorAiSummary,
    getBehaviorRisk,
    getBehaviorAnomalies,
    getBehaviorRelations,
    getBehaviorDomainDaily,
    compareBehaviorProfiles,
    exportBehaviorProfile
  } from '@/api/behaviorProfile'

  const { hasAuth } = useAuth()

  const loading = ref(false)
  const refreshing = ref(false)
  const aiLoading = ref(false)
  const aiResult = ref<any>(null)
  const trafficFilter = ref('')
  const subjects = ref<any[]>([])
  const currentIp = ref('')
  const days = ref(7)
  const activeTab = ref('behavior')
  const profile = ref<any>(null)
  const trend = ref<any[]>([])
  const risk = ref<any>(null)
  const anomalies = ref<any>(null)

  const hourRef = ref<HTMLElement>()
  const blockRef = ref<HTMLElement>()
  const heatRef = ref<HTMLElement>()
  const catRef = ref<HTMLElement>()
  const stackRef = ref<HTMLElement>()
  const trendRef = ref<HTMLElement>()
  const vulnRef = ref<HTMLElement>()
  const riskTrendRef = ref<HTMLElement>()

  const drillVisible = ref(false)
  const drillLoading = ref(false)
  const drillDomain = ref('')
  const drillData = ref<any[]>([])

  const compareVisible = ref(false)
  const compareLoading = ref(false)
  const cmpA = ref('')
  const cmpB = ref('')
  const compareResult = ref<any>(null)

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

  // 机器流量主体折叠标签、排到列表尾部（§9.7.1）
  const sortedSubjects = computed(() =>
    [...subjects.value].sort((a, b) => {
      const ma = a.traffic_type === 'machine' ? 1 : 0
      const mb = b.traffic_type === 'machine' ? 1 : 0
      return ma - mb || b.total - a.total
    })
  )

  const behaviorVisibleTags = computed(() => {
    const p = profile.value
    if (!p) return []
    return p.traffic_type === 'machine' ? (p.tags || []).filter((t: any) => t.name !== '机器流量为主') : p.tags || []
  })

  const workdayShare = computed(() => {
    const p = profile.value
    if (!p) return 0
    const t = (p.workday || 0) + (p.weekend || 0)
    return t ? Math.round(((p.workday || 0) / t) * 1000) / 10 : 0
  })
  const weekendShare = computed(() => {
    const p = profile.value
    if (!p) return 0
    const t = (p.workday || 0) + (p.weekend || 0)
    return t ? Math.round(((p.weekend || 0) / t) * 1000) / 10 : 0
  })

  const riskKpis = computed(() => {
    const r = risk.value
    if (!r) return []
    const a = r.alerts || {}
    return [
      { l: '7 天告警总数', v: formatNumber(a.total || 0), c: '#e8590c' },
      { l: 'critical / high', v: `${a.critical || 0} / ${a.high || 0}`, c: '#c92a2a' },
      { l: '未修复漏洞', v: r.vulns?.total || 0, c: '#f76707' },
      { l: '开放端口', v: r.ports?.total || 0, c: '#1971c4' }
    ]
  })

  // ── 数据加载 ──────────────────────────────

  const loadList = async () => {
    loading.value = true
    try {
      const res = await getBehaviorProfiles(
        trafficFilter.value ? { traffic_type: trafficFilter.value } : undefined
      )
      subjects.value = res?.data?.items || []
      if (!currentIp.value && !_initIp && subjects.value.length) {
        await selectSubject(subjects.value[0].ip)
      }
    } finally {
      loading.value = false
    }
  }

  const selectSubject = async (ip: string) => {
    currentIp.value = ip
    loading.value = true
    aiResult.value = null
    risk.value = null
    anomalies.value = null
    try {
      const [p, t, an] = await Promise.all([
        getBehaviorProfile(ip, { days: days.value }),
        getBehaviorTrend(ip, { days: 30 }),
        getBehaviorAnomalies(ip).catch(() => null)
      ])
      profile.value = p?.data || null
      trend.value = t?.data?.items || []
      anomalies.value = an?.data || null
      relations.value = null
      await nextTick()
      renderCharts()
    } finally {
      loading.value = false
    }
  }

  const reload = () => selectSubject(currentIp.value)

  const loadRisk = async () => {
    if (risk.value || !currentIp.value) return
    const r = await getBehaviorRisk(currentIp.value).catch(() => null)
    risk.value = r?.data || null
    await nextTick()
    renderRiskCharts()
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

  const onAiSummary = async () => {
    aiLoading.value = true
    aiResult.value = null
    try {
      const res = await getBehaviorAiSummary(currentIp.value, { days: days.value })
      aiResult.value = res?.data
      if (!aiResult.value) ElMessage.warning('AI 解读失败')
    } catch {
      ElMessage.error('AI 解读失败（稍后重试）')
    } finally {
      aiLoading.value = false
    }
  }

  const onExport = async () => {
    try {
      await exportBehaviorProfile(currentIp.value, days.value)
      ElMessage.success('报告已下载')
    } catch {
      ElMessage.error('导出失败')
    }
  }

  const openDomainDrill = async (domain: string) => {
    drillDomain.value = domain
    drillVisible.value = true
    drillLoading.value = true
    try {
      const res = await getBehaviorDomainDaily(currentIp.value, domain, { days: 30 })
      drillData.value = res?.data?.items || []
    } finally {
      drillLoading.value = false
    }
  }

  const onCompare = async () => {
    if (!cmpA.value || !cmpB.value || cmpA.value === cmpB.value) {
      ElMessage.warning('请选择两个不同的 IP')
      return
    }
    compareLoading.value = true
    try {
      const res = await compareBehaviorProfiles({ a: cmpA.value, b: cmpB.value, days: days.value })
      compareResult.value = res?.data
    } catch {
      ElMessage.error('对比失败（主体可能无快照）')
    } finally {
      compareLoading.value = false
    }
  }

  // ── 图表渲染 ──────────────────────────────

  const disposeCharts = () => {
    charts.forEach((c) => c.dispose())
    charts = []
  }

  const makeChart = (el: HTMLElement | undefined | null, option: any, retry = 5) => {
    if (!el) return
    // 容器尚未布局（v-loading/v-if 时序）时 clientWidth 为 0，echarts 会画成空白
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
    if (!profile.value) return
    const p = profile.value

    // 0: 24h 曲线
    makeChart(hourRef.value, {
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

    // 1: 时段分布饼
    const blockData = BLOCK_ORDER.map((b) => ({
      name: b,
      value: p.by_block?.[b] ?? 0,
      itemStyle: { color: BLOCK_COLORS[b] }
    }))
    makeChart(blockRef.value, {
      tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['38%', '68%'], data: blockData, label: { show: false } }]
    })

    // 2: 星期×小时热力图
    const heatData: [number, number, number][] = []
    let hMax = 1
    ;(p.wd_hour || []).forEach((row: number[], i: number) =>
      row.forEach((v, h) => {
        heatData.push([h, i, v])
        if (v > hMax) hMax = v
      })
    )
    makeChart(heatRef.value, {
      grid: { left: 44, right: 12, top: 10, bottom: 40 },
      xAxis: {
        type: 'category',
        data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')),
        axisLabel: { fontSize: 9 }
      },
      yAxis: { type: 'category', data: WD, axisLabel: { fontSize: 10 } },
      tooltip: {
        formatter: (pr: any) =>
          `${WD[pr.value[1]]} ${String(pr.value[0]).padStart(2, '0')}:00 — ${pr.value[2]} 次`
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
      series: [{ type: 'heatmap', data: heatData, label: { show: false } }]
    })

    // 3: 兴趣分类饼
    const catData = Object.entries(p.cat_share || {}).map(([k, v]) => ({ name: k, value: v }))
    makeChart(catRef.value, {
      tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10 } },
      series: [{ type: 'pie', radius: ['38%', '68%'], data: catData, label: { show: false } }]
    })

    // 4: 分类×时段堆叠（对标报告 cat_block_stack）
    const stackCats = Array.from(
      new Set(Object.values(p.cat_by_block || {}).flatMap((o: any) => Object.keys(o)))
    ).slice(0, 10)
    const catColors = ['#7048e8', '#1971c4', '#0c8599', '#e64980', '#d6336c', '#f76707', '#20c997', '#ae3ec9', '#5c7cfa', '#868e96']
    makeChart(stackRef.value, {
      grid: { left: 44, right: 12, top: 20, bottom: 44 },
      xAxis: { type: 'category', data: BLOCK_ORDER, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value' },
      tooltip: { trigger: 'axis' },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 10 } },
      series: stackCats.map((c, i) => ({
        name: c,
        type: 'bar',
        stack: 'total',
        barMaxWidth: 36,
        itemStyle: { color: catColors[i % catColors.length] },
        data: BLOCK_ORDER.map((b) => p.cat_by_block?.[b]?.[c] ?? 0)
      }))
    })

    // 5: 多日趋势（gap 日 = null 断线）
    makeChart(trendRef.value, {
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

  const renderRiskCharts = () => {
    if (!risk.value) return
    const r = risk.value
    // 漏洞饼：用 .bp-tabs 内 chart-box 第 6 个
    const vulnEl = vulnRef.value
    if (vulnEl) {
      const s = r.vulns?.severity || {}
      const colors: Record<string, string> = {
        critical: '#c92a2a',
        high: '#f76707',
        medium: '#fcc419',
        low: '#74c0fc'
      }
      makeChart(vulnEl, {
        tooltip: { trigger: 'item' },
        legend: { bottom: 0, textStyle: { fontSize: 10 } },
        series: [
          {
            type: 'pie',
            radius: ['38%', '68%'],
            data: Object.entries(s)
              .filter(([, v]) => (v as number) > 0)
              .map(([k, v]) => ({ name: k, value: v, itemStyle: { color: colors[k] } })),
            label: { show: false }
          }
        ]
      })
    }
    // 风险评分趋势：第 7 个
    const rtEl = riskTrendRef.value
    if (rtEl) {
      makeChart(rtEl, {
        grid: { left: 36, right: 12, top: 16, bottom: 24 },
        xAxis: {
          type: 'category',
          data: (r.risk_trend || []).map((i: any) => i.date?.slice(5) || ''),
          axisLabel: { fontSize: 9 }
        },
        yAxis: { type: 'value', max: 100 },
        tooltip: { trigger: 'axis' },
        series: [
          {
            type: 'line',
            data: (r.risk_trend || []).map((i: any) => i.score),
            smooth: true,
            itemStyle: { color: '#e8590c' },
            areaStyle: { opacity: 0.12 }
          }
        ]
      })
    }
  }

  const levelType = (level?: number) => {
    if (!level) return 'info'
    if (level >= 13) return 'danger'
    if (level >= 10) return 'warning'
    return 'info'
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

  watch(activeTab, (t) => {
    if (t === 'behavior' && profile.value) {
      nextTick(() => renderCharts())
    }
    if (t === 'risk') {
      loadRisk()
      nextTick(() => renderRiskCharts())
    }
    if (t === 'rel' && !relations.value && currentIp.value) {
      getBehaviorRelations(currentIp.value)
        .then((r) => (relations.value = r?.data || null))
        .catch(() => (relations.value = { note: '加载失败' }))
    }
  })

  const onResize = () => charts.forEach((c) => c.resize())

  // 入口跳转支持：从资产/告警/上网行为列表跳来时带 ?ip=xxx，自动选中
  const route = useRoute()
  const router = useRouter()
  const _ipFromQuery = (route.query.ip || route.query.agent_ip) as string | undefined
  const _initIp = _ipFromQuery || ''

  // 初次加载默认选中的 IP：query 优先；其次 subjects[0]；否则空
  onMounted(async () => {
    await loadList()
    if (_initIp) {
      // 无条件 selectSubject：未快照的 IP（API 返 404）会显示空态而不是错位到 subjects[0]
      await selectSubject(_initIp)
      // 选中后清除 query，避免用户手动切主体时仍被 query 覆盖
      router.replace({ query: {} })
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

    .bp-banner {
      margin-bottom: 12px;
      cursor: pointer;
    }

    .mt8 {
      margin-top: 8px;
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

    .kpi-card {
      .kpi-v {
        font-size: 22px;
        font-weight: 700;
      }

      .kpi-l {
        margin-top: 2px;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }

    .kev {
      margin-top: 8px;

      .kev-tag {
        margin: 2px;
      }
    }

    .ports {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;

      .port {
        padding: 3px 8px;
        font-family: ui-monospace, monospace;
        font-size: 12px;
        background: var(--el-fill-color-light);
        border-radius: 4px;

        &.danger {
          color: #c92a2a;
          background: #fff5f5;
          border: 1px solid #ffa8a8;
        }

        small {
          color: var(--el-text-color-secondary);
          margin-left: 2px;
        }
      }

      .dim {
        color: var(--el-text-color-secondary);
        font-size: 12px;
      }
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
      }
    }

    .ai-body {
      font-size: 12px;

      .ai-sec {
        margin: 6px 0;

        pre {
          margin: 4px 0 0;
          font-family: inherit;
          white-space: pre-wrap;
          word-break: break-word;
        }
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

    .cmp-result {
      margin-top: 12px;
    }

    .rel-stat {
      text-align: center;

      .kpi-v {
        font-size: 28px;
        font-weight: 700;
        color: var(--el-color-primary);
      }

      .kpi-l {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }

    .rel-accounts {
      margin-top: 10px;
      text-align: center;

      .acc-tag {
        margin: 2px;
      }
    }

    .rel-fail {
      margin-top: 8px;
      font-size: 12px;
      color: #c92a2a;
      text-align: center;
    }
  }
</style>
