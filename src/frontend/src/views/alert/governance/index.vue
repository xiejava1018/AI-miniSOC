<template>
  <div class="alert-governance-page art-full-height">
    <!-- 视图切换：实时(方案A) / 历史(方案B) -->
    <div class="view-switch">
      <ElRadioGroup v-model="viewMode" size="small" @change="onViewModeChange">
        <ElRadioButton label="realtime">实时聚合</ElRadioButton>
        <ElRadioButton label="history">历史快照</ElRadioButton>
      </ElRadioGroup>
      <span class="view-hint">
        {{ viewMode === 'realtime' ? '每次实时计算（永远新鲜）' : '每 6 小时落库快照（可追溯 / 趋势）' }}
      </span>
    </div>

    <!-- 实时聚合(方案 A) -->
    <div v-if="viewMode === 'realtime'">
    <!-- 统计卡片 -->
    <ElRow :gutter="16" class="stats-row">
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card">
          <div class="stat-value">{{ totalGroups }}</div>
          <div class="stat-label">告警簇(去重后)</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card stat-info">
          <div class="stat-value text-info">{{ rawTotal }}</div>
          <div class="stat-label">原始告警总数</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card stat-warning">
          <div class="stat-value text-warning">{{ assetCount }}</div>
          <div class="stat-label">覆盖资产数</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="hover" class="stat-card">
          <div class="stat-value">{{ filters.hours }}<span class="stat-unit">h</span></div>
          <div class="stat-label">统计时间窗</div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 摘要面板 -->
    <ElCard shadow="never" class="digest-card">
      <template #header>
        <div class="digest-header">
          <span class="digest-title">告警治理摘要</span>
          <div class="digest-actions">
            <span v-if="digest" class="digest-time">
              生成于 {{ formatTime(digest.created_at) }} ·
              <template v-if="digest.ai_model === 'template'">模板</template>
              <template v-else-if="digest.ai_model === 'heuristic'">启发式兜底</template>
              <template v-else>{{ digest.ai_model }}</template>
            </span>
            <ElButton
              type="primary"
              size="small"
              :loading="digestLoading"
              @click="generateDigest"
            >
              生成 / 刷新摘要
            </ElButton>
          </div>
        </div>
      </template>

      <ElAlert
        v-if="!digest && !digestLoading"
        type="info"
        :closable="false"
        title="尚无摘要快照"
        description="点击右上角「生成 / 刷新摘要」基于当前时间窗生成一份落库摘要（含等级分布、Top 资产、自然语言总结）。"
      />
      <template v-else>
        <div class="digest-body" v-loading="digestLoading">
          <pre class="digest-summary">{{ digest?.summary_text || '（暂无总结）' }}</pre>
          <div v-if="digest?.by_level?.length" class="digest-section">
            <div class="section-label">等级分布</div>
            <ElSpace wrap>
              <ElTag
                v-for="b in digest.by_level"
                :key="b.level"
                :type="getLevelType(b.level)"
                effect="light"
              >
                L{{ b.level }} · {{ b.count }}
              </ElTag>
            </ElSpace>
          </div>
          <div v-if="digest?.top_assets?.length" class="digest-section">
            <div class="section-label">高频资产 Top</div>
            <ElSpace wrap>
              <ElTag
                v-for="a in digest.top_assets.slice(0, 6)"
                :key="a.ip"
                effect="plain"
              >
                {{ a.asset_name || a.ip }} ({{ a.alert_count }})
              </ElTag>
            </ElSpace>
          </div>
        </div>
      </template>
    </ElCard>

    <!-- 过滤栏 -->
    <ElCard shadow="never" class="filter-card">
      <ElForm :inline="true" @submit.prevent>
        <ElFormItem label="时间窗">
          <ElSelect v-model="filters.hours" style="width: 140px" @change="onFilterChange">
            <ElOption label="最近1小时" :value="1" />
            <ElOption label="最近6小时" :value="6" />
            <ElOption label="最近24小时" :value="24" />
            <ElOption label="最近3天" :value="72" />
            <ElOption label="最近7天" :value="168" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="最低等级">
          <ElSelect
            v-model="filters.level"
            clearable
            placeholder="全部"
            style="width: 130px"
            @change="onFilterChange"
          >
            <ElOption label="≥3" :value="3" />
            <ElOption label="≥5" :value="5" />
            <ElOption label="≥8 中危" :value="8" />
            <ElOption label="≥12 高危" :value="12" />
            <ElOption label="≥15 严重" :value="15" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="簇最小条数">
          <ElInputNumber
            v-model="filters.min_count"
            :min="1"
            :max="1000"
            controls-position="right"
            style="width: 120px"
            @change="onFilterChange"
          />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="loading" @click="fetchGroups">
            查询
          </ElButton>
          <ElButton @click="resetFilter">重置</ElButton>
        </ElFormItem>
      </ElForm>
    </ElCard>

    <!-- 告警簇表格 -->
    <ElCard shadow="never" class="art-table-card">
      <template #header>
        <div class="table-header">
          <span>告警簇列表（共 {{ totalGroups }} 簇，按数量降序）</span>
          <div class="header-actions">
            <ElButton text size="small" type="primary" :loading="triageLoading" @click="loadTriageTop">
              加载 AI 研判
            </ElButton>
            <span class="total-info">原始告警合计 {{ rawTotal }}</span>
          </div>
        </div>
      </template>
      <ElTable
        :data="groups"
        v-loading="loading"
        stripe
        border
        :default-sort="{ prop: 'count', order: 'descending' }"
        @row-dblclick="(row: any) => showDetail(row)"
      >
        <ElTableColumn type="index" label="#" width="55" align="center" />
        <ElTableColumn prop="rule_description" label="规则描述" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="rule-cell">
              <span>{{ row.rule_description || '规则 ' + row.rule_id }}</span>
              <ElTag size="small" effect="plain" class="rule-id">R{{ row.rule_id }}</ElTag>
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="agent_name" label="资产" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.agent_name || row.agent_id || '未知' }}</span>
            <div class="cell-sub" v-if="row.agent_ip">{{ row.agent_ip }}</div>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="count" label="数量" width="100" align="center" sortable>
          <template #default="{ row }">
            <span class="count-badge">{{ row.count }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="等级" width="110" align="center">
          <template #default="{ row }">
            <ElTag :type="getLevelType(row.level_max)" effect="light">
              {{ row.level_min }}-{{ row.level_max }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="源IP(top)" width="100" align="center">
          <template #default="{ row }">
            {{ row.top_srcips ? row.top_srcips.length : '—' }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="first_seen" label="首次出现" width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ formatTime(row.first_seen) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="last_seen" label="最近出现" width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ formatTime(row.last_seen) }}</template>
        </ElTableColumn>
        <ElTableColumn label="关联资产" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <ElTag v-if="row.sample?.agent" type="success" effect="plain" size="small">
              {{ row.agent_name || row.agent_id }}
            </ElTag>
            <span v-else class="cell-sub">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="AI 研判" min-width="120" align="center">
          <template #default="{ row }">
            <template v-if="triageMap[row.fingerprint]">
              <ElTag :type="priorityType(triageMap[row.fingerprint].priority)" effect="dark" size="small">
                {{ triageMap[row.fingerprint].priority }}
              </ElTag>
              <ElTag v-if="triageMap[row.fingerprint].is_noise" type="info" size="small" effect="plain">
                噪声
              </ElTag>
            </template>
            <span v-else class="cell-sub">—</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <ElButton type="primary" link @click="showDetail(row)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>
    </ElCard>
    </div>

    <!-- 历史快照(方案 B) -->
    <div v-if="viewMode === 'history'">
      <!-- 历史过滤 -->
      <ElCard shadow="never" class="filter-card">
        <ElForm :inline="true" @submit.prevent>
          <ElFormItem label="快照日期">
            <ElDatePicker
              v-model="historyFilters.date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期(缺省最新)"
              style="width: 180px"
              @change="fetchHistory"
            />
          </ElFormItem>
          <ElFormItem label="资产 IP">
            <ElInput
              v-model="historyFilters.asset_ip"
              clearable
              placeholder="按资产 IP 过滤"
              style="width: 160px"
              @keyup.enter="fetchHistory"
            />
          </ElFormItem>
          <ElFormItem label="最低等级">
            <ElSelect
              v-model="historyFilters.level"
              clearable
              placeholder="全部"
              style="width: 130px"
              @change="fetchHistory"
            >
              <ElOption label="≥3" :value="3" />
              <ElOption label="≥5" :value="5" />
              <ElOption label="≥8 中危" :value="8" />
              <ElOption label="≥12 高危" :value="12" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem>
            <ElButton type="primary" :loading="historyLoading" @click="fetchHistory">查询</ElButton>
            <ElButton @click="resetHistoryFilter">重置</ElButton>
          </ElFormItem>
        </ElForm>
      </ElCard>

      <!-- 趋势图 -->
      <ElCard shadow="never" class="trend-card">
        <template #header>
          <div class="table-header">
            <span>告警簇趋势（最近 {{ trendDays }} 天，按快照日聚合）</span>
            <ElButton text size="small" :loading="trendLoading" @click="loadTrend">刷新</ElButton>
          </div>
        </template>
        <div ref="trendChartRef" class="trend-chart" v-loading="trendLoading"></div>
        <ElEmpty v-if="!trendLoading && trendData.length === 0" description="暂无快照数据，请等待每 6 小时调度或手动触发快照" />
      </ElCard>

      <!-- 历史簇表格 -->
      <ElCard shadow="never" class="art-table-card">
        <template #header>
          <div class="table-header">
            <span>历史告警簇（{{ historyGroups.length }} 条快照）</span>
            <span class="total-info">快照时间 {{ historySnapshotAt || '—' }}</span>
          </div>
        </template>
        <ElTable
          :data="historyGroups"
          v-loading="historyLoading"
          stripe
          border
          @row-dblclick="(row: any) => showDetail(row)"
        >
          <ElTableColumn type="index" label="#" width="55" align="center" />
          <ElTableColumn prop="rule_description" label="规则描述" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.rule_description || ('规则 ' + row.rule_id) }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="agent_name" label="资产" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.agent_name || row.agent_id || '未知' }}</span>
              <div class="cell-sub" v-if="row.agent_ip">{{ row.agent_ip }}</div>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="count" label="数量" width="100" align="center" sortable>
            <template #default="{ row }">
              <span class="count-badge">{{ row.count }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="等级" width="100" align="center">
            <template #default="{ row }">
              <ElTag :type="getLevelType(row.level_max)" effect="light">
                {{ row.level_min }}-{{ row.level_max }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="snapshot_at" label="快照时间" width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ formatTime(row.snapshot_at) }}</template>
          </ElTableColumn>
          <ElTableColumn label="关联资产" min-width="110" show-overflow-tooltip>
            <template #default="{ row }">
              <ElTag v-if="row.linked_asset_id" type="success" effect="plain" size="small">已关联</ElTag>
              <span v-else class="cell-sub">—</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="AI 研判" width="110" align="center">
            <template #default="{ row }">
              <template v-if="row.ai_priority">
                <ElTag :type="priorityType(row.ai_priority)" effect="dark" size="small">
                  {{ row.ai_priority }}
                </ElTag>
                <ElTag v-if="row.ai_is_noise" type="info" size="small" effect="plain">噪声</ElTag>
              </template>
              <span v-else class="cell-sub">—</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <ElButton type="primary" link @click="showDetail(row)">详情</ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>
    </div>

    <!-- 单簇明细抽屉 -->
    <ElDrawer
      v-model="drawerVisible"
      :title="detail?.rule_description || ('簇 ' + detail?.fingerprint)"
      size="620px"
      destroy-on-close
    >
      <div v-loading="detailLoading">
        <template v-if="detail">
          <ElDescriptions :column="2" border class="detail-desc">
            <ElDescriptionsItem label="指纹">{{ detail.fingerprint }}</ElDescriptionsItem>
            <ElDescriptionsItem label="数量">
              <span class="count-badge">{{ detail.count }}</span>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="资产">{{ detail.agent_name || detail.agent_id }}</ElDescriptionsItem>
            <ElDescriptionsItem label="Agent IP">{{ detail.agent_ip || '—' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="等级范围">
              <ElTag :type="getLevelType(detail.level_max)" effect="light">
                {{ detail.level_min }}-{{ detail.level_max }}
              </ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="不同源IP">
              <ElTag type="danger" effect="light">{{ detail.distinct_srcips }}</ElTag>
            </ElDescriptionsItem>
            <ElDescriptionsItem label="首次出现" :span="2">{{ formatTime(detail.first_seen) }}</ElDescriptionsItem>
            <ElDescriptionsItem label="最近出现" :span="2">{{ formatTime(detail.last_seen) }}</ElDescriptionsItem>
          </ElDescriptions>

          <!-- 关联资产 -->
          <div v-if="detail.linked_asset" class="detail-block">
            <div class="block-title">关联资产（按 IP 匹配）</div>
            <ElDescriptions :column="1" border size="small">
              <ElDescriptionsItem label="资产名">{{ detail.linked_asset.name || '—' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="IP">{{ detail.linked_asset.asset_ip || '—' }}</ElDescriptionsItem>
              <ElDescriptionsItem label="重要度">
                <ElTag :type="criticalityType(detail.linked_asset.criticality)" effect="light">
                  {{ criticalityText(detail.linked_asset.criticality) }}
                </ElTag>
              </ElDescriptionsItem>
            </ElDescriptions>
          </div>

          <!-- AI 研判（Phase 1） -->
          <div class="detail-block">
            <div class="block-title">
              AI 研判
              <ElButton
                text
                size="small"
                type="primary"
                :loading="triageVerdictLoading"
                @click="reTriage(false)"
              >
                重新研判
              </ElButton>
            </div>
            <div v-loading="triageVerdictLoading">
              <ElDescriptions v-if="triageVerdict" :column="2" border size="small">
                <ElDescriptionsItem label="优先级">
                  <ElTag :type="priorityType(triageVerdict.priority)" effect="dark" size="small">
                    {{ triageVerdict.priority }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="置信度">
                  {{ ((triageVerdict.confidence || 0) * 100).toFixed(0) }}%
                </ElDescriptionsItem>
                <ElDescriptionsItem label="是否噪声">
                  <ElTag :type="triageVerdict.is_noise ? 'info' : 'success'" effect="plain" size="small">
                    {{ triageVerdict.is_noise ? '是（良性）' : '否' }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="建议建事件">
                  <ElTag :type="triageVerdict.suggest_incident ? 'danger' : 'info'" effect="plain" size="small">
                    {{ triageVerdict.suggest_incident ? '建议' : '否' }}
                  </ElTag>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="来源" :span="2">
                  {{ triageVerdict.source }}
                  <template v-if="triageVerdict.model_name && triageVerdict.model_name !== 'heuristic'">
                    / {{ triageVerdict.model_name }}
                  </template>
                </ElDescriptionsItem>
                <ElDescriptionsItem label="研判理由" :span="2">
                  {{ triageVerdict.rationale || '—' }}
                </ElDescriptionsItem>
                <ElDescriptionsItem label="处置建议" :span="2">
                  <pre class="full-log">{{ triageVerdict.recommended_action || '—' }}</pre>
                </ElDescriptionsItem>
              </ElDescriptions>
              <ElEmpty v-else description="该簇尚无 AI 研判，点击「重新研判」生成" />
            </div>
          </div>

          <!-- 攻击者源 IP -->
          <div v-if="detail.top_srcips?.length" class="detail-block">
            <div class="block-title">攻击源 IP Top（共 {{ detail.distinct_srcips }} 个不同）</div>
            <ElSpace wrap>
              <ElTag
                v-for="ip in detail.top_srcips"
                :key="ip"
                type="info"
                effect="plain"
                size="small"
              >{{ ip }}</ElTag>
            </ElSpace>
          </div>

          <!-- 样本告警 -->
          <div class="detail-block">
            <div class="block-title">样本告警（最新 {{ detail.samples.length }} 条）</div>
            <ElCollapse>
              <ElCollapseItem
                v-for="(s, i) in detail.samples"
                :key="s.id || i"
                :name="i"
              >
                <template #title>
                  <span class="sample-title">
                    <ElTag :type="getLevelType(s.rule?.level)" effect="light" size="small">
                      L{{ s.rule?.level }}
                    </ElTag>
                    {{ s.rule?.description || ('规则 ' + s.rule?.id) }}
                    <span class="cell-sub">{{ formatTime(s.timestamp) }}</span>
                  </span>
                </template>
                <pre class="full-log">{{ s.full_log || '（无日志内容）' }}</pre>
              </ElCollapseItem>
            </ElCollapse>
          </div>
        </template>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
  import * as echarts from 'echarts'
  import {
    getAlertGroups,
    getAlertGroupDetail,
    getAlertDigest,
    generateAlertDigest,
    getAlertGroupHistory,
    getAlertGroupTrend,
    getAlertTriageTop,
    triageAlertGroup,
    getAlertGroupTriage,
    type AlertGroup,
    type AlertGroupDetail,
    type AlertDigest,
    type AlertGroupHistory,
    type AlertGroupTrendPoint,
    type AlertGroupTriage
  } from '@/api/alert'
  import { ElMessage } from 'element-plus'

  defineOptions({ name: 'AlertGovernancePage' })

  // ── 视图模式：实时(方案A) / 历史(方案B) ─────────────
  const viewMode = ref<'realtime' | 'history'>('realtime')

  // ── 状态（实时） ────────────────────────────────────
  const loading = ref(false)
  const groups = ref<AlertGroup[]>([])
  const totalGroups = ref(0)
  const digest = ref<AlertDigest | null>(null)
  const digestLoading = ref(false)
  const drawerVisible = ref(false)
  const detail = ref<AlertGroupDetail | null>(null)
  const detailLoading = ref(false)

  // ── AI 研判（Phase 1） ─────────────────────────────
  const triageMap = ref<Record<string, AlertGroupTriage>>({})
  const triageLoading = ref(false)
  const triageVerdict = ref<AlertGroupTriage | null>(null)
  const triageVerdictLoading = ref(false)

  const filters = reactive({
    hours: 24,
    level: null as number | null,
    min_count: 1,
    limit: 100
  })

  // ── 状态（历史） ────────────────────────────────────
  const historyLoading = ref(false)
  const historyGroups = ref<AlertGroupHistory[]>([])
  const historySnapshotAt = ref('')
  const historyFilters = reactive({
    date: '' as string,
    asset_ip: '' as string,
    level: null as number | null
  })
  const trendDays = ref(14)
  const trendLoading = ref(false)
  const trendData = ref<AlertGroupTrendPoint[]>([])
  const trendChartRef = ref<HTMLDivElement | null>(null)
  let trendChart: echarts.ECharts | null = null

  // ── 统计派生 ────────────────────────────────────────
  const rawTotal = computed(() =>
    digest.value?.total_alerts ??
    groups.value.reduce((s, g) => s + (g.count || 0), 0)
  )
  const assetCount = computed(
    () => new Set(groups.value.map((g) => g.agent_id).filter(Boolean)).size
  )

  // ── 数据加载 ────────────────────────────────────────
  const fetchGroups = async () => {
    loading.value = true
    try {
      const res: any = await getAlertGroups({ ...filters })
      const data = res?.data || res
      groups.value = data?.groups || []
      totalGroups.value = data?.total_groups ?? groups.value.length
    } catch (e: any) {
      ElMessage.error(e?.message || '加载告警簇失败')
    } finally {
      loading.value = false
    }
  }

  const fetchDigest = async () => {
    digestLoading.value = true
    try {
      const res: any = await getAlertDigest({})
      digest.value = res?.data || res
    } catch {
      digest.value = null
    } finally {
      digestLoading.value = false
    }
  }

  const generateDigest = async () => {
    digestLoading.value = true
    try {
      const res: any = await generateAlertDigest(filters.hours)
      digest.value = res?.data || res
      ElMessage.success('摘要已生成并落库')
    } catch (e: any) {
      ElMessage.error(e?.message || '生成摘要失败')
    } finally {
      digestLoading.value = false
    }
  }

  const showDetail = async (row: AlertGroup) => {
    drawerVisible.value = true
    detailLoading.value = true
    detail.value = null
    triageVerdict.value = null
    try {
      const res: any = await getAlertGroupDetail(row.fingerprint, {
        hours: filters.hours,
        sample_size: 5
      })
      detail.value = res?.data || res
      // 取该簇缓存的 AI verdict（无则 404，忽略）
      try {
        const r2: any = await getAlertGroupTriage(row.fingerprint)
        triageVerdict.value = r2?.data || r2
      } catch {
        triageVerdict.value = null
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '加载簇明细失败')
    } finally {
      detailLoading.value = false
    }
  }

  // ── AI 研判加载 ────────────────────────────────────
  const loadTriageTop = async () => {
    triageLoading.value = true
    try {
      const res: any = await getAlertTriageTop({ hours: filters.hours, top_n: 0 })
      const data = res?.data || res
      const m: Record<string, AlertGroupTriage> = {}
      ;(Array.isArray(data) ? data : []).forEach((g: any) => {
        if (g?.fingerprint) m[g.fingerprint] = g as AlertGroupTriage
      })
      triageMap.value = m
      ElMessage.success('AI 研判已加载')
    } catch (e: any) {
      ElMessage.error(e?.message || '加载 AI 研判失败')
    } finally {
      triageLoading.value = false
    }
  }

  const reTriage = async (force: boolean) => {
    if (!detail.value) return
    triageVerdictLoading.value = true
    try {
      const res: any = await triageAlertGroup(detail.value.fingerprint, {
        hours: filters.hours,
        force_refresh: force
      })
      triageVerdict.value = res?.data || res
      if (detail.value.fingerprint) {
        triageMap.value = { ...triageMap.value, [detail.value.fingerprint]: triageVerdict.value as AlertGroupTriage }
      }
      ElMessage.success('研判完成')
    } catch (e: any) {
      ElMessage.error(e?.message || '研判失败')
    } finally {
      triageVerdictLoading.value = false
    }
  }

  // ── 过滤交互 ────────────────────────────────────────
  const onFilterChange = () => {
    fetchGroups()
  }
  const resetFilter = () => {
    filters.hours = 24
    filters.level = null
    filters.min_count = 1
    filters.limit = 100
    fetchGroups()
  }

  // ── 历史(方案 B) ────────────────────────────────────
  const onViewModeChange = () => {
    if (viewMode.value === 'history') {
      fetchHistory()
      loadTrend()
    }
  }

  const fetchHistory = async () => {
    historyLoading.value = true
    try {
      const params: Record<string, any> = {}
      if (historyFilters.date) params.date = historyFilters.date
      if (historyFilters.asset_ip) params.asset_ip = historyFilters.asset_ip
      if (historyFilters.level != null) params.level = historyFilters.level
      const res: any = await getAlertGroupHistory(params)
      const data = res?.data || res
      historyGroups.value = Array.isArray(data) ? data : []
      historySnapshotAt.value = historyGroups.value[0]?.snapshot_at || ''
    } catch (e: any) {
      ElMessage.error(e?.message || '加载历史告警簇失败')
    } finally {
      historyLoading.value = false
    }
  }

  const resetHistoryFilter = () => {
    historyFilters.date = ''
    historyFilters.asset_ip = ''
    historyFilters.level = null
    fetchHistory()
  }

  const renderTrend = () => {
    if (!trendChartRef.value) return
    if (!trendChart) {
      trendChart = echarts.init(trendChartRef.value)
    }
    const days = trendData.value
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['告警簇数', '原始告警数', '关联资产数'] },
      grid: { left: 56, right: 24, top: 48, bottom: 40 },
      xAxis: { type: 'category', data: days.map((d) => d.date) },
      yAxis: { type: 'value' },
      series: [
        { name: '告警簇数', type: 'bar', data: days.map((d) => d.clusters), itemStyle: { color: '#409eff' } },
        { name: '原始告警数', type: 'line', smooth: true, data: days.map((d) => d.alerts), itemStyle: { color: '#e6a23c' } },
        { name: '关联资产数', type: 'line', smooth: true, data: days.map((d) => d.linked_assets), itemStyle: { color: '#67c23a' } }
      ]
    })
    trendChart.resize()
  }

  const loadTrend = async () => {
    trendLoading.value = true
    try {
      const res: any = await getAlertGroupTrend({ days: trendDays.value })
      const data = res?.data || res
      trendData.value = data?.days || []
      await nextTick()
      renderTrend()
    } catch (e: any) {
      ElMessage.error(e?.message || '加载趋势失败')
    } finally {
      trendLoading.value = false
    }
  }

  // ── 工具函数 ────────────────────────────────────────
  const formatTime = (ts?: string | null) => {
    if (!ts) return '--'
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { hour12: false })
  }

  const getLevelType = (
    level?: number | null
  ): 'danger' | 'warning' | 'info' | 'primary' => {
    if (level == null) return 'primary'
    if (level >= 12) return 'danger'
    if (level >= 8) return 'warning'
    return 'info'
  }

  const priorityType = (
    p?: string
  ): 'danger' | 'warning' | 'primary' | 'info' => {
    if (!p) return 'info'
    if (p === 'P0' || p === 'P1') return 'danger'
    if (p === 'P2') return 'warning'
    if (p === 'P3') return 'info'
    return 'primary'
  }

  const criticalityType = (c?: string): 'danger' | 'warning' | 'info' | 'success' => {
    if (c === 'critical' || c === 'high') return 'danger'
    if (c === 'medium') return 'warning'
    if (c === 'low') return 'info'
    return 'success'
  }
  const criticalityText = (c?: string) => {
    const map: Record<string, string> = {
      critical: '极高',
      high: '高',
      medium: '中',
      low: '低',
      normal: '普通',
      none: '无'
    }
    return (c && map[c]) || c || '未知'
  }

  const onResize = () => {
    trendChart?.resize()
  }

  onMounted(() => {
    fetchGroups()
    fetchDigest()
    window.addEventListener('resize', onResize)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    trendChart?.dispose()
    trendChart = null
  })
</script>

<style lang="scss" scoped>
  .alert-governance-page {
    .view-switch {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
      .view-hint {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
    .stats-row {
      margin-bottom: 16px;
    }
    .stat-card {
      text-align: center;
      .stat-value {
        font-size: 28px;
        font-weight: 700;
      }
      .stat-unit {
        font-size: 16px;
        margin-left: 2px;
      }
      .stat-label {
        margin-top: 4px;
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
    }
    .stat-info .stat-value {
      color: var(--el-color-info);
    }
    .stat-warning .stat-value {
      color: var(--el-color-warning);
    }

    .digest-card {
      margin-bottom: 16px;
      .digest-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .digest-title {
        font-weight: 600;
      }
      .digest-time {
        font-size: 12px;
        color: var(--el-text-color-secondary);
        margin-right: 12px;
      }
      .digest-summary {
        margin: 0 0 12px;
        padding: 12px;
        background: var(--el-fill-color-light);
        border-radius: 6px;
        font-size: 13px;
        line-height: 1.7;
        white-space: pre-wrap;
        word-break: break-all;
      }
      .digest-section {
        margin-top: 10px;
      }
      .section-label {
        font-size: 13px;
        color: var(--el-text-color-secondary);
        margin-bottom: 6px;
      }
    }

    .filter-card {
      margin-bottom: 16px;
    }

    .trend-card {
      margin-bottom: 16px;
      .trend-chart {
        width: 100%;
        height: 300px;
      }
    }

    .table-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 600;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .total-info {
      font-size: 13px;
      color: var(--el-text-color-secondary);
      font-weight: 400;
    }

    .rule-cell {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .rule-id {
      flex-shrink: 0;
    }
    .cell-sub {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
    .count-badge {
      font-weight: 700;
      color: var(--el-color-primary);
    }

    .detail-desc {
      margin-bottom: 16px;
    }
    .detail-block {
      margin-top: 16px;
    }
    .block-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: var(--el-text-color-primary);
    }
    .sample-title {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .full-log {
      max-height: 240px;
      overflow-y: auto;
      margin: 0;
      padding: 8px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      font-size: 12px;
      white-space: pre-wrap;
      word-break: break-all;
    }
  }
</style>
