<!--
  变更影响分析（PRD P3 / F3.1）

  设计取向：这是「变更前的问答页」，不是 dashboard。
  左侧输入变更描述 + 维护窗口，右侧出报告。
  诚实降级：data_degraded / source=template 都在页面顶部显式告知，
  不把模板兜底伪装成 AI 分析结果。
-->
<template>
  <div class="impact-analysis-page">
    <!-- 页头 -->
    <ElCard shadow="never" class="header-card">
      <div class="page-header">
        <div>
          <h2 class="page-title">变更影响分析</h2>
          <p class="page-desc">
            描述你的计划变更，系统会定位受影响资产、关联资产与历史告警，给出风险点与维护窗口建议。
          </p>
        </div>
      </div>
    </ElCard>

    <ElRow :gutter="16" class="main-row">
      <!-- 左：输入区 -->
      <ElCol :xs="24" :md="9">
        <ElCard shadow="never" class="input-card">
          <template #header>
            <span class="card-title">变更描述</span>
          </template>

          <ElForm label-position="top">
            <ElFormItem>
              <template #label>
                <span>变更内容</span>
                <ElTooltip
                  content="尽量写清 IP / 主机名 / 网段，例如「升级 192.168.0.10 的内核」或「重启 k3s-master」。只写「升级交换机」这类泛描述会定位不到资产。"
                  placement="top"
                >
                  <ElIcon class="hint-icon"><QuestionFilled /></ElIcon>
                </ElTooltip>
              </template>
              <ElInput
                v-model="form.change_description"
                type="textarea"
                :rows="5"
                maxlength="2000"
                show-word-limit
                placeholder="例：升级 192.168.0.30 的 Wazuh Agent 到 4.9，需重启服务"
              />
            </ElFormItem>

            <ElFormItem label="计划维护窗口（小时）">
              <ElInputNumber v-model="form.change_window_hours" :min="1" :max="168" :step="1" />
              <span class="window-hint">1 - 168（最长 7 天）</span>
            </ElFormItem>

            <ElFormItem>
              <ElButton
                type="primary"
                :loading="loading"
                :disabled="form.change_description.trim().length < 3"
                @click="runAnalysis"
              >
                {{ loading ? '分析中（可能需 30-60 秒）' : '开始分析' }}
              </ElButton>
              <ElButton v-if="result" @click="reset">清空</ElButton>
            </ElFormItem>
          </ElForm>

          <!-- 示例快填 -->
          <ElDivider content-position="left">
            <span class="example-label">示例</span>
          </ElDivider>
          <div class="examples">
            <ElTag
              v-for="ex in examples"
              :key="ex"
              size="small"
              class="example-tag"
              @click="form.change_description = ex"
            >
              {{ ex }}
            </ElTag>
          </div>
        </ElCard>
      </ElCol>

      <!-- 右：结果区 -->
      <ElCol :xs="24" :md="15">
        <!-- 空态 -->
        <ElCard v-if="!result && !loading" shadow="never" class="empty-card">
          <ElEmpty description="填写左侧变更描述后点「开始分析」" />
        </ElCard>

        <!-- loading -->
        <ElCard v-else-if="loading" shadow="never" class="empty-card">
          <ElSkeleton :rows="8" animated />
        </ElCard>

        <!-- 结果 -->
        <template v-else-if="result">
          <!-- 降级 / 来源横幅：必须置顶，绝不把模板伪装成 AI -->
          <ElAlert
            v-if="result.data_degraded"
            type="warning"
            show-icon
            :closable="false"
            class="banner"
          >
            <template #title>数据可信度降级，结果可能不全</template>
            <div class="banner-body">
              <div v-if="result.provenance?.opensearch_ok === false">
                · OpenSearch 不可达，告警历史为空：{{
                  (result.provenance.opensearch_errors || []).join('；')
                }}
              </div>
              <div v-for="s in overdueSources" :key="s.source_key">
                · 数据源 {{ s.source_key }} 过期（{{ s.reason }}）
              </div>
            </div>
          </ElAlert>

          <ElAlert
            v-if="result.source === 'template'"
            type="info"
            show-icon
            :closable="false"
            class="banner"
            title="AI 解读未启用，以下为基于事实拼装的模板分析（未包含拓扑信息）"
          />

          <!-- 未匹配到资产 -->
          <ElAlert
            v-if="result.provenance?.target_count === 0"
            type="error"
            show-icon
            :closable="false"
            class="banner"
            title="未在描述中识别到具体资产"
          >
            <div class="banner-body">请补充 IP、主机名或子网后重试。</div>
          </ElAlert>

          <!-- 报告主体 -->
          <ElCard shadow="never" class="report-card">
            <template #header>
              <div class="report-header">
                <span class="card-title">影响评估报告</span>
                <div class="report-meta">
                  <ElTag :type="result.source === 'glm' ? 'success' : 'info'" size="small">
                    {{ result.source === 'glm' ? 'AI 解读' : '模板兜底' }}
                  </ElTag>
                  <ElTag size="small" type="info">
                    定位 {{ result.provenance?.target_count ?? 0 }} 台
                  </ElTag>
                  <ElTag size="small" type="info">窗口 {{ result.change_window_hours }}h</ElTag>
                </div>
              </div>
            </template>

            <div class="section">
              <div class="section-title">结论</div>
              <pre class="section-body">{{ result.report?.summary || '—' }}</pre>
            </div>

            <div class="section">
              <div class="section-title">影响范围</div>
              <pre class="section-body">{{ result.report?.impact || '—' }}</pre>
            </div>

            <div class="section">
              <div class="section-title">建议与维护窗口</div>
              <pre class="section-body">{{ result.report?.recommendations || '—' }}</pre>
            </div>

            <AiFeedback
              v-if="result.source === 'glm'"
              target-type="report"
              :target-id="feedbackId"
            />
          </ElCard>

          <!-- 目标资产明细 -->
          <ElCard
            v-if="(result.details || []).length"
            shadow="never"
            class="detail-card"
          >
            <template #header>
              <span class="card-title">目标资产与粗粒度关联</span>
              <ElTooltip
                content="关联仅基于同网段 + 共享标签 + 告警历史；未包含网络拓扑（拓扑建模不在本期范围）"
                placement="top"
              >
                <ElIcon class="hint-icon"><QuestionFilled /></ElIcon>
              </ElTooltip>
            </template>

            <div v-for="d in result.details" :key="d.asset.id" class="target-block">
              <!-- 资产头 -->
              <div class="target-head">
                <span class="target-name">{{ d.asset.name }}</span>
                <ElTag size="small" type="info">{{ d.asset.ip || '无 IP' }}</ElTag>
                <ElTag size="small" :type="critType(d.asset.criticality)">
                  {{ critLabel(d.asset.criticality) }}
                </ElTag>
                <ElTag size="small" type="info">{{ d.asset.exposure }}</ElTag>
                <ElTag v-if="d.asset.risk_score != null" size="small" type="warning">
                  风险分 {{ d.asset.risk_score }}
                </ElTag>
                <ElTag
                  size="small"
                  :type="d.asset.asset_status === 'online' ? 'success' : 'danger'"
                >
                  {{ d.asset.asset_status }}
                </ElTag>
              </div>

              <!-- 告警历史 -->
              <div class="target-row">
                <span class="row-label">近 7 天告警</span>
                <template v-if="hasAlerts(d.alert_history_7d)">
                  <ElTag v-if="d.alert_history_7d.critical" size="small" type="danger">
                    critical {{ d.alert_history_7d.critical }}
                  </ElTag>
                  <ElTag v-if="d.alert_history_7d.high" size="small" type="warning">
                    high {{ d.alert_history_7d.high }}
                  </ElTag>
                  <ElTag v-if="d.alert_history_7d.medium" size="small">
                    medium {{ d.alert_history_7d.medium }}
                  </ElTag>
                  <ElTag v-if="d.alert_history_7d.low" size="small" type="info">
                    low {{ d.alert_history_7d.low }}
                  </ElTag>
                </template>
                <span v-else class="muted">无告警（或 OpenSearch 不可达）</span>
              </div>

              <!-- 风险趋势 -->
              <div class="target-row">
                <span class="row-label">7 天评分趋势</span>
                <span v-if="d.risk_trend_7d?.samples >= 2">
                  {{ d.risk_trend_7d.first }} → {{ d.risk_trend_7d.last }}
                  <ElTag
                    size="small"
                    :type="d.risk_trend_7d.delta > 0 ? 'danger' : 'success'"
                  >
                    {{ d.risk_trend_7d.delta > 0 ? '+' : '' }}{{ d.risk_trend_7d.delta }}
                  </ElTag>
                </span>
                <span v-else class="muted">样本不足（{{ d.risk_trend_7d?.samples ?? 0 }} 条）</span>
              </div>

              <!-- 关联资产 -->
              <div class="target-row">
                <span class="row-label">同网段</span>
                <span v-if="(d.related?.same_segment || []).length">
                  {{ d.related.same_segment.length }} 台：
                  <span class="related-names">
                    {{ d.related.same_segment.map((a: any) => a.name).slice(0, 6).join('、') }}
                    <template v-if="d.related.same_segment.length > 6">…</template>
                  </span>
                </span>
                <span v-else class="muted">无</span>
              </div>

              <div class="target-row">
                <span class="row-label">共享标签</span>
                <span v-if="(d.related?.shared_tags || []).length">
                  {{ d.related.shared_tags.length }} 台：
                  <span class="related-names">
                    {{ d.related.shared_tags.map((a: any) => a.name).slice(0, 6).join('、') }}
                    <template v-if="d.related.shared_tags.length > 6">…</template>
                  </span>
                </span>
                <span v-else class="muted">无</span>
              </div>

              <ElDivider v-if="!isLast(d)" />
            </div>
          </ElCard>

          <!-- 识别到的关键词（可解释性） -->
          <ElCard shadow="never" class="kw-card">
            <template #header>
              <span class="card-title">识别到的关键词</span>
              <span class="kw-hint">（用于定位资产，可据此判断描述是否够明确）</span>
            </template>
            <div class="kw-row">
              <span class="row-label">IP</span>
              <template v-if="(result.keywords?.ips || []).length">
                <ElTag v-for="ip in result.keywords.ips" :key="ip" size="small">{{ ip }}</ElTag>
              </template>
              <span v-else class="muted">未识别</span>
            </div>
            <div class="kw-row">
              <span class="row-label">主机名</span>
              <template v-if="(result.keywords?.name_hints || []).length">
                <ElTag
                  v-for="n in result.keywords.name_hints"
                  :key="n"
                  size="small"
                  type="info"
                >
                  {{ n }}
                </ElTag>
              </template>
              <span v-else class="muted">未识别</span>
            </div>
            <div class="kw-row">
              <span class="row-label">网段</span>
              <template v-if="(result.keywords?.cidrs || []).length">
                <ElTag v-for="c in result.keywords.cidrs" :key="c" size="small" type="warning">
                  {{ c }}
                </ElTag>
              </template>
              <span v-else class="muted">未识别</span>
            </div>
          </ElCard>
        </template>
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
  import { computed, reactive, ref } from 'vue'
  import { ElMessage } from 'element-plus'
  import { QuestionFilled } from '@element-plus/icons-vue'
  import { analyzeChangeImpact } from '@/api/asset'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'

  defineOptions({ name: 'AssetImpactAnalysis' })

  const loading = ref(false)
  const result = ref<any>(null)

  const form = reactive({
    change_description: '',
    change_window_hours: 4
  })

  const examples = [
    '升级 192.168.0.30 的 Wazuh Agent 到 4.9',
    '重启 k3s-master 节点',
    '迁移 192.168.0.0/24 网段到新交换机',
    '下线 pve-kail-linux 主机'
  ]

  // AiFeedback 需要稳定 target_id；用生成时间戳（后端 provenance 里带）
  const feedbackId = computed(
    () => result.value?.provenance?.generated_at || 'impact-analysis'
  )

  const overdueSources = computed(() =>
    (result.value?.source_health || []).filter((s: any) => s.overdue)
  )

  const hasAlerts = (a: any) =>
    a && (a.critical || a.high || a.medium || a.low)

  const isLast = (d: any) => {
    const list = result.value?.details || []
    return list.length > 0 && list[list.length - 1]?.asset?.id === d.asset.id
  }

  const critLabel = (c: string) =>
    ({ critical: '极重要', high: '重要', medium: '一般', low: '次要' })[c] || c

  const critType = (c: string) =>
    ({ critical: 'danger', high: 'warning', medium: 'info', low: 'info' })[c] || 'info'

  const runAnalysis = async () => {
    const desc = form.change_description.trim()
    if (desc.length < 3) {
      ElMessage.warning('变更描述至少 3 个字符')
      return
    }
    loading.value = true
    result.value = null
    try {
      const resp = await analyzeChangeImpact({
        change_description: desc,
        change_window_hours: form.change_window_hours
      })
      if (resp?.code === 200) {
        result.value = resp.data
        if (resp.data?.provenance?.target_count === 0) {
          ElMessage.warning('未识别到具体资产，请补充 IP / 主机名 / 网段')
        }
      } else {
        ElMessage.error(resp?.msg || '分析失败')
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '分析请求失败')
    } finally {
      loading.value = false
    }
  }

  const reset = () => {
    result.value = null
    form.change_description = ''
    form.change_window_hours = 4
  }
