<template>
  <div class="browsing-event-page art-full-height" id="table-full-screen">
    <!-- 统计卡片 -->
    <ElRow :gutter="12" class="stat-row">
      <ElCol :span="6">
        <ElCard shadow="never" class="stat-card">
          <div class="stat-label">今日异常</div>
          <div class="stat-value">{{ stats.today_total || 0 }}</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="stat-card critical">
          <div class="stat-label">严重/高危</div>
          <div class="stat-value">
            {{ (stats.today_by_severity?.critical || 0) + (stats.today_by_severity?.high || 0) }}
          </div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="stat-card warning">
          <div class="stat-label">中危</div>
          <div class="stat-value">{{ stats.today_by_severity?.medium || 0 }}</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="stat-card">
          <div class="stat-label">Top规则</div>
          <div class="stat-value stat-rule">
            {{ topRule || '—' }}
          </div>
        </ElCard>
      </ElCol>
    </ElRow>

    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="resetSearchParams"
      @search="getDataByPage"
    />

    <ElCard shadow="never" class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" @refresh="refresh">
        <template #left>
          <ElButton type="primary" plain @click="handleRefreshAll">刷新数据</ElButton>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="异常事件详情" size="600px">
      <template v-if="detail">
        <ElDescriptions :column="1" border>
          <ElDescriptionsItem label="源 IP">{{ detail.ip }}</ElDescriptionsItem>
          <ElDescriptionsItem label="目标域名">{{ detail.domain }}</ElDescriptionsItem>
          <ElDescriptionsItem label="应用类型">{{ detail.apptype || '—' }}</ElDescriptionsItem>
          <ElDescriptionsItem label="分值">
            <ElTag :type="severityType(detail.severity)">{{ detail.score }} ({{ detail.severity }})</ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="状态">
            <ElTag>{{ detail.status }}</ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="窗口内记录数">{{ detail.source_count }}</ElDescriptionsItem>
          <ElDescriptionsItem label="检测窗口">
            {{ detail.window_start }} ~ {{ detail.window_end }}
          </ElDescriptionsItem>
          <ElDescriptionsItem label="命中规则">
            <div v-for="h in detail.rule_hits" :key="h.rule" class="rule-hit">
              <ElTag size="small" type="warning">{{ h.rule }}</ElTag>
              <span class="rule-weight">+{{ h.weight }}</span>
              <span class="rule-detail">{{ h.detail }}</span>
            </div>
          </ElDescriptionsItem>
          <ElDescriptionsItem v-if="detail.incident_id" label="关联事件">
            <ElLink type="primary" :href="`/#/system/incident?id=${detail.incident_id}`" target="_blank">
              查看安全事件
            </ElLink>
          </ElDescriptionsItem>
        </ElDescriptions>

        <div class="detail-actions">
          <ElButton @click="handleStatus(detail, 'confirmed')" type="primary" plain>确认为威胁</ElButton>
          <ElButton @click="handleStatus(detail, 'false_positive')" type="warning" plain>标记误报</ElButton>
          <ElButton @click="handleStatus(detail, 'ignored')" plain>忽略</ElButton>
          <ElButton @click="handleWhitelist(detail)" type="success" plain>加入白名单</ElButton>
          <ElButton @click="handleAnalyze(detail)" type="primary" :loading="analyzing">AI 研判</ElButton>
        </div>

        <!-- AI 研判结果 -->
        <div v-if="aiResult" class="ai-result">
          <ElDivider content-position="left">AI 研判结果</ElDivider>
          <ElDescriptions :column="1" border>
            <ElDescriptionsItem label="风险评级">{{ aiResult.risk_assessment || '—' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="分析说明">{{ aiResult.explanation || '—' }}</ElDescriptionsItem>
            <ElDescriptionsItem label="处置建议">{{ aiResult.recommendations || '—' }}</ElDescriptionsItem>
          </ElDescriptions>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, h, computed, onMounted } from 'vue'
  import { ElMessage, ElMessageBox, ElTag } from 'element-plus'
  import { useTable } from '@/composables/useTable'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import {
    getBrowsingEvents,
    getBrowsingEvent,
    updateBrowsingEvent,
    whitelistBrowsingEvent,
    analyzeBrowsingEvent,
    getBrowsingStats
  } from '@/api/browsing'
  import type { SearchFormItem } from '@/types'

  // 统计
  const stats = ref<any>({})
  const loadStats = async () => {
    try {
      const res = await getBrowsingStats()
      stats.value = res?.data || {}
    } catch (e) {
      console.error('加载统计失败', e)
    }
  }

  // 刷新数据：同时刷新统计卡片 + 表格
  const handleRefreshAll = async () => {
    await loadStats()
    refresh()
  }
  const topRule = computed(() => {
    const r = stats.value.today_by_rule || {}
    const entries = Object.entries(r) as [string, number][]
    if (!entries.length) return ''
    entries.sort((a, b) => b[1] - a[1])
    return `${entries[0][0]} (${entries[0][1]})`
  })

  // 表格
  const tableApi = useTable<any>({
    core: {
      apiFn: getBrowsingEvents,
      apiParams: { ip: '', domain: '', severity: '', status: '' },
      columnsFactory: () => [
        { prop: 'created_at', label: '检测时间', align: 'center', width: 160,
          formatter: (r: any) => (r.created_at || '').replace('T', ' ').slice(0, 19) },
        { prop: 'ip', label: '源 IP', align: 'center', width: 130 },
        { prop: 'domain', label: '目标域名', align: 'left', showOverflowTooltip: true,
          formatter: (r: any) => r.domain || '--' },
        { prop: 'severity', label: '等级', align: 'center', width: 90,
          formatter: (r: any) => h(ElTag, { type: severityType(r.severity) }, () => r.severity) },
        { prop: 'score', label: '分值', align: 'center', width: 80 },
        { prop: 'rule_hits', label: '命中规则', align: 'center', width: 140,
          formatter: (r: any) => (r.rule_hits || []).map((h: any) => h.rule).join(',') || '--' },
        { prop: 'source_count', label: '记录数', align: 'center', width: 80 },
        { prop: 'status', label: '状态', align: 'center', width: 100,
          formatter: (r: any) => h(ElTag, { type: statusType(r.status) }, () => statusText(r.status)) },
        { prop: 'operation', label: '操作', align: 'center', width: 120, fixed: 'right',
          formatter: (r: any) =>
            h('div', { class: 'operation-column-container' }, [
              h(ArtButtonTable, { type: 'edit', style: 'margin-right:8px;', onClick: () => showDetail(r) })
            ]) }
      ]
    }
  })

  const {
    data, loading, columns, columnChecks, pagination,
    searchParams, getDataByPage, resetSearchParams,
    handleSizeChange, handleCurrentChange, refresh
  } = tableApi as any

  // 搜索项
  const searchItems: SearchFormItem[] = [
    { label: '源 IP', key: 'ip', type: 'input', span: 6, clearable: true, placeholder: '请输入 IP' },
    { label: '目标域名', key: 'domain', type: 'input', span: 6, clearable: true, placeholder: '请输入域名' },
    {
      label: '等级', key: 'severity', type: 'select', span: 6, clearable: true, placeholder: '选择等级',
      options: () => [
        { label: '严重', value: 'critical' }, { label: '高危', value: 'high' },
        { label: '中危', value: 'medium' }, { label: '低危', value: 'low' }
      ]
    },
    {
      label: '状态', key: 'status', type: 'select', span: 6, clearable: true, placeholder: '选择状态',
      options: () => [
        { label: '新建', value: 'new' }, { label: '已确认', value: 'confirmed' },
        { label: '误报', value: 'false_positive' }, { label: '已解决', value: 'resolved' },
        { label: '已忽略', value: 'ignored' }
      ]
    }
  ]

  // 详情
  const detailVisible = ref(false)
  const detail = ref<any>(null)
  const showDetail = async (row: any) => {
    aiResult.value = null
    try {
      const res = await getBrowsingEvent(row.id)
      detail.value = res?.data || row
      detailVisible.value = true
    } catch (e) {
      console.error(e)
    }
  }

  // 处置
  const handleStatus = async (d: any, status: string) => {
    try {
      const res = await updateBrowsingEvent(d.id, { status })
      if (res.code === 200 || res.code === 201) {
        ElMessage.success('已更新')
        detailVisible.value = false
        refresh()
        loadStats()
      } else {
        ElMessage.error(res.message || '操作失败')
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleWhitelist = (d: any) => {
    ElMessageBox.confirm(`确定将 ${d.domain} 加入白名单吗？`, '加入白名单', { type: 'warning' })
      .then(async () => {
        try {
          const res = await whitelistBrowsingEvent(d.id)
          if (res.code === 200 || res.code === 201) {
            ElMessage.success('已加入白名单')
            detailVisible.value = false
            refresh()
          } else {
            ElMessage.error(res.message || '操作失败')
          }
        } catch (e) {
          console.error(e)
        }
      })
      .catch(() => {})
  }

  // AI 研判
  const analyzing = ref(false)
  const aiResult = ref<any>(null)
  const handleAnalyze = async (d: any) => {
    analyzing.value = true
    aiResult.value = null
    try {
      const res = await analyzeBrowsingEvent(d.id)
      if (res.code === 200 || res.code === 201) {
        aiResult.value = res.data
        ElMessage.success('AI 研判完成')
      } else {
        ElMessage.error(res.message || '研判失败')
      }
    } catch (e) {
      console.error(e)
      ElMessage.error('研判失败，请稍后重试')
    } finally {
      analyzing.value = false
    }
  }

  // 工具函数
  const severityType = (s: string) => {
    if (s === 'critical') return 'danger'
    if (s === 'high') return 'danger'
    if (s === 'medium') return 'warning'
    return 'info'
  }
  const statusType = (s: string) => {
    if (s === 'new') return 'danger'
    if (s === 'confirmed') return 'warning'
    if (s === 'resolved') return 'success'
    return 'info'
  }
  const statusText = (s: string) => {
    const m: any = { new: '新建', confirmed: '已确认', false_positive: '误报', resolved: '已解决', ignored: '已忽略' }
    return m[s] || s
  }

  onMounted(() => {
    loadStats()
  })
</script>

<style lang="scss" scoped>
  .browsing-event-page {
    display: flex;
    flex-direction: column;
    gap: 12px;

    .stat-row {
      margin-bottom: 0;
    }

    .stat-card {
      text-align: center;
      :deep(.el-card__body) {
        padding: 16px;
      }
      .stat-label {
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
      .stat-value {
        font-size: 28px;
        font-weight: 700;
        margin-top: 4px;
        color: var(--el-color-primary);
      }
      &.critical .stat-value {
        color: var(--el-color-danger);
      }
      &.warning .stat-value {
        color: var(--el-color-warning);
      }
      .stat-rule {
        font-size: 16px;
      }
    }

    .rule-hit {
      margin-bottom: 6px;
      .rule-weight {
        margin: 0 6px;
        font-weight: 700;
        color: var(--el-color-danger);
      }
      .rule-detail {
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
    }

    .detail-actions {
      margin-top: 20px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .ai-result {
      margin-top: 16px;
    }
  }
</style>
