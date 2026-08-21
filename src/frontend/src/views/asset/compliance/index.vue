<!--
  合规基线检查（P3/F3.3）

  双层架构的 UI 体现：
  - 判定结论（达标/不达标/无法判定）一律来自规则引擎，页面上标注「规则判定」
  - AI 只在 fail 项里出现「整改建议」，带 [依据 规则ID] 前缀，可审计
  - 达标率必须与覆盖率同屏：unknown 越多，达标率越不可信
-->
<template>
  <div class="compliance-page art-full-height">
    <!-- 概览 -->
    <ElCard shadow="never" class="summary-card">
      <div v-if="!run" class="empty-run">
        <ElEmpty description="尚无巡检记录">
          <ElButton v-if="hasAuth('check')" type="primary" :loading="checking" @click="handleRunCheck">
            立即执行巡检
          </ElButton>
        </ElEmpty>
      </div>
      <template v-else>
        <div class="summary-head">
          <div class="summary-title">
            <span class="t">合规基线</span>
            <ElTag size="small" effect="plain">{{ run.ruleset_name }}</ElTag>
            <ElTag size="small" type="info" effect="plain">规则库 v{{ run.ruleset_version }}</ElTag>
            <span class="meta">
              {{ run.rules_total }} 条规则 · 在网 {{ run.assets_in_scope }}/{{ run.assets_total }} 台 ·
              {{ formatTime(run.created_at) }} 由 {{ run.triggered_by }} 触发
            </span>
          </div>
          <div class="summary-actions">
            <ElButton v-if="hasAuth('check')" type="primary" :loading="checking" @click="handleRunCheck">
              重新巡检
            </ElButton>
            <ElButton v-if="hasAuth('interpret')" :loading="interpreting" @click="handleInterpret">
              AI 解读整改（仅不达标项）
            </ElButton>
            <ElButton text @click="rulesVisible = true">查看规则库</ElButton>
          </div>
        </div>

        <ElRow :gutter="12" class="stat-row">
          <ElCol :xs="12" :sm="8" :md="4">
            <div class="stat-box">
              <div class="stat-label">达标率</div>
              <div class="stat-value" :class="rateClass">
                {{ run.compliance_rate === null ? '—' : run.compliance_rate + '%' }}
              </div>
              <div class="stat-sub">pass /(pass+fail)</div>
            </div>
          </ElCol>
          <ElCol :xs="12" :sm="8" :md="4">
            <div class="stat-box">
              <div class="stat-label">
                数据覆盖率
                <ElTooltip content="可判定项占比。覆盖率低说明大量规则因缺数据无法判定，此时达标率参考价值有限" placement="top">
                  <ElIcon class="hint-icon"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </div>
              <div class="stat-value" :class="coverageClass">
                {{ run.coverage_rate === null ? '—' : run.coverage_rate + '%' }}
              </div>
              <div class="stat-sub">(pass+fail)/(pass+fail+unknown)</div>
            </div>
          </ElCol>
          <ElCol :xs="8" :sm="8" :md="4">
            <div class="stat-box">
              <div class="stat-label">达标项</div>
              <div class="stat-value pass">{{ run.pass_count }}</div>
              <div class="stat-sub">规则判定</div>
            </div>
          </ElCol>
          <ElCol :xs="8" :sm="12" :md="4">
            <div class="stat-box clickable" @click="quickFilter('fail')">
              <div class="stat-label">不达标</div>
              <div class="stat-value fail">{{ run.fail_count }}</div>
              <div class="stat-sub">点击查看明细</div>
            </div>
          </ElCol>
          <ElCol :xs="8" :sm="12" :md="4">
            <div class="stat-box clickable" @click="quickFilter('unknown')">
              <div class="stat-label">无法判定</div>
              <div class="stat-value unknown">{{ run.unknown_count }}</div>
              <div class="stat-sub">缺数据，需补采集</div>
            </div>
          </ElCol>
          <ElCol :xs="24" :sm="12" :md="4">
            <div class="stat-box">
              <div class="stat-label">不适用</div>
              <div class="stat-value skipped">{{ run.stats?.skipped_total ?? 0 }}</div>
              <div class="stat-sub">规则 scope 未命中</div>
            </div>
          </ElCol>
        </ElRow>

        <ElAlert
          v-if="invalidRules.length"
          type="error"
          :closable="false"
          show-icon
          class="coverage-alert"
        >
          <template #title>
            规则库中有 {{ invalidRules.length }} 条规则未能加载（{{
              invalidRules.map((r) => `${r.id}：${r.reason}`).join('；')
            }}），本次巡检未覆盖这些要求，请修正 configs/compliance_rules.yaml。
          </template>
        </ElAlert>

        <ElAlert v-if="lowCoverage" type="warning" :closable="false" show-icon class="coverage-alert">          <template #title>
            数据覆盖率仅 {{ run.coverage_rate }}%，共 {{ run.unknown_count }} 项无法判定——
            达标率 {{ run.compliance_rate }}% 只代表「有数据的部分」。建议先补齐端口扫描与 Agent 覆盖再看结论。
          </template>
        </ElAlert>

        <!-- 逐规则达标情况 -->
        <div class="rule-stats">
          <div class="rule-stats-title">逐规则判定分布</div>
          <ElTable :data="ruleRows" size="small" :max-height="320" @row-click="onRuleRowClick">
            <ElTableColumn prop="id" label="规则" width="140">
              <template #default="{ row }">
                <span class="rule-id">{{ row.id }}</span>
                <span class="rule-ver">v{{ row.version }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn prop="title" label="要求" min-width="230" show-overflow-tooltip />
            <ElTableColumn label="严重度" width="88">
              <template #default="{ row }">
                <ElTag :type="sevType(row.severity)" size="small" effect="light">
                  {{ sevLabel(row.severity) }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="达标" width="70" align="right">
              <template #default="{ row }"><span class="n pass">{{ row.pass }}</span></template>
            </ElTableColumn>
            <ElTableColumn label="不达标" width="80" align="right">
              <template #default="{ row }">
                <span class="n" :class="{ fail: row.fail > 0 }">{{ row.fail }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="无法判定" width="90" align="right">
              <template #default="{ row }">
                <span class="n" :class="{ unknown: row.unknown > 0 }">{{ row.unknown }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="不适用" width="80" align="right">
              <template #default="{ row }"><span class="n skipped">{{ row.skipped }}</span></template>
            </ElTableColumn>
            <ElTableColumn label="达标率" width="150">
              <template #default="{ row }">
                <ElProgress
                  v-if="row.rate !== null"
                  :percentage="row.rate"
                  :stroke-width="10"
                  :color="row.rate >= 90 ? '#67c23a' : row.rate >= 60 ? '#e6a23c' : '#f56c6c'"
                />
                <span v-else class="no-data">无可判定数据</span>
              </template>
            </ElTableColumn>
          </ElTable>
        </div>
      </template>
    </ElCard>

    <!-- 问题项明细 -->
    <ElCard v-if="run" shadow="never" class="findings-card">
      <div class="findings-head">
        <div class="findings-title">
          问题项明细
          <span class="sub">（判定结论由规则引擎产出，AI 仅补充整改建议）</span>
        </div>
        <div class="findings-filters">
          <ElRadioGroup v-model="filterStatus" size="small" @change="loadFindings(1)">
            <ElRadioButton value="fail">不达标 {{ run.fail_count }}</ElRadioButton>
            <ElRadioButton value="unknown">无法判定 {{ run.unknown_count }}</ElRadioButton>
          </ElRadioGroup>
          <ElSelect
            v-model="filterSeverity"
            placeholder="全部严重度"
            clearable
            size="small"
            style="width: 130px"
            @change="loadFindings(1)"
          >
            <ElOption label="严重" value="critical" />
            <ElOption label="高" value="high" />
            <ElOption label="中" value="medium" />
            <ElOption label="低" value="low" />
          </ElSelect>
          <ElSelect
            v-model="filterRuleId"
            placeholder="全部规则"
            clearable
            filterable
            size="small"
            style="width: 190px"
            @change="loadFindings(1)"
          >
            <ElOption v-for="r in ruleRows" :key="r.id" :label="`${r.id} ${r.title}`" :value="r.id" />
          </ElSelect>
        </div>
      </div>

      <ElTable v-loading="findingsLoading" :data="findings" size="small" row-key="id">
        <ElTableColumn type="expand">
          <template #default="{ row }">
            <div class="finding-detail">
              <div class="fd-line">
                <span class="fd-k">判定依据</span>
                <span class="fd-v">
                  {{ row.reason }}
                  <ElTag size="small" effect="plain" type="info" class="ml-1">规则判定</ElTag>
                </span>
              </div>
              <div class="fd-line">
                <span class="fd-k">对照基线</span>
                <span class="fd-v">{{ ruleMap[row.rule_id]?.baseline || '—' }}</span>
              </div>
              <div class="fd-line">
                <span class="fd-k">判定证据</span>
                <span class="fd-v"><code>{{ JSON.stringify(row.evidence) }}</code></span>
              </div>
              <div class="fd-line" v-if="ruleMap[row.rule_id]?.rationale">
                <span class="fd-k">规则意图</span>
                <span class="fd-v">{{ ruleMap[row.rule_id]?.rationale }}</span>
              </div>
              <div v-if="row.status === 'unknown'" class="fd-unknown">
                无法判定 ≠ 达标。请补齐所需数据（端口扫描 / Agent 部署 / 系统信息）后重新巡检。
              </div>
              <div v-else-if="row.ai_remediation" class="fd-remediation">
                <div class="fd-remediation-head">
                  <span>整改建议</span>
                  <ElTag size="small" :type="row.ai_model === 'glm' ? 'primary' : 'info'" effect="light">
                    {{ row.ai_model === 'glm' ? 'AI 生成' : '规则库预置' }}
                  </ElTag>
                  <span class="fd-ai-meta" v-if="row.ai_generated_at">{{ formatTime(row.ai_generated_at) }}</span>
                  <AiFeedback
                    v-if="row.ai_model === 'glm'"
                    target-type="compliance"
                    :target-id="row.id"
                  />
                </div>
                <pre class="fd-remediation-body">{{ row.ai_remediation }}</pre>
              </div>
              <div v-else class="fd-hint">
                <span>{{ ruleMap[row.rule_id]?.remediation_hint || '暂无整改建议' }}</span>
                <ElTag size="small" effect="plain" class="ml-1">规则库预置方向</ElTag>
                <ElButton v-if="hasAuth('interpret')" text type="primary" size="small" @click="handleInterpret">
                  生成 AI 整改建议
                </ElButton>
              </div>
            </div>
          </template>
        </ElTableColumn>
        <ElTableColumn label="资产" min-width="170">
          <template #default="{ row }">
            <ElButton text type="primary" size="small" @click="goAsset(row.asset_id)">
              {{ row.asset_name || row.asset_ip || '—' }}
            </ElButton>
            <span v-if="row.asset_name && row.asset_ip" class="asset-ip">{{ row.asset_ip }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="规则" width="130">
          <template #default="{ row }">
            <span class="rule-id">{{ row.rule_id }}</span>
            <span class="rule-ver">v{{ row.rule_version }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="rule_title" label="合规要求" min-width="200" show-overflow-tooltip />
        <ElTableColumn label="严重度" width="88">
          <template #default="{ row }">
            <ElTag :type="sevType(row.severity)" size="small" effect="light">{{ sevLabel(row.severity) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="判定" width="100">
          <template #default="{ row }">
            <ElTag :type="row.status === 'fail' ? 'danger' : 'info'" size="small">
              {{ row.status === 'fail' ? '不达标' : '无法判定' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="reason" label="判定依据" min-width="220" show-overflow-tooltip />
        <ElTableColumn label="整改建议" width="100" align="center">
          <template #default="{ row }">
            <ElTag v-if="row.ai_model === 'glm'" size="small" type="success" effect="plain">已生成</ElTag>
            <span v-else class="no-data">—</span>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="loadFindings()"
          @size-change="loadFindings(1)"
        />
      </div>
    </ElCard>

    <!-- 规则库抽屉：规则原文即审计依据 -->
    <ElDrawer v-model="rulesVisible" title="合规规则库" size="46%">
      <div class="rules-meta" v-if="ruleset">
        <ElTag size="small" effect="plain">{{ ruleset.ruleset_name }}</ElTag>
        <ElTag size="small" type="info" effect="plain">v{{ ruleset.ruleset_version }}</ElTag>
        <span class="rules-note">
          规则库以 YAML 维护于 <code>configs/compliance_rules.yaml</code>，随代码版本管理；
          判定过程不含 AI，结论可完整复现。
        </span>
      </div>
      <ElCollapse v-if="ruleset" accordion>
        <ElCollapseItem v-for="r in ruleset.rules" :key="r.id" :name="r.id">
          <template #title>
            <span class="rule-id">{{ r.id }}</span>
            <span class="rule-ver">v{{ r.version }}</span>
            <ElTag :type="sevType(r.severity)" size="small" effect="light" class="mx-1">
              {{ sevLabel(r.severity) }}
            </ElTag>
            <span>{{ r.title }}</span>
          </template>
          <div class="rule-detail">
            <p><b>对照基线：</b>{{ r.baseline || '—' }}</p>
            <p><b>规则意图：</b>{{ r.rationale || '—' }}</p>
            <p v-if="r.scope"><b>适用范围：</b><code>{{ JSON.stringify(r.scope) }}</code></p>
            <p v-if="r.requires"><b>依赖数据：</b><code>{{ r.requires.join(', ') }}</code>（缺失即判无法判定）</p>
            <p><b>判定逻辑：</b><code>{{ JSON.stringify(r.check) }}</code></p>
            <p><b>整改方向：</b>{{ r.remediation_hint || '—' }}</p>
          </div>
        </ElCollapseItem>
      </ElCollapse>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import { QuestionFilled } from '@element-plus/icons-vue'
  import {
    getLatestComplianceRun,
    runComplianceCheck,
    getComplianceFindings,
    interpretCompliance,
    getComplianceRules,
    type ComplianceRun,
    type ComplianceFinding,
    type ComplianceRule
  } from '@/api/asset'
  import { useAuth } from '@/hooks/core/useAuth'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'

  defineOptions({ name: 'AssetCompliance' })

  const { hasAuth } = useAuth()
  const router = useRouter()

  const run = ref<ComplianceRun | null>(null)
  const checking = ref(false)
  const interpreting = ref(false)

  const findings = ref<ComplianceFinding[]>([])
  const findingsLoading = ref(false)
  const filterStatus = ref<'fail' | 'unknown'>('fail')
  const filterSeverity = ref<string>('')
  const filterRuleId = ref<string>('')
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)

  const rulesVisible = ref(false)
  const ruleset = ref<{
    ruleset_version: string
    ruleset_name: string
    rules: ComplianceRule[]
    invalid_rules?: { id: string; reason: string }[]
  } | null>(null)
  const ruleMap = computed<Record<string, ComplianceRule>>(() => {
    const m: Record<string, ComplianceRule> = {}
    ;(ruleset.value?.rules || []).forEach((r) => (m[r.id] = r))
    return m
  })
  /** 加载失败的规则：合规场景下必须显式暴露，否则报告会少算规则而无人察觉 */
  const invalidRules = computed(() => ruleset.value?.invalid_rules || [])

  const SEV_LABEL: Record<string, string> = { critical: '严重', high: '高', medium: '中', low: '低' }
  const SEV_TYPE: Record<string, string> = {
    critical: 'danger',
    high: 'danger',
    medium: 'warning',
    low: 'info'
  }
  const sevLabel = (s: string) => SEV_LABEL[s] || s
  const sevType = (s: string) => (SEV_TYPE[s] || 'info') as any

  const formatTime = (t?: string | null) => (t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '—')

  const rateClass = computed(() => {
    const r = run.value?.compliance_rate
    if (r === null || r === undefined) return ''
    return r >= 90 ? 'pass' : r >= 60 ? 'warn' : 'fail'
  })
  const coverageClass = computed(() => {
    const r = run.value?.coverage_rate
    if (r === null || r === undefined) return ''
    return r >= 80 ? 'pass' : r >= 50 ? 'warn' : 'fail'
  })
  /** 覆盖率不足 80% 时必须显式提示，避免达标率被误读为全局结论 */
  const lowCoverage = computed(
    () => run.value?.coverage_rate !== null && (run.value?.coverage_rate ?? 100) < 80
  )

  /** 逐规则统计：fail 多的排前，便于直接盯问题 */
  const ruleRows = computed(() => {
    const per = run.value?.stats?.per_rule || {}
    return Object.entries(per)
      .map(([id, s]) => {
        const judged = s.pass + s.fail
        return {
          id,
          ...s,
          rate: judged > 0 ? Math.round((s.pass / judged) * 100) : null
        }
      })
      .sort((a, b) => b.fail - a.fail || (a.rate ?? 101) - (b.rate ?? 101) || a.id.localeCompare(b.id))
  })

  const loadRun = async () => {
    try {
      const res = await getLatestComplianceRun()
      run.value = res?.data?.run || null
      if (run.value) await loadFindings(1)
    } catch {
      ElMessage.error('加载巡检结果失败')
    }
  }

  const loadRules = async () => {
    try {
      const res = await getComplianceRules()
      ruleset.value = res?.data || null
    } catch {
      /* 规则库仅用于展示增强，失败不阻塞主流程 */
    }
  }

  const loadFindings = async (toPage?: number) => {
    if (!run.value) return
    if (toPage) page.value = toPage
    findingsLoading.value = true
    try {
      const res = await getComplianceFindings({
        run_id: run.value.id,
        status: filterStatus.value,
        severity: filterSeverity.value || undefined,
        rule_id: filterRuleId.value || undefined,
        page: page.value,
        page_size: pageSize.value
      })
      findings.value = res?.data?.records || []
      total.value = res?.data?.total || 0
    } catch {
      ElMessage.error('加载问题项失败')
    } finally {
      findingsLoading.value = false
    }
  }

  const handleRunCheck = async () => {
    checking.value = true
    try {
      const res = await runComplianceCheck()
      run.value = res?.data?.run || null
      const r = run.value
      ElMessage.success(
        r
          ? `巡检完成：不达标 ${r.fail_count} 项，无法判定 ${r.unknown_count} 项（达标率 ${r.compliance_rate ?? '—'}%）`
          : '巡检完成'
      )
      await loadFindings(1)
    } catch {
      ElMessage.error('巡检执行失败')
    } finally {
      checking.value = false
    }
  }

  const handleInterpret = async () => {
    interpreting.value = true
    try {
      const res = await interpretCompliance(10)
      const s = res?.data?.stats || {}
      if (!s.candidates) {
        ElMessage.info('没有待生成建议的不达标项')
      } else {
        ElMessage.success(
          `已生成 ${s.generated || 0} 条 AI 建议` +
            (s.fallback ? `，${s.fallback} 条降级为规则库预置文案` : '') +
            (s.errors ? `，${s.errors} 条失败` : '')
        )
      }
      await loadFindings()
    } catch {
      ElMessage.error('AI 解读失败')
    } finally {
      interpreting.value = false
    }
  }

  const quickFilter = (status: 'fail' | 'unknown') => {
    filterStatus.value = status
    filterSeverity.value = ''
    filterRuleId.value = ''
    loadFindings(1)
  }

  const onRuleRowClick = (row: any) => {
    filterRuleId.value = row.id
    filterStatus.value = row.fail > 0 ? 'fail' : 'unknown'
    loadFindings(1)
  }

  const goAsset = (id: string) => router.push(`/assets/detail/${id}`)

  onMounted(() => {
    loadRules()
    loadRun()
  })
</script>

<style lang="scss" scoped>
  .compliance-page {
    .summary-card,
    .findings-card {
      margin-bottom: 12px;
    }

    .empty-run {
      padding: 20px 0;
    }

    .summary-head {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;

      .summary-title {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;

        .t {
          font-size: 16px;
          font-weight: 600;
        }

        .meta {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }

      .summary-actions {
        display: flex;
        gap: 8px;
      }
    }

    .stat-row {
      margin-bottom: 10px;
    }

    .stat-box {
      padding: 10px 12px;
      margin-bottom: 8px;
      background: var(--el-fill-color-lighter);
      border-radius: 6px;

      &.clickable {
        cursor: pointer;

        &:hover {
          background: var(--el-fill-color);
        }
      }

      .stat-label {
        display: flex;
        gap: 4px;
        align-items: center;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }

      .stat-value {
        margin: 2px 0;
        font-size: 22px;
        font-weight: 600;

        &.pass {
          color: var(--el-color-success);
        }

        &.warn {
          color: var(--el-color-warning);
        }

        &.fail {
          color: var(--el-color-danger);
        }

        &.unknown {
          color: var(--el-color-info);
        }

        &.skipped {
          color: var(--el-text-color-secondary);
        }
      }

      .stat-sub {
        font-size: 11px;
        color: var(--el-text-color-placeholder);
      }
    }

    .hint-icon {
      font-size: 13px;
      color: var(--el-text-color-placeholder);
      cursor: help;
    }

    .coverage-alert {
      margin-bottom: 12px;
    }

    .rule-stats-title,
    .findings-title {
      margin-bottom: 8px;
      font-size: 14px;
      font-weight: 600;

      .sub {
        font-size: 12px;
        font-weight: 400;
        color: var(--el-text-color-secondary);
      }
    }

    .findings-head {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;

      .findings-filters {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
      }
    }

    .rule-id {
      font-family: var(--el-font-family-monospace, monospace);
      font-size: 12px;
    }

    .rule-ver {
      margin-left: 3px;
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }

    .n {
      font-variant-numeric: tabular-nums;

      &.pass {
        color: var(--el-color-success);
      }

      &.fail {
        font-weight: 600;
        color: var(--el-color-danger);
      }

      &.unknown {
        color: var(--el-color-info);
      }

      &.skipped {
        color: var(--el-text-color-placeholder);
      }
    }

    .no-data {
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }

    .asset-ip {
      margin-left: 4px;
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }

    .finding-detail {
      padding: 8px 16px 12px;

      .fd-line {
        display: flex;
        gap: 8px;
        margin-bottom: 6px;
        font-size: 13px;

        .fd-k {
          flex: 0 0 68px;
          color: var(--el-text-color-secondary);
        }

        .fd-v {
          flex: 1;
        }
      }

      .fd-unknown {
        padding: 8px 10px;
        font-size: 12px;
        color: var(--el-color-info);
        background: var(--el-color-info-light-9);
        border-radius: 4px;
      }

      .fd-hint {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        align-items: center;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }

      .fd-remediation {
        padding: 8px 10px;
        margin-top: 6px;
        background: var(--el-fill-color-lighter);
        border-left: 3px solid var(--el-color-primary);
        border-radius: 4px;

        .fd-remediation-head {
          display: flex;
          gap: 8px;
          align-items: center;
          margin-bottom: 6px;
          font-size: 13px;
          font-weight: 600;

          .fd-ai-meta {
            font-size: 11px;
            font-weight: 400;
            color: var(--el-text-color-placeholder);
          }
        }

        .fd-remediation-body {
          margin: 0;
          font-family: inherit;
          font-size: 13px;
          line-height: 1.7;
          white-space: pre-wrap;
        }
      }
    }

    .pager {
      display: flex;
      justify-content: flex-end;
      margin-top: 10px;
    }

    .rules-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      margin-bottom: 12px;

      .rules-note {
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }

    .rule-detail {
      font-size: 13px;
      line-height: 1.8;

      p {
        margin: 0 0 4px;
      }

      code {
        padding: 1px 4px;
        font-size: 12px;
        background: var(--el-fill-color-light);
        border-radius: 3px;
      }
    }
  }
</style>