</script>

<style lang="scss" scoped>
  .impact-analysis-page {
    .header-card {
      margin-bottom: 16px;
    }

    .page-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
    }

    .page-title {
      margin: 0 0 6px;
      font-size: 18px;
      font-weight: 600;
    }

    .page-desc {
      margin: 0;
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }

    .card-title {
      font-size: 15px;
      font-weight: 600;
    }

    .hint-icon {
      margin-left: 4px;
      color: var(--el-text-color-placeholder);
      cursor: help;
      vertical-align: middle;
    }

    .window-hint {
      margin-left: 10px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }

    .example-label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }

    .examples {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .example-tag {
      cursor: pointer;

      &:hover {
        opacity: 0.75;
      }
    }

    .banner {
      margin-bottom: 12px;
    }

    .banner-body {
      margin-top: 4px;
      font-size: 12px;
      line-height: 1.7;
    }

    .empty-card {
      min-height: 300px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .report-card,
    .detail-card,
    .kw-card {
      margin-bottom: 16px;
    }

    .report-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
    }

    .report-meta {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .section {
      margin-bottom: 18px;

      &:last-of-type {
        margin-bottom: 8px;
      }
    }

    .section-title {
      margin-bottom: 6px;
      font-size: 13px;
      font-weight: 600;
      color: var(--el-color-primary);
    }

    .section-body {
      margin: 0;
      padding: 10px 12px;
      font-family: inherit;
      font-size: 13px;
      line-height: 1.8;
      white-space: pre-wrap;
      word-break: break-word;
      background: var(--el-fill-color-light);
      border-radius: 4px;
    }

    .target-block {
      margin-bottom: 4px;
    }

    .target-head {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
    }

    .target-name {
      font-size: 14px;
      font-weight: 600;
      margin-right: 4px;
    }

    .target-row,
    .kw-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 6px;
      font-size: 13px;
    }

    .row-label {
      min-width: 88px;
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }

    .related-names {
      color: var(--el-text-color-regular);
    }

    .muted {
      color: var(--el-text-color-placeholder);
      font-size: 12px;
    }

    .kw-hint {
      margin-left: 6px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }
  }
</style>