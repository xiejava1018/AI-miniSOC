<!--
  OH-UI.11 定级备案稽核视图（S4 Phase 0 辅助定级）

  消费 OH-4.12 GET /business-systems/rating-audit + /{id}/rating-gap。
  设计（红线：系统只建议不裁决，本视图全程只读）：
  - 顶部 KPI：总数 / 未定级 / 待确认 / 已确认 / 建议覆盖率（S4 KPI ≥80%）
  - 发现列表：四类稽核发现（unrated/pending/divergence/member_exceeds）
  - 点击行 → 右侧抽屉单系统差距分析（确认 vs 建议 vs 成员分布 + 建议依据）
-->
<template>
  <div class="ra-page art-full-height">
    <ElCard shadow="never">
      <template #header>
        <div class="card-head">
          <span class="t">定级备案稽核</span>
          <ElTag size="small" type="warning" effect="plain">
            待处理发现 {{ audit?.finding_count ?? '—' }}
          </ElTag>
          <span class="meta">
            辅助定级与差距分析——系统只建议不裁决，等级变更须人工确认
          </span>
          <ElButton :icon="Refresh" circle size="small" @click="loadAudit" />
        </div>
      </template>

      <!-- KPI -->
      <div v-loading="loading" class="kpis">
        <div class="kpi">
          <div class="kpi-num">{{ audit?.total_systems ?? '—' }}</div>
          <div class="kpi-label">业务系统</div>
        </div>
        <div class="kpi kpi--danger">
          <div class="kpi-num">{{ audit?.distribution?.unrated ?? '—' }}</div>
          <div class="kpi-label">未定级</div>
        </div>
        <div class="kpi kpi--warning">
          <div class="kpi-num">{{ audit?.distribution?.suggested ?? '—' }}</div>
          <div class="kpi-label">待确认建议</div>
        </div>
        <div class="kpi kpi--success">
          <div class="kpi-num">{{ audit?.distribution?.confirmed ?? '—' }}</div>
          <div class="kpi-label">已确认</div>
        </div>
        <div class="kpi">
          <div class="kpi-num">
            {{ audit?.suggestion_coverage != null ? audit.suggestion_coverage + '%' : '—' }}
          </div>
          <div class="kpi-label">建议覆盖率（目标 ≥80%）</div>
        </div>
      </div>

      <!-- 发现列表 -->
      <div class="findings">
        <div class="block-title">稽核发现</div>
        <ElTable
          v-loading="loading"
          :data="filteredFindings"
          stripe
          row-key="system_id"
          @row-click="openGap"
        >
          <ElTableColumn label="业务系统" min-width="160">
            <template #default="{ row }">
              <span class="sys-name">{{ row.system_name }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="定级状态" width="100" align="center">
            <template #default="{ row }">
              <ElTag :type="statusTag(row.rating_status)" size="small">
                {{ statusLabel(row.rating_status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="发现类型" width="150" align="center">
            <template #default="{ row }">
              <ElTag :type="kindTag(row.kind)" size="small" effect="plain">
                {{ kindLabel(row.kind) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="说明" min-width="320">
            <template #default="{ row }">
              <span class="msg">{{ row.message }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" width="80" fixed="right">
            <template #default>
              <ElButton text type="primary" size="small">差距分析</ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
        <ElEmpty
          v-if="!loading && !filteredFindings.length"
          description="无稽核发现——定级状态健康"
        />
      </div>
    </ElCard>

    <!-- 差距分析抽屉 -->
    <ElDrawer v-model="gapVisible" title="定级差距分析" size="560px">
      <div v-if="gap" v-loading="gapLoading" class="gap-body">
        <div class="block">
          <ElDescriptions :column="2" border size="small">
            <ElDescriptionsItem label="系统" :span="2">
              {{ gap.system.name }}（{{ gap.system.code }}）
            </ElDescriptionsItem>
            <ElDescriptionsItem label="已确认等级">
              <LevelTag :level="gap.system.confirmed_level || undefined" />
            </ElDescriptionsItem>
            <ElDescriptionsItem label="建议等级">
              <LevelTag :level="gap.system.suggested_level || undefined" />
            </ElDescriptionsItem>
            <ElDescriptionsItem label="定级状态">
              {{ statusLabel(gap.system.rating_status) }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="确认人">
              {{ gap.system.confirmed_by || '—' }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <div class="block">
          <div class="block-title">差距结论</div>
          <ElAlert :closable="false" :type="gapAlertType" show-icon>
            <template #title>{{ gapLabel(gap.gap) }}</template>
            <div v-if="gap.consistency === 'member_exceeds_system'">
              一致性告警：最高成员资产等级（{{ gap.member_summary.highest_member?.protection_level || '—' }}）
              高于系统等级
            </div>
          </ElAlert>
        </div>

        <div class="block">
          <div class="block-title">
            成员资产（{{ gap.member_summary.count }}）
          </div>
          <ElDescriptions :column="3" border size="small">
            <ElDescriptionsItem label="继承系统">
              {{ gap.member_summary.level_sources.inherited }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="人工裁定">
              {{ gap.member_summary.level_sources.manual }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="最高成员">
              {{ gap.member_summary.highest_member?.name || '—' }}
              （{{ gap.member_summary.highest_member?.protection_level || '—' }}）
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <div v-if="gap.system.suggestion_basis" class="block">
          <div class="block-title">建议依据（可解释）</div>
          <ElInput
            :model-value="JSON.stringify(gap.system.suggestion_basis, null, 2)"
            type="textarea"
            :rows="10"
            readonly
          />
        </div>

        <ElAlert :closable="false" type="info" show-icon>
          <template #title>{{ gap.red_line }}</template>
        </ElAlert>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref, defineComponent, h } from 'vue'
  import { ElMessage } from 'element-plus'
  import { Refresh } from '@element-plus/icons-vue'
  import {
    getRatingAudit,
    getRatingGap,
    type RatingAuditResult,
    type RatingFinding,
    type RatingGapResult
  } from '@/api/businessSystem'

  defineOptions({ name: 'RatingAuditView' })

  // 等级小标签（内联组件避免单文件膨胀）
  const LevelTag = defineComponent({
    props: { level: { type: String, default: null } },
    setup(props: { level: string | null }) {
      return () =>
        h('span', { class: 'level-tag' }, props.level || '未定级')
    }
  })

  const audit = ref<RatingAuditResult | null>(null)
  const loading = ref(false)
  const kindFilter = ref<string>('')

  const gapVisible = ref(false)
  const gapLoading = ref(false)
  const gap = ref<RatingGapResult | null>(null)

  const filteredFindings = computed<RatingFinding[]>(() =>
    kindFilter.value
      ? (audit.value?.findings || []).filter((f) => f.kind === kindFilter.value)
      : audit.value?.findings || []
  )

  const STATUS_LABELS: Record<string, string> = {
    unrated: '未定级',
    suggested: '待确认',
    confirmed: '已确认'
  }
  const KIND_LABELS: Record<string, string> = {
    unrated: '未定级',
    pending: '建议待确认',
    divergence: '确认低于建议',
    member_exceeds_system: '成员超系统等级'
  }
  const GAP_LABELS: Record<string, string> = {
    confirmed_below_suggested: '已确认等级低于建议——请人工复核是否偏低（建议引擎可能偏保守）',
    confirmed_above_suggested: '已确认等级高于建议——从严定级，无需处理',
    aligned: '确认等级与建议一致'
  }

  const statusLabel = (s: string) => STATUS_LABELS[s] || s
  const kindLabel = (k: string) => KIND_LABELS[k] || k
  const gapLabel = (g: string | null) =>
    g ? GAP_LABELS[g] || g : '暂无建议等级（未跑建议引擎）'
  const gapAlertType = computed(() =>
    gap.value?.gap === 'confirmed_below_suggested' ||
      gap.value?.consistency === 'member_exceeds_system'
      ? 'warning'
      : 'success'
  )

  const statusTag = (s: string): 'success' | 'warning' | 'info' =>
    s === 'confirmed' ? 'success' : s === 'suggested' ? 'warning' : 'info'
  const kindTag = (k: string): 'danger' | 'warning' | 'info' => {
    if (k === 'divergence' || k === 'member_exceeds_system') return 'danger'
    if (k === 'pending') return 'warning'
    return 'info'
  }

  const loadAudit = async () => {
    loading.value = true
    try {
      const res: any = await getRatingAudit()
      audit.value = res?.data || res || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载定级稽核失败')
    } finally {
      loading.value = false
    }
  }

  const openGap = async (row: RatingFinding) => {
    gapVisible.value = true
    gapLoading.value = true
    gap.value = null
    try {
      const res: any = await getRatingGap(row.system_id)
      gap.value = res?.data || res || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载差距分析失败')
      gapVisible.value = false
    } finally {
      gapLoading.value = false
    }
  }

  loadAudit()
</script>

<style lang="scss" scoped>
  .ra-page {
    height: auto;
    min-height: var(--art-full-height);

    .card-head {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;

      .t {
        font-size: 16px;
        font-weight: 600;
      }

      .meta {
        font-size: 12px;
        color: var(--art-text-gray-600);
      }
    }

    .kpis {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-bottom: 20px;

      .kpi {
        min-width: 130px;
        padding: 12px 16px;
        text-align: center;
        border: 1px solid var(--art-border-color);
        border-radius: 8px;

        .kpi-num {
          font-size: 22px;
          font-weight: 700;
        }

        .kpi-label {
          margin-top: 2px;
          font-size: 12px;
          color: var(--art-text-gray-500);
        }

        &.kpi--danger .kpi-num {
          color: var(--el-color-danger);
        }

        &.kpi--warning .kpi-num {
          color: var(--el-color-warning);
        }

        &.kpi--success .kpi-num {
          color: var(--el-color-success);
        }
      }
    }

    .findings {
      .block-title {
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 600;
      }

      .sys-name {
        font-weight: 500;
        cursor: pointer;
      }

      .msg {
        font-size: 13px;
      }

      :deep(.el-table__row) {
        cursor: pointer;
      }
    }

    .gap-body {
      .block {
        margin-bottom: 18px;
      }

      .block-title {
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 600;
      }

      .level-tag {
        font-family: monospace;
      }
    }
  }
</style>
