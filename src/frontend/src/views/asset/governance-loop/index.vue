<!--
  治理闭环看板（OH-7.4）

  汇总闭环六步的运行态势（只读）：
    - KPI：工单总数 / 闭环率 / 卡点数量
    - 阶段分布 + 漏斗（dispatch→handling→verify→returned→closed）
    - 卡点清单（verify_overdue / unassigned / recurring）
    - 权重学习报告（OH-7.3）只读嵌入
  数据全部来自既有 GET 端点，不新增判定、不自动闭环。
-->
<template>
  <div class="governance-loop-page" v-loading="loading">
    <!-- KPI -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-num">{{ status.total_tickets }}</div>
        <div class="kpi-label">工单总数</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-num">{{ status.closed_rate }}%</div>
        <div class="kpi-label">闭环率（剔除已取消）</div>
      </div>
      <div class="kpi-card" :class="{ alert: status.blocker_count > 0 }">
        <div class="kpi-num">{{ status.blocker_count }}</div>
        <div class="kpi-label">卡点工单</div>
      </div>
    </div>

    <div class="two-col">
      <!-- 阶段漏斗 -->
      <ElCard shadow="never" class="panel">
        <template #header><span class="panel-title">闭环漏斗</span></template>
        <div class="funnel">
          <div v-for="f in funnelView" :key="f.stage" class="funnel-row">
            <div class="funnel-label">{{ stageLabel[f.stage] }}</div>
            <div class="funnel-bar-wrap">
              <div class="funnel-bar" :style="{ width: f.width + '%' }" />
              <span class="funnel-count" :style="{ left: f.width + '%' }">{{ f.count }}</span>
            </div>
          </div>
          <div class="funnel-row cancelled">
            <div class="funnel-label">已取消</div>
            <div class="funnel-bar-wrap">
              <div class="funnel-bar cancelled"
                   :style="{ width: cancelledWidth + '%' }" />
              <span class="funnel-count">{{ cancelledCount }}</span>
            </div>
          </div>
        </div>
      </ElCard>

      <!-- 阶段分布 -->
      <ElCard shadow="never" class="panel">
        <template #header><span class="panel-title">阶段分布</span></template>
        <div class="dist-grid">
          <div v-for="f in status.funnel" :key="f.stage" class="dist-item">
            <div class="dist-num">{{ f.count }}</div>
            <div class="dist-label">{{ stageLabel[f.stage] }}</div>
          </div>
          <div class="dist-item">
            <div class="dist-num">{{ cancelledCount }}</div>
            <div class="dist-label">已取消</div>
          </div>
        </div>
      </ElCard>
    </div>

    <!-- 卡点清单 -->
    <ElCard shadow="never" class="panel">
      <template #header>
        <span class="panel-title">卡点清单（{{ status.blocker_count }}）</span>
      </template>
      <ElEmpty v-if="status.blockers.length === 0" description="暂无卡点"
               :image-size="70" />
      <ElTable v-else :data="status.blockers" table-layout="fixed">
        <ElTableColumn prop="title" label="工单" min-width="180" show-overflow-tooltip />
        <ElTableColumn prop="kind" label="卡点类型" width="140">
          <template #default="{ row }">
            <ElTag :type="blockerTag[row.kind]">{{ blockerLabel[row.kind] }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn prop="message" label="说明" min-width="200" show-overflow-tooltip />
      </ElTable>
    </ElCard>

    <!-- 权重学习（只读） -->
    <ElCard shadow="never" class="panel">
      <template #header><span class="panel-title">权重学习报告（复盘）</span></template>
      <div v-if="!feedback.sample_sufficient" class="muted">
        {{ feedback.message }}（当前 {{ feedback.total_verified }} /
        需 {{ feedback.min_sample }} 已验证工单）
      </div>
      <template v-else>
        <ElTable :data="feedback.suggestions" table-layout="fixed" size="small">
          <ElTableColumn prop="dimension" label="维度" width="140" />
          <ElTableColumn prop="direction" label="方向" width="90">
            <template #default="{ row }">
              <ElTag :type="row.direction === 'up' ? 'danger' : 'success'">
                {{ row.direction === 'up' ? '上调' : '下调' }} {{ row.delta }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="reason" label="依据" min-width="200" show-overflow-tooltip />
        </ElTable>
        <ElAlert v-if="feedback.suggestions.length === 0" type="success"
                 :closable="false" show-icon
                 title="样本充足，但当前分布未触发调整建议" style="margin-top: 10px" />
      </template>
      <div class="red-line">{{ feedback.red_line }}</div>
    </ElCard>

    <div class="red-line root">{{ status.red_line }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getLoopStatus,
  getWeightFeedback,
  type LoopStatus,
  type WeightFeedback,
} from '@/api/asset'

const loading = ref(false)
const status = reactive<LoopStatus>({
  total_tickets: 0,
  stage_distribution: {},
  funnel: [],
  closed_rate: 0,
  blockers: [],
  blocker_count: 0,
  red_line: '',
})
const feedback = reactive<WeightFeedback>({
  total_verified: 0,
  min_sample: 30,
  sample_sufficient: false,
  by_dimension: {},
  suggestions: [],
  current_weights: {},
  red_line: '',
})

const stageLabel: Record<string, string> = {
  dispatch: '派单',
  handling: '处置中',
  verify: '待验证',
  returned: '已驳回',
  closed: '已闭环',
  cancelled: '已取消',
}
const blockerLabel: Record<string, string> = {
  verify_overdue: '验证超期',
  unassigned: '未指派',
  recurring: '反复问题',
}
const blockerTag: Record<string, any> = {
  verify_overdue: 'warning',
  unassigned: 'danger',
  recurring: 'info',
}

const maxFunnel = computed(() =>
  Math.max(1, ...status.funnel.map(f => f.count)))

const funnelView = computed(() =>
  status.funnel.map(f => ({
    ...f,
    width: Math.round(f.count * 100 / maxFunnel.value),
  })))

const cancelledCount = computed(() =>
  status.stage_distribution.cancelled || 0)
const cancelledWidth = computed(() =>
  Math.round(cancelledCount.value * 100 / maxFunnel.value))

async function load() {
  loading.value = true
  try {
    const [s, f] = await Promise.all([getLoopStatus(), getWeightFeedback()])
    Object.assign(status, s)
    Object.assign(feedback, f)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.governance-loop-page {
  padding: 4px 2px 8px;
}
.kpi-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.kpi-card {
  flex: 1;
  min-width: 160px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 16px 20px;
}
.kpi-card.alert {
  border-color: var(--el-color-warning-light-5);
}
.kpi-num {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
}
.kpi-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.panel {
  margin-bottom: 12px;
}
.panel-title {
  font-weight: 600;
}
.funnel-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.funnel-label {
  width: 70px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.funnel-bar-wrap {
  flex: 1;
  position: relative;
  height: 22px;
}
.funnel-bar {
  height: 100%;
  background: var(--el-color-primary);
  border-radius: 3px;
  min-width: 2px;
}
.funnel-bar.cancelled {
  background: var(--el-text-color-disabled);
}
.funnel-count {
  position: absolute;
  left: calc(var(--w, 0) + 6px);
  top: 1px;
  font-size: 13px;
  padding-left: 6px;
}
.funnel-row.cancelled .funnel-count {
  position: static;
}
.dist-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.dist-item {
  text-align: center;
  padding: 10px 0;
}
.dist-num {
  font-size: 24px;
  font-weight: 600;
}
.dist-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.red-line {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 8px;
}
.red-line.root {
  margin-top: 4px;
}
@media (max-width: 1100px) {
  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>
