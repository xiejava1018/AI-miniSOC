<!--
  变更风险预测结果面板（OH-UI.12 · S11）

  展示纯启发式风险分 + 贡献因子 + 证据汇总 + 降级源。
  红线：这是「风险」不是「成功率」；不伪造源覆盖。
-->
<template>
  <div class="risk-predict-panel">
    <!-- 未识别资产 -->
    <ElAlert
      v-if="!result.identified"
      type="error"
      show-icon
      :closable="false"
      class="banner"
      :title="result.message || '未识别到具体资产'"
    >
      <div class="banner-body">请补充 IP、主机名或网段后重试。</div>
    </ElAlert>

    <template v-else>
      <!-- 降级源 -->
      <ElAlert
        v-if="result.degraded_sources.length"
        type="warning"
        show-icon
        :closable="false"
        class="banner"
        title="部分数据源不可达，预测基于可得数据，可能低估风险"
      >
        <div class="banner-body">
          <ElTag v-for="s in result.degraded_sources" :key="s"
                  size="small" type="warning" class="src-tag">{{ s }}</ElTag>
        </div>
      </ElAlert>

      <ElCard shadow="never" class="risk-card">
        <div class="risk-head">
          <div class="risk-score-block">
            <div class="risk-score" :class="result.risk_level">
              {{ result.risk_score }}
            </div>
            <ElTag :type="levelTag[result.risk_level]" size="large" effect="dark">
              {{ levelLabel[result.risk_level] }}风险
            </ElTag>
          </div>
          <div class="risk-meta">
            <div class="meta-row">
              <span class="meta-label">定位目标</span>
              <span>{{ (result.targets || []).length }} 台</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">回溯窗口</span>
              <span>{{ result.history_days }} 天</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">维护窗口</span>
              <span>{{ result.change_window_hours }} 小时</span>
            </div>
          </div>
        </div>

        <ElDivider />

        <!-- 贡献因子 -->
        <div class="section-title">风险贡献因子</div>
        <div v-if="result.contributing_factors.length" class="factors">
          <div v-for="(f, i) in result.contributing_factors" :key="i"
               class="factor-row">
            <span class="dot" />{{ f }}
          </div>
        </div>
        <div v-else class="muted">近窗口内无显著风险信号</div>

        <!-- 证据汇总 -->
        <template v-if="result.evidence_summary">
          <ElDivider />
          <div class="section-title">证据汇总</div>
          <pre class="evidence">{{ JSON.stringify(result.evidence_summary, null, 2) }}</pre>
        </template>

        <div class="red-line">{{ result.red_line }}</div>
      </ElCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { ChangeRiskPredictResult } from '@/api/asset'

defineProps<{ result: ChangeRiskPredictResult }>()

const levelLabel: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '严重', unknown: '未知',
}
const levelTag: Record<string, any> = {
  low: 'success', medium: 'info', high: 'warning', critical: 'danger',
  unknown: 'info',
}
</script>

<style scoped>
.banner {
  margin-bottom: 12px;
}
.banner-body {
  margin-top: 6px;
}
.src-tag {
  margin-right: 6px;
}
.risk-card {
  margin-bottom: 12px;
}
.risk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.risk-score-block {
  display: flex;
  align-items: center;
  gap: 14px;
}
.risk-score {
  font-size: 44px;
  font-weight: 700;
  line-height: 1;
}
.risk-score.low { color: var(--el-color-success); }
.risk-score.medium { color: var(--el-color-info); }
.risk-score.high { color: var(--el-color-warning); }
.risk-score.critical { color: var(--el-color-danger); }
.risk-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.meta-row {
  font-size: 13px;
}
.meta-label {
  display: inline-block;
  width: 72px;
  color: var(--el-text-color-secondary);
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 8px;
}
.factors {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.factor-row {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-warning);
  flex: none;
}
.evidence {
  margin: 0;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.muted {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
.red-line {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 12px;
}
</style>
