<!--
  资产知识图谱 - P95 性能看板（OH-3.6）

  设计依据：
    - docs/design/2026-09-30-资产管理AI能力建设-实施方案.md OH-3.6
    - 跟踪表 §一总表 / §五 T-7
    - 后端 /api/v1/graph/perf 提供 4 类 query P50/P95/max/avg/slow_count + slow ring buffer

  功能：
    1. 顶部 4 个 P95 卡片（neighbors / paths / impact_scope / vuln_chokepoints）
       超阈值（≥500ms）红色 + 样本数 + slow_count
    2. 中部「最近慢查询」表：timestamp + latency + query_type + asset_key
    3. 底部「样本统计 + 窗口信息」：window_size + 实际样本数 + 阈值
    4. admin 才有「重置采样」按钮（清零重新基线；OH-3.8 扩容触发后用）

  不做：
    - 时序曲线（项目无 chart 库导入门槛；表格 + 颜色更轻）
    - Prometheus exporter（项目无该栈；OH-3.7 自己落库告警即可）
-->
<template>
  <div class="perf-page art-full-height" v-loading="loading">
    <!-- 页头 -->
    <div class="perf-header">
      <div>
        <h2 class="page-title">图谱 P95 性能看板</h2>
        <p class="page-desc">
          4 类图查询（neighbors / paths / impact_scope / vuln_chokepoints）的滑动窗口时延。
          超过 {{ thresholdLabel }}ms 阈值会标红并落「最近慢查询」。OH-3.7 告警 / OH-3.8
          扩容触发线共用本数据。
        </p>
      </div>
      <div class="perf-header-actions">
        <ElButton :icon="Refresh" :loading="loading" @click="load">刷新</ElButton>
        <ElButton
          v-if="canReset"
          :icon="Delete"
          type="danger"
          plain
          :loading="resetting"
          @click="onReset"
        >重置采样</ElButton>
      </div>
    </div>

    <!-- 主内容：4 P95 卡片 + 慢查询表 -->
    <div v-if="data" class="perf-body">
      <!-- 4 P95 卡片 -->
      <ElRow :gutter="16" class="p95-row">
        <ElCol v-for="card in cards" :key="card.key" :xs="24" :sm="12" :md="6">
          <ElCard shadow="never" class="p95-card" :class="{ 'over-threshold': card.overThreshold }">
            <div class="p95-card-label">{{ card.label }}</div>
            <div class="p95-card-value">
              <span class="big">{{ formatMs(card.p95_ms) }}</span>
              <span class="unit">ms</span>
            </div>
            <div class="p95-card-meta">
              <div><span class="k">样本</span><span class="v">{{ card.samples }}</span></div>
              <div><span class="k">P50</span><span class="v">{{ formatMs(card.p50_ms) }}ms</span></div>
              <div><span class="k">Avg</span><span class="v">{{ formatMs(card.avg_ms) }}ms</span></div>
              <div><span class="k">Max</span><span class="v">{{ formatMs(card.max_ms) }}ms</span></div>
              <div>
                <span class="k">慢</span>
                <span class="v" :class="{ 'warn': card.slow_count > 0 }">{{ card.slow_count }}</span>
              </div>
            </div>
            <div v-if="card.overThreshold" class="p95-card-warn">
              <ElIcon><WarningFilled /></ElIcon>
              P95 超过 {{ formatMs(card.threshold) }}ms 阈值
            </div>
          </ElCard>
        </ElCol>
      </ElRow>

      <!-- 最近慢查询 -->
      <ElCard shadow="never" class="slow-card">
        <template #header>
          <div class="slow-header">
            <span class="slow-title">最近慢查询</span>
            <span class="slow-meta">阈值 {{ thresholdLabel }}ms · ring buffer 上限 50</span>
          </div>
        </template>
        <ElTable
          :data="slowRows"
          :empty-text="slowEmptyText"
          stripe
          size="small"
          class="slow-table"
        >
          <ElTableColumn prop="latency_ms" label="耗时 (ms)" width="120" align="right">
            <template #default="{ row }">
              <span class="latency" :class="latencyClass(row.latency_ms)">
                {{ formatMs(row.latency_ms) }}
              </span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="query_type" label="查询类型" width="160">
            <template #default="{ row }">
              <ElTag :type="queryTypeTag(row.query_type)" size="small">
                {{ queryTypeLabel(row.query_type) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="asset_key" label="资产键" min-width="200">
            <template #default="{ row }">
              <span class="asset-key">{{ row.asset_key || '—' }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="ts" label="时刻" width="160">
            <template #default="{ row }">
              {{ formatTs(row.ts) }}
            </template>
          </ElTableColumn>
        </ElTable>
      </ElCard>

      <!-- 窗口信息 -->
      <ElCard shadow="never" class="window-card">
        <template #header>
          <div class="win-header">
            <span class="win-title">窗口信息</span>
            <span class="win-meta">滑动窗口上限 {{ windowSize }} 样本/端点</span>
          </div>
        </template>
        <div class="window-grid">
          <div class="win-item">
            <div class="win-k">窗口上限</div>
            <div class="win-v">{{ windowSize }}</div>
          </div>
          <div class="win-item">
            <div class="win-k">慢查询阈值</div>
            <div class="win-v">{{ thresholdLabel }} ms</div>
          </div>
          <div class="win-item">
            <div class="win-k">4 端点样本合计</div>
            <div class="win-v">{{ totalSamples }}</div>
          </div>
          <div class="win-item">
            <div class="win-k">4 端点慢查询合计</div>
            <div class="win-v" :class="{ warn: totalSlow > 0 }">{{ totalSlow }}</div>
          </div>
        </div>
        <div class="window-foot">
          数据来源：内存滑动窗口（deque(maxlen={{ windowSize }})）+ ring buffer (50)；
          重启进程后样本清零，不持久化。
        </div>
      </ElCard>
    </div>

    <!-- 空态 -->
    <ElEmpty v-else-if="!loading && loadError" :description="loadError" />
    <ElEmpty v-else-if="!loading" description="加载中…" />
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { Refresh, Delete, WarningFilled } from '@element-plus/icons-vue'
  import { useUserStore } from '@/store/modules/user'
  import {
    getGraphPerf,
    postGraphPerfReset,
    type GraphPerfResponse,
    type GraphSlowQuery,
    type GraphQueryType
  } from '@/api/graph'

  defineOptions({ name: 'AssetGraphPerf' })

  // ---------- state ----------
  const loading = ref(false)
  const resetting = ref(false)
  const data = ref<GraphPerfResponse | null>(null)
  const loadError = ref<string>('')

  const userStore = useUserStore()
  const canReset = computed(() => {
    const info = userStore.info || {}
    // 后端可能返回 user.role_code / role.code / role / 用户表 'role_code' 字段
    // 兼顾不同时期的字段命名（CLAUDE.md T-3 教训）
    const role =
      (info as any).role_code ||
      (info as any).roleCode ||
      (info as any).role?.code ||
      (info as any).role ||
      ''
    return role === 'admin' || role === 'R_SUPER'
  })

  // ---------- 派生 ----------
  const windowSize = computed(() => data.value?.snapshot.window_size ?? 200)
  const thresholdLabel = computed(() =>
    data.value ? Math.round(data.value.snapshot.slow_threshold_ms) : 500
  )

  const QUERY_LABEL: Record<GraphQueryType, string> = {
    neighbors: '邻居子图 (BFS)',
    paths: '最短攻击路径',
    impact_scope: '影响面聚合',
    vuln_chokepoints: '修复阻塞点'
  }

  const cards = computed(() => {
    if (!data.value) return []
    const snap = data.value.snapshot
    return (['neighbors', 'paths', 'impact_scope', 'vuln_chokepoints'] as GraphQueryType[]).map(
      (k) => ({
        key: k,
        label: QUERY_LABEL[k],
        p50_ms: snap.p50_ms[k],
        p95_ms: snap.p95_ms[k],
        avg_ms: snap.avg_ms[k],
        max_ms: snap.max_ms[k],
        samples: snap.samples[k],
        slow_count: snap.slow_count[k],
        threshold: snap.slow_threshold_ms,
        overThreshold: snap.p95_ms[k] >= snap.slow_threshold_ms
      })
    )
  })

  const slowRows = computed<GraphSlowQuery[]>(() => data.value?.recent_slow ?? [])
  const slowEmptyText = computed(() =>
    data.value && data.value.recent_slow.length === 0
      ? `暂无慢查询（阈值 ${thresholdLabel.value}ms）`
      : '加载中…'
  )

  const totalSamples = computed(() =>
    cards.value.reduce((s, c) => s + c.samples, 0)
  )
  const totalSlow = computed(() =>
    cards.value.reduce((s, c) => s + c.slow_count, 0)
  )

  // ---------- 辅助 ----------
  const formatMs = (v: number) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return '0'
    return v < 10 ? v.toFixed(2) : v < 100 ? v.toFixed(1) : v.toFixed(0)
  }

  const formatTs = (ts: number) => {
    // 后端 ts 是 time.monotonic()，无意义；前端改为「距今 N 秒前」语义
    // 但 monotonic 不可转 wallclock；改用相对位置（ring 顺序）即可
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
  }

  const queryTypeLabel = (q: GraphQueryType) => QUERY_LABEL[q] || q

  const queryTypeTag = (q: GraphQueryType): 'primary' | 'success' | 'warning' | 'info' => {
    return (
      ({
        neighbors: 'primary',
        paths: 'warning',
        impact_scope: 'success',
        vuln_chokepoints: 'info'
      } as Record<GraphQueryType, 'primary' | 'success' | 'warning' | 'info'>)[q] || 'info'
    )
  }

  const latencyClass = (ms: number) =>
    ms >= 1000 ? 'very-slow' : ms >= 500 ? 'slow' : 'fast'

  // ---------- load ----------
  const load = async () => {
    loading.value = true
    loadError.value = ''
    try {
      const res = await getGraphPerf(10)
      data.value = (res?.data as GraphPerfResponse) || null
    } catch (e: any) {
      loadError.value = e?.message || '加载图谱性能看板失败'
      data.value = null
    } finally {
      loading.value = false
    }
  }

  const onReset = async () => {
    try {
      await ElMessageBox.confirm(
        '确认清空滑动窗口 + 慢查询 ring buffer？OH-3.8 扩容触发后通常用。',
        '重置采样',
        { type: 'warning', confirmButtonText: '确认重置', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
    resetting.value = true
    try {
      await postGraphPerfReset()
      ElMessage.success('已重置')
      await load()
    } catch (e: any) {
      ElMessage.error(e?.message || '重置失败')
    } finally {
      resetting.value = false
    }
  }

  onMounted(load)
</script>

<style lang="scss" scoped>
  .perf-page {
    padding: 16px;

    .perf-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
      gap: 12px;

      .page-title {
        margin: 0 0 4px;
        font-size: 20px;
        font-weight: 600;
      }
      .page-desc {
        margin: 0;
        font-size: 13px;
        color: var(--el-text-color-secondary);
        max-width: 760px;
        line-height: 1.5;
      }
      .perf-header-actions {
        display: flex;
        gap: 8px;
        flex-shrink: 0;
      }
    }

    .perf-body {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .p95-row {
      margin-bottom: 0;
    }

    .p95-card {
      border-left: 4px solid var(--el-color-info);
      transition: border-left-color 0.2s;

      &.over-threshold {
        border-left-color: var(--el-color-danger);
      }

      .p95-card-label {
        font-size: 13px;
        color: var(--el-text-color-secondary);
        margin-bottom: 8px;
      }

      .p95-card-value {
        margin-bottom: 12px;
        .big {
          font-size: 32px;
          font-weight: 700;
          color: var(--el-text-color-primary);
          font-variant-numeric: tabular-nums;
        }
        .unit {
          margin-left: 4px;
          font-size: 14px;
          color: var(--el-text-color-secondary);
        }
      }

      .p95-card-meta {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 4px 12px;
        font-size: 12px;
        color: var(--el-text-color-secondary);

        > div {
          display: flex;
          justify-content: space-between;
        }
        .v {
          color: var(--el-text-color-primary);
          font-variant-numeric: tabular-nums;
          &.warn {
            color: var(--el-color-danger);
            font-weight: 600;
          }
        }
      }

      .p95-card-warn {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px dashed var(--el-color-danger-light-5);
        color: var(--el-color-danger);
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 4px;
      }
    }

    .slow-card {
      .slow-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;

        .slow-title {
          font-size: 15px;
          font-weight: 600;
        }
        .slow-meta {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }
      .slow-table {
        .latency {
          font-variant-numeric: tabular-nums;
          font-weight: 600;
          &.fast {
            color: var(--el-color-success);
          }
          &.slow {
            color: var(--el-color-warning);
          }
          &.very-slow {
            color: var(--el-color-danger);
          }
        }
        .asset-key {
          font-family: var(--el-font-family-monospace, monospace);
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }
    }

    .window-card {
      .win-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;

        .win-title {
          font-size: 15px;
          font-weight: 600;
        }
        .win-meta {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }

      .window-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
      }

      .win-item {
        padding: 12px;
        background: var(--el-fill-color-light);
        border-radius: 4px;

        .win-k {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          margin-bottom: 4px;
        }
        .win-v {
          font-size: 18px;
          font-weight: 600;
          color: var(--el-text-color-primary);
          font-variant-numeric: tabular-nums;
          &.warn {
            color: var(--el-color-danger);
          }
        }
      }

      .window-foot {
        margin-top: 12px;
        font-size: 12px;
        color: var(--el-text-color-secondary);
      }
    }
  }
</style>
