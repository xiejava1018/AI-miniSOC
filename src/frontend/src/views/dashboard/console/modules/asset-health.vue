<!--
  资产健康度 - Dashboard console 入口卡
  设计文档: docs/design/2026-06-03-asset-overview-design.md §4.1

  复用概览页 KPI 字段,4 张 MetricCard 横排 + 右上角"查看详情"按钮跳转
  走 /api/v1/assets/overview 端点的 kpi 字段(单独请求,不与概览页共享 store)
-->
<template>
  <div class="art-card asset-health-card mb-5 max-sm:mb-4">
    <div class="asset-health-card__header">
      <div class="title">
        <h4>资产健康度</h4>
        <p>实时反映 SOC 风险全貌</p>
      </div>
      <ElButton
        type="primary"
        text
        bg
        size="small"
        @click="goOverview"
      >
        查看详情 →
      </ElButton>
    </div>

    <ElRow :gutter="16" v-loading="loading">
      <ElCol :sm="12" :md="6" v-for="kpi in kpiCards" :key="kpi.label">
        <div
          class="metric-card"
          :class="[`metric-card--${kpi.type}`, { 'metric-card--muted': kpi.value === 0 }]"
        >
          <div class="metric-card__label">{{ kpi.label }}</div>
          <div class="metric-card__value">
            <span class="metric-card__number">{{ kpi.value }}</span>
            <span v-if="kpi.suffix" class="metric-card__suffix">{{ kpi.suffix }}</span>
          </div>
        </div>
      </ElCol>
    </ElRow>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { getAssetOverview } from '@/api/asset'

  defineOptions({ name: 'AssetHealth' })

  const router = useRouter()
  const kpi = ref<Api.Asset.AssetOverviewKpi | null>(null)
  const loading = ref(false)

  const kpiCards = computed(() => {
    const k = kpi.value
    return [
      {
        label: '总资产',
        value: k?.total_assets ?? 0,
        suffix: '个',
        type: 'info' as const
      },
      {
        label: '高危资产',
        value: k?.high_risk_assets ?? 0,
        suffix: '个',
        type: 'danger' as const
      },
      {
        label: '24h 告警',
        value: k?.alerts_24h ?? 0,
        suffix: '条',
        type: 'danger' as const
      },
      {
        label: '未关闭事件',
        value: k?.open_incidents ?? 0,
        suffix: '个',
        type: 'warning' as const
      }
    ]
  })

  const goOverview = () => {
    router.push('/asset/overview')
  }

  const fetchKpi = async () => {
    loading.value = true
    try {
      const res = await getAssetOverview()
      if (res.code === 200 && res.data) {
        kpi.value = res.data.kpi
      }
    } catch (err) {
      console.error('[AssetHealth] 加载 KPI 失败:', err)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    fetchKpi()
  })
</script>

<style lang="scss" scoped>
  .asset-health-card {
    padding: 20px;
    box-sizing: border-box;

    &__header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 16px;

      .title {
        h4 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
          color: var(--el-text-color-primary, #303133);
        }
        p {
          margin: 4px 0 0;
          font-size: 12px;
          color: var(--el-text-color-secondary, #909399);
        }
      }
    }
  }

  .metric-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 14px;
    background: var(--el-fill-color-blank, #fff);
    border: 1px solid var(--el-border-color-lighter, #ebeef5);
    border-left-width: 3px;
    border-radius: 4px;
    margin-bottom: 12px;
    min-height: 76px;

    &--info {
      border-left-color: var(--el-color-primary, #409eff);
      .metric-card__number {
        color: var(--el-color-primary, #409eff);
      }
    }

    &--danger {
      border-left-color: var(--el-color-danger, #f56c6c);
      .metric-card__number {
        color: var(--el-color-danger, #f56c6c);
      }
    }

    &--warning {
      border-left-color: var(--el-color-warning, #e6a23c);
      .metric-card__number {
        color: var(--el-color-warning, #e6a23c);
      }
    }

    &--muted .metric-card__number {
      color: var(--el-text-color-placeholder, #c0c4cc);
    }

    &__label {
      font-size: 12px;
      color: var(--el-text-color-secondary, #606266);
    }

    &__value {
      display: flex;
      align-items: baseline;
      gap: 4px;
    }

    &__number {
      font-size: 22px;
      font-weight: 600;
      line-height: 1.1;
      font-variant-numeric: tabular-nums;
    }

    &__suffix {
      font-size: 12px;
      color: var(--el-text-color-secondary, #606266);
    }
  }
</style>
