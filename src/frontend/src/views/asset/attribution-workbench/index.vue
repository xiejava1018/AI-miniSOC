<!--
  OH-UI.3 归属确认工作台

  数据源：资产同步路径上 score_fusion 判定为 needs_review 的观测。
  设计要点（spike v0.1）：
  - 入口型列表在前：默认只看 pending，每条展示观测 IP / 最佳候选 /
    confidence / 冲突因子 / 重复触发次数
  - 右侧抽屉看全候选评分对比（观测值 vs 候选值逐因子），三个裁决动作：
      merge   合并到候选资产（复用同步合并路径，含漂移更新）
      create  确认不同实体，新建资产
      dismiss 忽略
  - 终态行不再给操作入口（后端也会 409），但保留状态筛选可追溯
-->
<template>
  <div class="attr-page art-full-height">
    <ElCard shadow="never" class="list-card">
      <template #header>
        <div class="card-head">
          <span class="t">归属确认工作台</span>
          <ElTag size="small" type="warning" effect="plain">
            待处理 {{ pendingCount }}
          </ElTag>
          <span class="meta">
            身份融合判定为「无法自动合并」的观测在此人工裁决
          </span>
        </div>
      </template>

      <div class="toolbar">
        <ElRadioGroup v-model="statusFilter" size="small" @change="loadList(1)">
          <ElRadioButton value="pending">待处理</ElRadioButton>
          <ElRadioButton value="merged">已合并</ElRadioButton>
          <ElRadioButton value="created">已新建</ElRadioButton>
          <ElRadioButton value="dismissed">已忽略</ElRadioButton>
        </ElRadioGroup>
        <ElButton :icon="Refresh" circle size="small" @click="loadList(1)" />
      </div>

      <ElTable v-loading="loading" :data="rows" stripe row-key="id">
        <ElTableColumn label="观测" min-width="180">
          <template #default="{ row }">
            <div class="obj-cell">
              <div class="obj-main">
                {{ row.observation?.name || '（未命名）' }}
              </div>
              <div class="obj-sub">
                {{ row.observation?.asset_ip }}
                <template v-if="row.observation?.network_segment">
                  · {{ row.observation.network_segment }}
                </template>
              </div>
            </div>
          </template>
        </ElTableColumn>

        <ElTableColumn label="最佳候选" min-width="180">
          <template #default="{ row }">
            <div v-if="row.best_score?.factors" class="cand-main">
              {{ candidateName(row) }}
            </div>
            <ElProgress
              :percentage="Math.round((row.confidence || 0) * 100)"
              :stroke-width="6"
              :status="progressStatus(row.confidence)"
              class="conf-bar"
            />
          </template>
        </ElTableColumn>

        <ElTableColumn label="冲突因子" width="160">
          <template #default="{ row }">
            <template v-if="row.conflict_factors?.length">
              <ElTag
                v-for="f in row.conflict_factors"
                :key="f"
                size="small"
                type="danger"
                effect="plain"
                class="factor-tag"
              >
                {{ factorLabel(f) }}
              </ElTag>
            </template>
            <span v-else class="muted">无强冲突</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="重复触发" width="100" align="center">
          <template #default="{ row }">
            <ElTag :type="row.occurrence_count > 1 ? 'warning' : 'info'" size="small">
              {{ row.occurrence_count }} 次
            </ElTag>
          </template>
        </ElTableColumn>

        <ElTableColumn label="来源" width="110">
          <template #default="{ row }">
            <span class="muted">{{ row.source }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="最近触发" min-width="160">
          <template #default="{ row }">
            <span class="muted">{{ formatTime(row.last_occurred_at) }}</span>
          </template>
        </ElTableColumn>

        <ElTableColumn label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <ElButton
                v-if="hasAuth('resolve')"
                text
                type="primary"
                size="small"
                @click="openDetail(row)"
              >
                裁决
              </ElButton>
              <span v-else class="muted">无权限</span>
            </template>
            <ElButton text size="small" @click="openDetail(row)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div class="pager">
        <ElPagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="() => loadList()"
          @size-change="() => loadList(1)"
        />
      </div>
    </ElCard>

    <!-- 裁决抽屉 -->
    <ElDrawer v-model="detailVisible" title="归属裁决" size="640px">
      <div v-if="detail" class="detail-body">
        <!-- 观测概览 -->
        <div class="block">
          <div class="block-title">待裁决观测</div>
          <ElDescriptions :column="2" border size="small">
            <ElDescriptionsItem label="IP">
              {{ detail.observation?.asset_ip || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="主机名">
              {{ detail.observation?.name || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="MAC">
              {{ detail.observation?.mac_address || '—' }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="Agent">
              {{ detail.observation?.wazuh_agent_id || '—' }}
            </ElDescriptionsItem>
          </ElDescriptions>
        </div>

        <!-- 候选评分对比 -->
        <div class="block">
          <div class="block-title">
            候选资产（{{ detail.candidates?.length || 0 }}）
          </div>
          <ElTable :data="detail.candidates" size="small" border>
            <ElTableColumn label="候选" min-width="150">
              <template #default="{ row }">
                <div class="cand-main">{{ row.name || '（未命名）' }}</div>
                <div class="obj-sub">{{ row.asset_ip }}</div>
              </template>
            </ElTableColumn>
            <ElTableColumn label="置信度" width="110">
              <template #default="{ row }">
                <ElProgress
                  :percentage="Math.round(row.score.confidence * 100)"
                  :stroke-width="6"
                  :status="progressStatus(row.score.confidence)"
                />
              </template>
            </ElTableColumn>
            <ElTableColumn
              v-if="detail.status === 'pending'"
              label="合并到"
              width="80"
              align="center"
            >
              <template #default="{ row }">
                <ElRadio v-model="mergeTarget" :value="row.asset_id" />
              </template>
            </ElTableColumn>
          </ElTable>
        </div>

        <!-- 逐因子明细 -->
        <div v-if="detail.best_score" class="block">
          <div class="block-title">逐因子判定（最佳候选）</div>
          <ElTable :data="detail.best_score.factors" size="small" border>
            <ElTableColumn prop="name" label="因子" width="110">
              <template #default="{ row }">
                {{ factorLabel(row.name) }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="观测值" min-width="120">
              <template #default="{ row }">{{ row.a_value ?? '—' }}</template>
            </ElTableColumn>
            <ElTableColumn label="候选值" min-width="120">
              <template #default="{ row }">{{ row.b_value ?? '—' }}</template>
            </ElTableColumn>
            <ElTableColumn label="结果" width="80" align="center">
              <template #default="{ row }">
                <ElTag
                  v-if="row.present && row.match"
                  type="success"
                  size="small"
                >
                  一致
                </ElTag>
                <ElTag
                  v-else-if="row.present"
                  type="danger"
                  size="small"
                >
                  矛盾
                </ElTag>
                <span v-else class="muted">缺失</span>
              </template>
            </ElTableColumn>
          </ElTable>
        </div>

        <!-- 备注 -->
        <div v-if="detail.status === 'pending'" class="block">
          <ElInput
            v-model="note"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="裁决备注（可选，记入审计日志）"
          />
        </div>

        <!-- 终态信息 -->
        <div v-if="detail.status !== 'pending'" class="block">
          <ElAlert :closable="false" type="info" show-icon>
            <template #title>
              {{ statusLabel(detail.status) }} · {{ detail.resolved_by || '—' }} ·
              {{ formatTime(detail.resolved_at) }}
            </template>
            <div v-if="detail.resolve_note">{{ detail.resolve_note }}</div>
          </ElAlert>
        </div>
      </div>

      <template v-if="detail?.status === 'pending' && hasAuth('resolve')" #footer>
        <div class="drawer-footer">
          <ElButton @click="detailVisible = false">取消</ElButton>
          <ElButton :loading="resolving" @click="submitResolve('dismiss')">
            忽略
          </ElButton>
          <ElButton
            type="warning"
            :loading="resolving"
            @click="submitResolve('create')"
          >
            新建资产
          </ElButton>
          <ElButton
            type="primary"
            :loading="resolving"
            :disabled="!mergeTarget"
            @click="submitResolve('merge')"
          >
            合并到候选
          </ElButton>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { ElMessage } from 'element-plus'
  import { Refresh } from '@element-plus/icons-vue'
  import {
    getAttributionReviews,
    getAttributionReview,
    resolveAttributionReview,
    type AttributionReviewItem,
    type AttributionStatus
  } from '@/api/asset'
  import { useAuth } from '@/hooks/core/useAuth'

  defineOptions({ name: 'AttributionWorkbench' })

  const { hasAuth } = useAuth()

  const rows = ref<AttributionReviewItem[]>([])
  const loading = ref(false)
  const statusFilter = ref<AttributionStatus>('pending')
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const pendingCount = ref(0)

  const detailVisible = ref(false)
  const detail = ref<AttributionReviewItem | null>(null)
  const mergeTarget = ref<string>('')
  const note = ref('')
  const resolving = ref(false)

  const FACTOR_LABELS: Record<string, string> = {
    ip: 'IP',
    mac: 'MAC',
    hostname: '主机名',
    wazuh_agent: 'Wazuh Agent',
    hardware: '硬件指纹'
  }
  const STATUS_LABELS: Record<string, string> = {
    merged: '已合并',
    created: '已新建',
    dismissed: '已忽略'
  }

  const factorLabel = (f: string) => FACTOR_LABELS[f] || f
  const statusLabel = (s: string) => STATUS_LABELS[s] || s

  const progressStatus = (v?: number | null): '' | 'success' | 'warning' | 'exception' => {
    if (v == null) return ''
    if (v >= 0.8) return 'success'
    if (v >= 0.4) return 'warning'
    return 'exception'
  }

  const formatTime = (v?: string | null) => {
    if (!v) return '—'
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return String(v)
    return d.toLocaleString('zh-CN', { hour12: false })
  }

  const candidateName = (row: AttributionReviewItem) => {
    const c = row.candidates?.[0]
    return c?.name || c?.asset_ip || '（候选已不存在）'
  }

  const loadList = async (toPage?: number) => {
    if (toPage) page.value = toPage
    loading.value = true
    try {
      const res = await getAttributionReviews({
        status: statusFilter.value,
        page: page.value,
        page_size: pageSize.value
      })
      rows.value = res?.data?.items || []
      total.value = res?.data?.total || 0
      pendingCount.value = res?.data?.pending_count || 0
    } catch (e: any) {
      ElMessage.error(e?.message || '加载待复核列表失败')
    } finally {
      loading.value = false
    }
  }

  const openDetail = async (row: AttributionReviewItem) => {
    detail.value = null
    detailVisible.value = true
    mergeTarget.value = ''
    note.value = ''
    try {
      const res = await getAttributionReview(row.id)
      detail.value = res?.data || null
      mergeTarget.value = detail.value?.candidate_asset_id || ''
    } catch (e: any) {
      ElMessage.error(e?.message || '加载详情失败')
      detailVisible.value = false
    }
  }

  const submitResolve = async (decision: 'merge' | 'create' | 'dismiss') => {
    if (!detail.value) return
    if (decision === 'merge' && !mergeTarget.value) {
      ElMessage.warning('请先选择要合并到的候选资产')
      return
    }
    resolving.value = true
    try {
      await resolveAttributionReview(detail.value.id, {
        decision,
        target_asset_id: decision === 'merge' ? mergeTarget.value : undefined,
        note: note.value || undefined
      })
      ElMessage.success('裁决成功')
      detailVisible.value = false
      await loadList()
    } catch (e: any) {
      // 409 已被他人处理 / 422 候选越界或已删除 —— 消息直接展示
      ElMessage.error(e?.message || '裁决失败')
    } finally {
      resolving.value = false
    }
  }

  loadList(1)
</script>

<style lang="scss" scoped>
  .attr-page {
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

    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }

    .obj-cell {
      .obj-main {
        font-weight: 500;
      }

      .obj-sub {
        font-size: 12px;
        color: var(--art-text-gray-500);
      }
    }

    .cand-main {
      font-weight: 500;
    }

    .conf-bar {
      margin-top: 4px;
    }

    .factor-tag {
      margin-right: 4px;
    }

    .muted {
      color: var(--art-text-gray-400);
    }

    .pager {
      display: flex;
      justify-content: flex-end;
      margin-top: 12px;
    }

    .detail-body {
      .block {
        margin-bottom: 20px;
      }

      .block-title {
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 600;
      }
    }

    .drawer-footer {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }
</style>
