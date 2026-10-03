<!--
  数据健康（P3/F1.3 v1.2）

  三层数据健康的统一入口。分层不是为了好看，而是排障时要先判断该找谁：
    源健康   基础设施层 —— 采集器/同步任务还在不在工作
    同步死信 数据层     —— 同步过程中被丢弃/失败的数据
    稽核差异 业务层     —— 台账与实际网络的差异
  上层异常往往是下层引起的，所以从上往下排。

  soc_source_health 与 soc_sync_dead_letter 以前只有后台任务在写表、
  没有任何界面，出问题没人知道。这个页面是它们第一次可见。
-->
<template>
  <div class="dh-page art-full-height" v-loading="loading">
    <!-- 总体结论 -->
    <ElCard shadow="never" class="overall-card" :class="`ov-${data?.overall_status || 'unknown'}`">
      <div class="overall-body">
        <div class="ov-left">
          <div class="ov-status">
            <ElIcon class="ov-icon"><component :is="statusIcon" /></ElIcon>
            <span class="ov-text">{{ statusLabel }}</span>
          </div>
          <div class="ov-time">检查时间 {{ formatTime(data?.checked_at) }}</div>
        </div>
        <div class="ov-right">
          <template v-if="data?.issues?.length">
            <div v-for="(it, i) in data.issues" :key="i" class="issue-item">· {{ it }}</div>
          </template>
          <div v-else class="issue-item ok">三层检查均未发现问题</div>
        </div>
        <ElButton :loading="loading" @click="load">刷新</ElButton>
      </div>
    </ElCard>

    <ElRow :gutter="12">
      <!-- 第 1 层：源健康 -->
      <ElCol :xs="24" :lg="8">
        <ElCard shadow="never" class="layer-card">
          <template #header>
            <div class="card-head">
              <span class="t">数据源健康</span>
              <span class="sub">基础设施层</span>
              <div class="counter">
                <ElTag size="small" type="success" effect="plain">
                  正常 {{ counter.healthy }}
                </ElTag>
                <ElTag v-if="counter.degraded" size="small" type="warning" effect="plain">
                  过期 {{ counter.degraded }}
                </ElTag>
                <ElTag v-if="counter.down" size="small" type="danger" effect="plain">
                  故障 {{ counter.down }}
                </ElTag>
                <ElTag v-if="counter.unknown" size="small" type="info" effect="plain">
                  未知 {{ counter.unknown }}
                </ElTag>
              </div>
            </div>
          </template>

          <ElEmpty
            v-if="!sources.length"
            :image-size="60"
            description="尚无数据源健康记录（采集链路可能未接入监控）"
          />
          <div v-for="s in sources" :key="s.source_key" class="src-item">
            <div class="src-head">
              <ElTag size="small" :type="srcTag(s.status)" effect="dark">
                {{ srcLabel(s.status) }}
              </ElTag>
              <span class="src-name">{{ s.display_name }}</span>
              <span class="src-type">{{ s.source_type }}</span>
            </div>
            <div v-if="s.reason" class="src-reason">{{ s.reason }}</div>
            <div class="src-meta">
              最近成功 {{ formatTime(s.last_success_at) || '无' }}
              <template v-if="s.last_records_count != null">
                · {{ s.last_records_count }} 条
              </template>
              · 成功 {{ s.success_count }} / 失败 {{ s.failure_count }}
            </div>
            <div v-if="s.last_failure_message" class="src-err">
              {{ s.last_failure_message }}
            </div>
          </div>

          <!-- 同步任务新鲜度：台账数据的可信度依据 -->
          <div class="sync-fresh">
            <div class="sf-title">资产同步</div>
            <div class="sf-row" :class="{ warn: data?.sync_freshness?.stale }">
              最近成功：{{ formatTime(data?.sync_freshness?.last_success_at) || '无记录' }}
              <ElTag v-if="data?.sync_freshness?.stale" size="small" type="warning" effect="plain">
                超 {{ data?.sync_freshness?.stale_threshold_hours }}h 未更新
              </ElTag>
            </div>
            <div v-if="lastCounts" class="sf-row sub">
              上次同步 {{ lastCounts.total }} 台（新增 {{ lastCounts.created }} / 更新
              {{ lastCounts.updated }} / 失败 {{ lastCounts.failed }}）
            </div>
            <div v-if="data?.sync_freshness?.last_failure_at" class="sf-row err">
              最近失败 {{ formatTime(data.sync_freshness.last_failure_at) }}：
              {{ data.sync_freshness.last_failure_message || '未记录原因' }}
            </div>
          </div>
        </ElCard>
      </ElCol>

      <!-- 第 2 层：同步死信 -->
      <ElCol :xs="24" :lg="8">
        <ElCard shadow="never" class="layer-card">
          <template #header>
            <div class="card-head">
              <span class="t">同步死信</span>
              <span class="sub">数据层</span>
              <div class="counter">
                <ElTag
                  size="small"
                  :type="deadLetter.pending ? 'danger' : 'success'"
                  effect="plain"
                >
                  待处理 {{ deadLetter.pending }}
                </ElTag>
                <ElTag size="small" type="info" effect="plain"> 累计 {{ deadLetter.total }} </ElTag>
              </div>
            </div>
          </template>

          <ElEmpty v-if="!deadLetter.pending" :image-size="60" description="没有被丢弃的同步数据" />
          <template v-else>
            <div class="dl-group">
              <div
                v-for="g in deadLetter.by_source || []"
                :key="`${g.source}-${g.data_type}`"
                class="dl-row"
              >
                <span class="dl-src">{{ g.source }}</span>
                <span class="dl-type">{{ g.data_type }}</span>
                <span class="dl-count">{{ g.count }} 条</span>
              </div>
            </div>
            <div class="dl-samples">
              <div class="ds-title">最近样本</div>
              <div v-for="d in deadLetter.samples || []" :key="d.id" class="ds-item">
                <div class="ds-head">
                  <span class="ds-key">{{ d.item_key || '(无 key)' }}</span>
                  <span class="ds-time">{{ formatTime(d.created_at) }}</span>
                </div>
                <div class="ds-err">
                  {{ d.error_class
                  }}<template v-if="d.error_message">: {{ d.error_message }}</template>
                </div>
                <div v-if="d.replay_count" class="ds-meta">已重放 {{ d.replay_count }} 次</div>
              </div>
            </div>
          </template>
        </ElCard>
      </ElCol>

      <!-- 第 3 层：稽核差异 -->
      <ElCol :xs="24" :lg="8">
        <ElCard shadow="never" class="layer-card">
          <template #header>
            <div class="card-head">
              <span class="t">台账稽核</span>
              <span class="sub">业务层</span>
              <div class="counter">
                <ElTag size="small" :type="reconPending ? 'warning' : 'success'" effect="plain">
                  待处理 {{ reconPending }}
                </ElTag>
              </div>
            </div>
          </template>

          <ElEmpty v-if="!latestRun?.has_data" :image-size="60" description="尚未执行过稽核">
            <ElButton type="primary" size="small" @click="goRecon">前往稽核</ElButton>
          </ElEmpty>
          <template v-else>
            <div class="rc-stats">
              <div class="rc-box">
                <div class="rc-label">影子资产</div>
                <div class="rc-value danger">{{ latestRun.by_type?.shadow || 0 }}</div>
              </div>
              <div class="rc-box">
                <div class="rc-label">疑似下线</div>
                <div class="rc-value warning">{{ latestRun.by_type?.offline || 0 }}</div>
              </div>
              <div class="rc-box">
                <div class="rc-label">不一致</div>
                <div class="rc-value info">{{ latestRun.by_type?.mismatch || 0 }}</div>
              </div>
            </div>
            <div class="rc-meta">
              最近稽核 {{ formatTime(latestRun.checked_at) }} · 共 {{ latestRun.diff_total }} 项
            </div>
            <ElAlert
              v-if="latestRun.freshness?.degraded"
              type="warning"
              :closable="false"
              show-icon
              class="rc-alert"
            >
              <template #title>该次稽核时数据源异常，结果可能不全</template>
            </ElAlert>
            <div class="rc-status">
              <span v-for="(v, k) in latestRun.by_status || {}" :key="k" class="rs-item">
                {{ statusText(String(k)) }} {{ v }}
              </span>
            </div>
            <ElButton text type="primary" size="small" @click="goRecon"> 查看差异明细 → </ElButton>
          </template>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 第 4 层：画像完整度（OH-2.5，八维画像层） -->
    <ElCard v-loading="aggLoading" shadow="never" class="layer-card agg-card">
      <template #header>
        <div class="card-head">
          <span class="t">画像完整度</span>
          <span class="sub">八维画像层</span>
          <div class="counter">
            <ElTag size="small" type="primary" effect="plain">
              已评估 {{ agg?.computed_assets ?? '—' }} / {{ agg?.total_assets ?? '—' }} 台
            </ElTag>
            <ElTag size="small" effect="plain">均分 {{ agg?.aggregate_coverage?.avg_overall_score ?? '—' }}</ElTag>
            <ElTag size="small" effect="plain">AHS 均分 {{ agg?.aggregate_coverage?.avg_ahs_score ?? '—' }}</ElTag>
          </div>
        </div>
      </template>

      <ElEmpty v-if="!agg || !agg.total_assets" :image-size="60" description="尚无资产可评估" />
      <template v-else>
        <ElAlert
          v-if="agg.truncated"
          type="info"
          :closable="false"
          show-icon
          class="agg-alert"
        >
          <template #title>资产数已达单次评估上限，当前仅覆盖前 {{ agg.computed_assets + agg.error_assets }} 台</template>
        </ElAlert>
        <div class="agg-grid">
          <!-- 左：八维覆盖 -->
          <div class="agg-col dims">
            <div class="agg-col-title">八维覆盖（覆盖率 = 覆盖资产 / 已评估）</div>
            <div v-for="d in agg.dimension_coverage" :key="d.dimension" class="dim-row">
              <span class="dim-name">{{ dimLabel(d.dimension) }}</span>
              <ElProgress
                class="dim-bar"
                :percentage="Math.round(d.ratio * 100)"
                :stroke-width="10"
                :color="ratioColor(d.ratio)"
              />
              <span class="dim-meta">{{ d.covered }}/{{ agg.computed_assets }} · 置信 {{ d.avg_confidence.toFixed(2) }}</span>
            </div>
          </div>

          <!-- 中：完整度分布 + 状态分布 -->
          <div class="agg-col hist">
            <div class="agg-col-title">完整度分布</div>
            <div v-for="(v, k) in agg.score_distribution" :key="k" class="hist-row">
              <span class="hist-label">{{ k }}</span>
              <div class="hist-bar-wrap">
                <div
                  class="hist-bar"
                  :style="{ width: histWidth(v) + '%', background: histColor(String(k)) }"
                />
              </div>
              <span class="hist-count">{{ v }}</span>
            </div>
            <div class="agg-col-title state-title">状态分布</div>
            <div class="state-tags">
              <ElTag
                v-for="(v, k) in agg.aggregate_coverage.state_distribution"
                :key="k"
                size="small"
                :type="stateTagType(String(k))"
                effect="plain"
              >
                {{ stateLabel(String(k)) }} {{ v }}
              </ElTag>
            </div>
          </div>

          <!-- 右：缺失维度定位（worst 5） -->
          <div class="agg-col worst">
            <div class="agg-col-title">缺失维度定位（完整度最低 5 台）</div>
            <div
              v-for="w in agg.worst_assets"
              :key="w.asset_id"
              class="worst-row"
              @click="goAsset(w.asset_id)"
            >
              <div class="worst-head">
                <span class="worst-name">{{ w.asset_name || w.asset_ip || w.asset_id }}</span>
                <span class="worst-score" :class="scoreClass(w.overall_score)">{{ w.overall_score }}</span>
              </div>
              <div class="worst-dims">
                <template v-if="w.missing_dims.length">
                  <ElTag
                    v-for="d in w.missing_dims"
                    :key="d"
                    size="small"
                    type="danger"
                    effect="plain"
                  >
                    {{ dimLabel(d) }}
                  </ElTag>
                </template>
                <span v-else class="worst-full">八维全覆盖</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import {
    CircleCheckFilled,
    WarningFilled,
    CircleCloseFilled,
    QuestionFilled
  } from '@element-plus/icons-vue'
  import { getDataHealth, getAssetCompletenessAggregate } from '@/api/asset'
  import type { AssetCompletenessAggregate } from '@/api/asset'

  defineOptions({ name: 'AssetDataHealth' })

  const router = useRouter()
  const loading = ref(false)
  const data = ref<any>(null)
  const aggLoading = ref(false)
  const agg = ref<AssetCompletenessAggregate | null>(null)

  const counter = computed(
    () => data.value?.source_health?.counter || { healthy: 0, degraded: 0, down: 0, unknown: 0 }
  )
  const sources = computed(() => data.value?.source_health?.sources || [])
  const deadLetter = computed(
    () => data.value?.dead_letter || { pending: 0, total: 0, by_source: [], samples: [] }
  )
  const latestRun = computed(() => data.value?.reconciliation?.latest_run || null)
  const reconPending = computed(() => data.value?.reconciliation?.pending_all_runs || 0)
  const lastCounts = computed(() => data.value?.sync_freshness?.last_success_counts || null)

  const STATUS_MAP: Record<string, string> = {
    healthy: '数据链路正常',
    degraded: '数据链路降级',
    down: '数据链路故障',
    unknown: '状态未知'
  }
  const statusLabel = computed(() => STATUS_MAP[data.value?.overall_status] || '状态未知')
  const statusIcon = computed(() => {
    switch (data.value?.overall_status) {
      case 'healthy':
        return CircleCheckFilled
      case 'degraded':
        return WarningFilled
      case 'down':
        return CircleCloseFilled
      default:
        return QuestionFilled
    }
  })

  const SRC_LABEL: Record<string, string> = {
    healthy: '正常',
    degraded: '过期',
    down: '故障',
    unknown: '未知'
  }
  const srcLabel = (s: string) => SRC_LABEL[s] || s
  const srcTag = (s: string): 'success' | 'warning' | 'danger' | 'info' =>
    (({ healthy: 'success', degraded: 'warning', down: 'danger', unknown: 'info' } as Record<string, 'success' | 'warning' | 'danger' | 'info'>)[s] || 'info')

  const RECON_STATUS: Record<string, string> = {
    pending: '待处理',
    confirmed: '已确认',
    ignored: '已忽略',
    resolved: '已处理'
  }
  const statusText = (k: string) => RECON_STATUS[k] || k

  const formatTime = (v?: string | null) => {
    if (!v) return ''
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return String(v)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }

  const goRecon = () => router.push('/assets/reconciliation')
  const goAsset = (id: string) => router.push(`/assets/detail/${id}`)

  // ===== OH-2.5 画像完整度子卡 =====
  const DIM_LABEL: Record<string, string> = {
    identity: '身份',
    ownership: '归属',
    technology: '技术',
    exposure: '暴露',
    vulnerability: '脆弱',
    threat: '威胁',
    compliance: '合规',
    behavior: '行为'
  }
  const dimLabel = (d: string) => DIM_LABEL[d] || d

  const ratioColor = (r: number) => (r >= 0.8 ? '#67c23a' : r >= 0.5 ? '#e6a23c' : '#f56c6c')

  const STATE_LABEL: Record<string, string> = {
    valid: '完整',
    partial: '部分覆盖',
    insufficient_data: '数据不足',
    error: '计算失败'
  }
  const stateLabel = (s: string) => STATE_LABEL[s] || s
  const stateTagType = (
    s: string
  ): 'success' | 'warning' | 'danger' | 'info' | 'primary' =>
    (({
      valid: 'success',
      partial: 'primary',
      insufficient_data: 'warning',
      error: 'danger'
    } as Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'>)[s] || 'info')

  const histMax = computed(() => {
    const vals = Object.values(agg.value?.score_distribution || {})
    return vals.length ? Math.max(...vals) : 0
  })
  const histWidth = (v: number) => (histMax.value ? Math.round((v / histMax.value) * 100) : 0)
  const histColor = (bucket: string) => {
    const lo = parseInt(bucket, 10)
    if (lo >= 81) return '#67c23a'
    if (lo >= 61) return '#95d475'
    if (lo >= 41) return '#e6a23c'
    if (lo >= 21) return '#f89898'
    return '#f56c6c'
  }
  const scoreClass = (s: number) => (s >= 61 ? 'good' : s >= 41 ? 'mid' : 'bad')

  const loadAggregate = async () => {
    aggLoading.value = true
    try {
      const res = await getAssetCompletenessAggregate(100)
      agg.value = (res?.data as AssetCompletenessAggregate) || null
    } catch (e: any) {
      // 完整度子卡失败不阻塞页面主三层，只静默降级
      agg.value = null
    } finally {
      aggLoading.value = false
    }
  }

  const load = async () => {
    loading.value = true
    try {
      const res = await getDataHealth(5)
      data.value = res?.data || null
    } catch (e: any) {
      ElMessage.error(e?.message || '加载数据健康失败')
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    load()
    loadAggregate()
  })
</script>

<style lang="scss" scoped>
  .dh-page {
    .overall-card {
      margin-bottom: 12px;
      border-left: 4px solid var(--el-color-info);

      &.ov-healthy {
        border-left-color: var(--el-color-success);
      }

      &.ov-degraded {
        border-left-color: var(--el-color-warning);
      }

      &.ov-down {
        border-left-color: var(--el-color-danger);
      }

      .overall-body {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
        align-items: center;
      }

      .ov-left {
        min-width: 180px;

        .ov-status {
          display: flex;
          gap: 8px;
          align-items: center;

          .ov-icon {
            font-size: 22px;
          }

          .ov-text {
            font-size: 17px;
            font-weight: 600;
          }
        }

        .ov-time {
          margin-top: 4px;
          font-size: 12px;
          color: var(--art-text-gray-500);
        }
      }

      .ov-right {
        flex: 1;
        min-width: 240px;

        .issue-item {
          font-size: 13px;
          line-height: 1.8;
          color: var(--el-color-warning);

          &.ok {
            color: var(--art-text-gray-600);
          }
        }
      }
    }

    .layer-card {
      height: 100%;
      margin-bottom: 12px;

      .card-head {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;

        .t {
          font-size: 15px;
          font-weight: 600;
        }

        .sub {
          padding: 1px 6px;
          font-size: 11px;
          color: var(--art-text-gray-500);
          background: var(--art-gray-100);
          border-radius: 3px;
        }

        .counter {
          display: flex;
          flex-wrap: wrap;
          gap: 4px;
          margin-left: auto;
        }
      }
    }

    .src-item {
      padding: 8px 0;
      border-bottom: 1px solid var(--art-border-color);

      &:last-child {
        border-bottom: none;
      }

      .src-head {
        display: flex;
        gap: 8px;
        align-items: center;

        .src-name {
          font-size: 13px;
          font-weight: 500;
        }

        .src-type {
          font-size: 11px;
          color: var(--art-text-gray-500);
        }
      }

      .src-reason {
        margin-top: 3px;
        font-size: 12px;
        color: var(--el-color-warning);
      }

      .src-meta {
        margin-top: 3px;
        font-size: 11px;
        color: var(--art-text-gray-500);
      }

      .src-err {
        margin-top: 3px;
        font-size: 11px;
        color: var(--el-color-danger);
        word-break: break-all;
      }
    }

    .sync-fresh {
      padding-top: 10px;
      margin-top: 10px;
      border-top: 1px dashed var(--art-border-color);

      .sf-title {
        margin-bottom: 4px;
        font-size: 13px;
        font-weight: 500;
      }

      .sf-row {
        display: flex;
        gap: 6px;
        align-items: center;
        font-size: 12px;
        line-height: 1.8;

        &.warn {
          color: var(--el-color-warning);
        }

        &.sub {
          color: var(--art-text-gray-500);
        }

        &.err {
          color: var(--el-color-danger);
        }
      }
    }

    .dl-group {
      margin-bottom: 10px;

      .dl-row {
        display: flex;
        gap: 8px;
        align-items: center;
        font-size: 12px;
        line-height: 1.9;

        .dl-src {
          font-weight: 500;
        }

        .dl-type {
          color: var(--art-text-gray-500);
        }

        .dl-count {
          margin-left: auto;
          color: var(--el-color-danger);
        }
      }
    }

    .dl-samples {
      .ds-title {
        margin-bottom: 4px;
        font-size: 12px;
        color: var(--art-text-gray-600);
      }

      .ds-item {
        padding: 6px 0;
        border-top: 1px solid var(--art-border-color);

        .ds-head {
          display: flex;
          gap: 8px;
          font-size: 12px;

          .ds-key {
            font-weight: 500;
          }

          .ds-time {
            margin-left: auto;
            color: var(--art-text-gray-500);
          }
        }

        .ds-err {
          margin-top: 2px;
          font-size: 11px;
          color: var(--el-color-danger);
          word-break: break-all;
        }

        .ds-meta {
          font-size: 11px;
          color: var(--art-text-gray-500);
        }
      }
    }

    .rc-stats {
      display: flex;
      gap: 8px;
      margin-bottom: 8px;

      .rc-box {
        flex: 1;
        padding: 8px;
        text-align: center;
        background: var(--art-main-bg-color);
        border-radius: 4px;

        .rc-label {
          font-size: 11px;
          color: var(--art-text-gray-600);
        }

        .rc-value {
          margin-top: 2px;
          font-size: 20px;
          font-weight: 600;

          &.danger {
            color: var(--el-color-danger);
          }

          &.warning {
            color: var(--el-color-warning);
          }

          &.info {
            color: var(--el-color-info);
          }
        }
      }
    }

    .rc-meta {
      font-size: 12px;
      color: var(--art-text-gray-500);
    }

    .rc-alert {
      margin: 8px 0;
    }

    .rc-status {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 6px 0;
      font-size: 12px;
      color: var(--art-text-gray-600);
    }

    /* ===== OH-2.5 画像完整度子卡 ===== */
    .agg-card {
      margin-top: 12px;

      .agg-alert {
        margin-bottom: 10px;
      }

      .agg-grid {
        display: grid;
        grid-template-columns: minmax(300px, 5fr) minmax(240px, 3fr) minmax(260px, 4fr);
        gap: 24px;

        @media (width <= 1200px) {
          grid-template-columns: 1fr;
        }
      }

      .agg-col-title {
        margin-bottom: 10px;
        font-size: 12px;
        font-weight: 600;
        color: var(--art-text-gray-700);

        &.state-title {
          margin-top: 16px;
        }
      }

      /* 左列：八维覆盖 */
      .dims {
        .dim-row {
          display: grid;
          grid-template-columns: 44px 1fr auto;
          align-items: center;
          gap: 10px;
          margin-bottom: 8px;

          .dim-name {
            font-size: 12px;
            color: var(--art-text-gray-600);
          }

          .dim-meta {
            font-size: 11px;
            color: var(--art-text-gray-500);
            white-space: nowrap;
          }
        }
      }

      /* 中列：直方图 + 状态 */
      .hist {
        .hist-row {
          display: grid;
          grid-template-columns: 52px 1fr 28px;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;

          .hist-label {
            font-size: 11px;
            color: var(--art-text-gray-500);
            text-align: right;
          }

          .hist-bar-wrap {
            height: 12px;
            overflow: hidden;
            background: var(--art-gray-200, #f0f2f5);
            border-radius: 6px;

            .hist-bar {
              min-width: 2px;
              height: 100%;
              border-radius: 6px;
              transition: width 0.4s ease;
            }
          }

          .hist-count {
            font-size: 12px;
            font-weight: 600;
            color: var(--art-text-gray-700);
          }
        }

        .state-tags {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
      }

      /* 右列：缺失维度定位 */
      .worst {
        .worst-row {
          padding: 8px 10px;
          margin-bottom: 8px;
          cursor: pointer;
          border: 1px solid var(--art-border-light, #e8eaec);
          border-radius: 8px;
          transition: all 0.2s;

          &:hover {
            border-color: var(--el-color-primary-light-5);
            box-shadow: var(--art-box-shadow-sm, 0 2px 8px rgb(0 0 0 / 6%));
          }

          .worst-head {
            display: flex;
            align-items: center;
            justify-content: space-between;

            .worst-name {
              overflow: hidden;
              font-size: 13px;
              font-weight: 500;
              color: var(--art-text-gray-800);
              text-overflow: ellipsis;
              white-space: nowrap;
            }

            .worst-score {
              flex-shrink: 0;
              margin-left: 8px;
              font-size: 16px;
              font-weight: 700;

              &.good {
                color: var(--el-color-success);
              }

              &.mid {
                color: var(--el-color-warning);
              }

              &.bad {
                color: var(--el-color-danger);
              }
            }
          }

          .worst-dims {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 6px;

            .worst-full {
              font-size: 11px;
              color: var(--el-color-success);
            }
          }
        }
      }
    }
  }
</style>
