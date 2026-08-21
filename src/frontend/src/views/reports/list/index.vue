<!--
  安全报告列表 / 详情（P3 / F2.2）

  PRD 设计原则在 UI 里的体现：
  - 报告是「人话」的摘要"。 详情四章节直接渲染文本，不用花哨组件，
    不让用户面对一堆图表
  - data_coverage 是硬门槛。 详情顶部始终显示数据说明，缺数据的报告
    必须明显高亮，否则用户会以为是「无问题」的报告
  - 触发按钮都用 ElMessage 回显真实后端 msg（500/503 绝不能笼统「生成失败」）
-->
<template>
  <div class="reports-page art-full-height">
    <ElCard shadow="never" class="toolbar">
      <div class="toolbar-left">
        <h3 class="t">安全报告</h3>
        <span class="meta">基于规则 + GLM 的结构化运维摘要，可作周会材料</span>
      </div>
      <div class="toolbar-right">
        <ElSelect
          v-model="filterType"
          size="default"
          style="width: 140px"
          @change="() => loadList(1)"
        >
          <ElOption label="全部类型" value="" />
          <ElOption label="周报" value="weekly" />
          <ElOption label="月报" value="monthly" />
          <ElOption label="按需" value="on_demand" />
          <ElOption label="事件驱动" value="incident_driven" />
        </ElSelect>
        <ElButton
          v-if="hasAuth('generate')"
          type="primary"
          :loading="generating"
          @click="openGenerateDialog()"
        >
          生成报告
        </ElButton>
        <ElButton v-if="hasAuth('trigger')" :loading="triggering" @click="handleCheckTrigger">
          事件驱动检查
        </ElButton>
      </div>
    </ElCard>

    <div class="main-grid">
      <!-- 左侧列表 -->
      <ElCard shadow="never" class="list-card" v-loading="listLoading">
        <ElEmpty v-if="!rows.length && !listLoading" description="尚无报告" />
        <div
          v-for="r in rows"
          :key="r.id"
          class="report-item"
          :class="{ active: r.id === selectedId }"
          @click="selectReport(r)"
        >
          <div class="ri-head">
            <ElTag size="small" :type="typeTag(r.report_type)" effect="plain">
              {{ typeLabel(r.report_type) }}
            </ElTag>
            <span class="ri-time">{{ formatTime(r.created_at) }}</span>
          </div>
          <div class="ri-title">{{ r.title }}</div>
          <div class="ri-summary">{{ truncate(r.summary, 100) }}</div>
          <div class="ri-meta">
            <span>{{ r.triggered_by }}</span>
            <span v-if="r.data_coverage?.data_degraded" class="warn">数据降级</span>
          </div>
        </div>
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

      <!-- 右侧详情 -->
      <ElCard shadow="never" class="detail-card" v-loading="detailLoading">
        <ElEmpty v-if="!selected" :image-size="80" description="从左侧选一份报告查看详情" />
        <template v-else>
          <div class="detail-head">
            <div class="head-main">
              <ElTag size="small" :type="typeTag(selected.report_type)" effect="plain">
                {{ typeLabel(selected.report_type) }}
              </ElTag>
              <h2 class="t">{{ selected.title }}</h2>
              <div class="meta">
                触发人 {{ selected.triggered_by }} · 周期 {{ formatTime(selected.period_start) }} ~
                {{ formatTime(selected.period_end) }}
                <template v-if="selected.prompt_version">
                  · 模型 {{ selected.prompt_version }}</template
                >
                <template v-if="selected.trigger_meta?.critical_high_count != null">
                  · critical+high {{ selected.trigger_meta.critical_high_count }} / 阈值
                  {{ selected.trigger_meta.threshold }}
                </template>
              </div>
            </div>
            <div class="head-actions">
              <AiFeedback
                v-if="selected.prompt_version?.startsWith('security-report')"
                target-type="report"
                :target-id="selected.id"
              />
            </div>
          </div>

          <!-- 数据说明：硬门槛，置顶且明显 -->
          <ElAlert
            v-if="selected.data_coverage?.data_degraded"
            type="warning"
            :closable="false"
            show-icon
            class="coverage-alert"
          >
            <template #title> 数据可信度降级，结果可能不全 </template>
            <div class="coverage-body">
              <div v-for="g in selected.data_coverage.gaps || []" :key="g.scope" class="gap-row">
                <div class="gap-scope">· {{ g.scope }}</div>
                <div class="gap-reason">{{ g.reason }}</div>
                <div class="gap-impact">{{ g.impact }}</div>
              </div>
            </div>
          </ElAlert>
          <ElAlert v-else type="success" :closable="false" show-icon class="coverage-alert">
            <template #title>数据完整，本次报告覆盖窗口无缺口</template>
          </ElAlert>

          <!-- 执行摘要（AI） -->
          <section class="block">
            <h4 class="block-t">执行摘要</h4>
            <div class="block-body">{{ selected.summary }}</div>
          </section>

          <!-- 总览（规则拼装，不走 AI） -->
          <section class="block">
            <h4 class="block-t">资产总览</h4>
            <pre class="block-body">{{ selected.content.overview }}</pre>
          </section>

          <!-- 趋势 -->
          <section class="block">
            <h4 class="block-t">告警趋势</h4>
            <pre class="block-body">{{ selected.content.trends }}</pre>
          </section>

          <!-- 风险 Top5 -->
          <section class="block">
            <h4 class="block-t">高风险资产</h4>
            <pre class="block-body">{{ selected.content.risks }}</pre>
          </section>

          <!-- 高亮风险（AI） -->
          <section v-if="selected.risk_highlights" class="block">
            <h4 class="block-t">高亮风险</h4>
            <pre class="block-body">{{ selected.risk_highlights }}</pre>
          </section>

          <!-- 处置建议（AI） -->
          <section v-if="selected.recommendations" class="block">
            <h4 class="block-t">处置建议</h4>
            <pre class="block-body">{{ selected.recommendations }}</pre>
          </section>

          <!-- 数据说明（详细） -->
          <section class="block block-notes">
            <h4 class="block-t">数据说明（完整）</h4>
            <pre class="block-body">{{ selected.content.data_notes }}</pre>
            <div v-if="selected.data_coverage?.source_health?.length" class="src-health">
              <div
                v-for="s in selected.data_coverage.source_health"
                :key="s.source_key"
                class="sh-row"
                :class="{ overdue: s.overdue }"
              >
                <span class="sh-key">{{ s.source_key }}</span>
                <span class="sh-time">最近成功 {{ formatTime(s.last_success_at) || '无' }}</span>
                <span v-if="s.reason" class="sh-reason">{{ s.reason }}</span>
              </div>
            </div>
          </section>
        </template>
      </ElCard>
    </div>

    <!-- 生成对话框 -->
    <ElDialog v-model="genVisible" title="生成报告" width="520px" :close-on-click-modal="false">
      <ElForm label-width="92px" :model="genForm">
        <ElFormItem label="报告类型">
          <ElRadioGroup v-model="genForm.report_type">
            <ElRadioButton value="weekly">周报</ElRadioButton>
            <ElRadioButton value="monthly">月报</ElRadioButton>
            <ElRadioButton value="on_demand">按需</ElRadioButton>
          </ElRadioGroup>
        </ElFormItem>
        <template v-if="genForm.report_type === 'on_demand'">
          <ElFormItem label="起始时间" required>
            <ElDatePicker
              v-model="genForm.period_start"
              type="datetime"
              format="YYYY-MM-DD HH:mm"
              placeholder="必填"
              style="width: 100%"
            />
          </ElFormItem>
          <ElFormItem label="结束时间" required>
            <ElDatePicker
              v-model="genForm.period_end"
              type="datetime"
              format="YYYY-MM-DD HH:mm"
              placeholder="必填"
              style="width: 100%"
            />
          </ElFormItem>
        </template>
        <ElFormItem label="使用 AI">
          <ElSwitch
            v-model="genForm.force_glm"
            :active-text="'AI 解读'"
            :inactive-text="'仅规则模板'"
          />
          <span class="form-tip">
            AI 解读会调用 GLM（约 3-10 秒）。预算耗尽时自动降级为规则模板。
          </span>
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="genVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="generating" @click="handleGenerate">生成</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted } from 'vue'
  import { ElMessage } from 'element-plus'
  import {
    listReports,
    getReport,
    generateReport,
    checkIncidentTrigger,
    type SecurityReport,
    type ReportType
  } from '@/api/asset'
  import { useAuth } from '@/hooks/core/useAuth'
  import AiFeedback from '@/components/business/ai-feedback/index.vue'

  defineOptions({ name: 'SecurityReports' })

  const { hasAuth } = useAuth()

  const rows = ref<SecurityReport[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const filterType = ref<'' | ReportType>('')
  const listLoading = ref(false)

  const selected = ref<SecurityReport | null>(null)
  const detailLoading = ref(false)
  const selectedId = computed(() => selected.value?.id || null)

  const generating = ref(false)
  const triggering = ref(false)
  const genVisible = ref(false)
  const genForm = ref({
    report_type: 'weekly' as ReportType,
    period_start: undefined as Date | undefined,
    period_end: undefined as Date | undefined,
    force_glm: true
  })

  const TYPE_LABEL: Record<string, string> = {
    weekly: '周报',
    monthly: '月报',
    on_demand: '按需',
    incident_driven: '事件驱动'
  }
  const TYPE_TAG: Record<string, string> = {
    weekly: 'primary',
    monthly: 'success',
    on_demand: 'info',
    incident_driven: 'warning'
  }
  const typeLabel = (t: string) => TYPE_LABEL[t] || t
  const typeTag = (t: string) => TYPE_TAG[t] || 'info'

  const formatTime = (v?: string | null) => {
    if (!v) return ''
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return String(v)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  const truncate = (v: string | null | undefined, n: number) => {
    if (!v) return ''
    return v.length > n ? v.slice(0, n) + '…' : v
  }

  const loadList = async (toPage?: number) => {
    if (toPage) page.value = toPage
    listLoading.value = true
    try {
      const res = await listReports({
        report_type: (filterType.value || undefined) as ReportType | undefined,
        page: page.value,
        page_size: pageSize.value
      })
      rows.value = res?.data?.records || []
      total.value = res?.data?.total || 0
      // 自动选中第一份（仅在当前未选时）
      if (!selected.value && rows.value.length) selectReport(rows.value[0])
    } catch (e: any) {
      ElMessage.error(e?.message || '加载报告列表失败')
    } finally {
      listLoading.value = false
    }
  }

  const selectReport = async (r: SecurityReport) => {
    detailLoading.value = true
    try {
      const res = await getReport(r.id)
      selected.value = res?.data || r
    } catch (e: any) {
      // 选中失败不影响列表
      selected.value = r
      ElMessage.warning(e?.message || '详情获取失败，显示列表摘要')
    } finally {
      detailLoading.value = false
    }
  }

  const openGenerateDialog = () => {
    genForm.value = {
      report_type: 'weekly',
      period_start: undefined,
      period_end: undefined,
      force_glm: true
    }
    genVisible.value = true
  }

  const handleGenerate = async () => {
    if (genForm.value.report_type === 'on_demand') {
      if (!genForm.value.period_start || !genForm.value.period_end) {
        ElMessage.error('按需报告必须选择起止时间')
        return
      }
    }
    generating.value = true
    try {
      const body: any = {
        report_type: genForm.value.report_type,
        force_glm: genForm.value.force_glm
      }
      if (genForm.value.report_type === 'on_demand') {
        body.period_start = new Date(genForm.value.period_start).toISOString()
        body.period_end = new Date(genForm.value.period_end).toISOString()
      }
      const res = await generateReport(body)
      const r = res?.data
      ElMessage.success(r ? `${r.title} 已生成` : '报告已生成')
      genVisible.value = false
      await loadList(1)
      if (r) selectReport(r as SecurityReport)
    } catch (e: any) {
      ElMessage.error(e?.message || '生成失败')
    } finally {
      generating.value = false
    }
  }

  const handleCheckTrigger = async () => {
    triggering.value = true
    try {
      const res = await checkIncidentTrigger()
      const d = res?.data || {}
      if (d.triggered && d.report) {
        ElMessage.success(
          `已达阈值（critical+high ${d.critical_high_count} ≥ ${d.threshold}），已生成事件驱动报告`
        )
        await loadList(1)
        selectReport(d.report as SecurityReport)
      } else if (!d.opensearch_ok) {
        ElMessage.warning(`OpenSearch 不可达：${d.opensearch_error || '未知'}`)
      } else {
        ElMessage.info(
          `未达阈值（critical+high ${d.critical_high_count} < ${d.threshold}），无需生成`
        )
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '检查失败')
    } finally {
      triggering.value = false
    }
  }

  onMounted(() => loadList(1))
</script>

<style lang="scss" scoped>
  .reports-page {
    .toolbar {
      display: flex;
      margin-bottom: 12px;

      .toolbar-left {
        display: flex;
        flex: 1;
        gap: 12px;
        align-items: baseline;

        .t {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }

        .meta {
          font-size: 12px;
          color: var(--art-text-gray-500);
        }
      }

      .toolbar-right {
        display: flex;
        gap: 8px;
        align-items: center;
      }
    }

    .main-grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 12px;
      min-height: 0;

      @media (max-width: 1100px) {
        grid-template-columns: 1fr;
      }
    }

    .list-card {
      display: flex;
      flex-direction: column;
      min-height: 0;
      max-height: calc(100vh - 200px);

      .report-item {
        padding: 12px;
        cursor: pointer;
        border-bottom: 1px solid var(--art-border-color);
        transition: background 0.15s;

        &:hover {
          background: var(--art-gray-100);
        }

        &.active {
          background: var(--el-color-primary-light-9);
          border-left: 3px solid var(--el-color-primary);
        }

        .ri-head {
          display: flex;
          gap: 6px;
          align-items: center;
          justify-content: space-between;

          .ri-time {
            font-size: 11px;
            color: var(--art-text-gray-500);
          }
        }

        .ri-title {
          margin: 6px 0;
          font-size: 13px;
          font-weight: 500;
          line-height: 1.5;
        }

        .ri-summary {
          font-size: 12px;
          line-height: 1.6;
          color: var(--art-text-gray-600);
        }

        .ri-meta {
          display: flex;
          gap: 8px;
          align-items: center;
          margin-top: 4px;
          font-size: 11px;
          color: var(--art-text-gray-500);

          .warn {
            color: var(--el-color-warning);
          }
        }
      }

      .pager {
        display: flex;
        justify-content: flex-end;
        padding: 8px 0 0;
        margin-top: auto;
      }
    }

    .detail-card {
      min-height: 0;
      overflow-y: auto;
      max-height: calc(100vh - 200px);

      .detail-head {
        display: flex;
        gap: 12px;
        align-items: flex-start;
        margin-bottom: 16px;

        .head-main {
          flex: 1;

          .t {
            margin: 6px 0 4px;
            font-size: 18px;
            font-weight: 600;
          }

          .meta {
            font-size: 12px;
            color: var(--art-text-gray-500);
          }
        }
      }

      .coverage-alert {
        margin-bottom: 16px;

        .coverage-body {
          margin-top: 4px;

          .gap-row {
            padding: 2px 0;
            font-size: 12px;
            line-height: 1.7;

            .gap-scope {
              font-weight: 500;
            }

            .gap-reason {
              margin-left: 8px;
              color: var(--art-text-gray-600);
            }

            .gap-impact {
              margin-left: 8px;
              color: var(--el-color-warning);
            }
          }
        }
      }

      .block {
        padding: 12px 0;
        border-top: 1px dashed var(--art-border-color);

        &:first-of-type {
          border-top: none;
        }

        .block-t {
          margin: 0 0 8px;
          font-size: 14px;
          font-weight: 600;
          color: var(--art-text-gray-700);
        }

        .block-body {
          margin: 0;
          font-size: 13px;
          line-height: 1.85;
          white-space: pre-wrap;
          color: var(--art-text-gray-800);
          font-family: inherit;
        }

        &.block-notes {
          background: var(--art-gray-50);
          padding: 12px 16px;
          border-radius: 6px;
          border-top: none;
        }
      }

      .src-health {
        margin-top: 8px;

        .sh-row {
          display: flex;
          gap: 12px;
          align-items: center;
          padding: 4px 0;
          font-size: 12px;

          &.overdue .sh-key {
            color: var(--el-color-warning);
          }

          .sh-time {
            color: var(--art-text-gray-500);
          }

          .sh-reason {
            color: var(--el-color-warning);
          }
        }
      }
    }
  }

  .form-tip {
    display: inline-block;
    margin-left: 8px;
    font-size: 12px;
    color: var(--art-text-gray-500);
  }
</style>
