<!--
  配置变更审计（X1E-11 配置中心）

  设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §6
-->
<template>
  <div class="config-logs-page art-full-height">
    <ElCard shadow="never" class="art-table-card">
      <!-- 工具栏 -->
      <div class="toolbar">
        <ElSelect v-model="filterTarget" placeholder="全部对象" clearable style="width: 150px" @change="getData">
          <ElOption label="全部对象" value="" />
          <ElOption label="数据源" value="data_source" />
          <ElOption label="系统配置" value="system_config" />
        </ElSelect>
        <ElSelect v-model="filterAction" placeholder="全部动作" clearable style="width: 150px" @change="getData">
          <ElOption label="全部动作" value="" />
          <ElOption label="新建" value="create" />
          <ElOption label="更新" value="update" />
          <ElOption label="删除" value="delete" />
          <ElOption label="启用" value="enable" />
          <ElOption label="停用" value="disable" />
          <ElOption label="设默认" value="set_default" />
          <ElOption label="连接测试" value="test" />
        </ElSelect>
        <ElInput
          v-model="searchKeyword"
          placeholder="操作人 IP / 配置键"
          style="width: 240px"
          clearable
          @keyup.enter="getData"
          @clear="getData"
        >
          <template #append>
            <ElButton @click="getData">搜索</ElButton>
          </template>
        </ElInput>
        <div class="grow-spacer" />
        <ElButton @click="exportCsv">导出 CSV</ElButton>
      </div>

      <!-- 表格 -->
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

      <div class="hint-block">
        审计记录只增不改不删；敏感字段（密码/密钥）只记录「已变更」事实，
        <b>永不记录明文或密文</b>。
      </div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, h, resolveComponent, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfigChangeLogs } from '@/api/configChangeLog'

defineOptions({ name: 'ConfigLogsPage' })

const filterTarget = ref<string>('')
const filterAction = ref<string>('')
const searchKeyword = ref<string>('')
const loading = ref(false)
const data = ref<Api.ConfigChangeLog.Item[]>([])
const pagination = reactive({ current: 1, size: 20, total: 0, sizeChange: handleSizeChange, currentChange: handleCurrentChange })

const actionLabels: Record<string, { label: string; type: 'primary' | 'success' | 'info' | 'warning' | 'danger' }> = {
  create: { label: '新建', type: 'success' },
  update: { label: '更新', type: 'primary' },
  delete: { label: '删除', type: 'danger' },
  enable: { label: '启用', type: 'success' },
  disable: { label: '停用', type: 'info' },
  set_default: { label: '设默认', type: 'warning' },
  test: { label: '测试', type: 'info' },
}

const columns = ref<any[]>([
  {
    prop: 'created_at',
    label: '时间',
    width: 160,
    formatter: (row: Api.ConfigChangeLog.Item) =>
      h('span', { class: 'code muted' }, row.created_at || '--'),
  },
  { prop: 'operator_id', label: '操作人', width: 100 },
  {
    prop: 'action',
    label: '动作',
    width: 100,
    formatter: (row: Api.ConfigChangeLog.Item) => {
      const meta = actionLabels[row.action] || { label: row.action, type: 'info' as const }
      return h(
        resolveComponent('ElTag'),
        { size: 'small', type: meta.type, effect: 'plain' },
        { default: () => meta.label }
      )
    },
  },
  {
    prop: 'target_key',
    label: '对象',
    width: 200,
    formatter: (row: Api.ConfigChangeLog.Item) =>
      h('span', { class: 'code' }, `${row.target_type} / ${row.target_key}`),
  },
  {
    prop: 'changes',
    label: '变更内容',
    formatter: (row: Api.ConfigChangeLog.Item) => {
      if (row.action === 'test') {
        return h('span', { class: 'muted' }, row.after_value || '--')
      }
      if (!row.changed_fields || row.changed_fields.length === 0) {
        return h('span', { class: 'muted' }, '--')
      }
      return h(
        'div',
        { class: 'changes' },
        row.changed_fields.map((f) =>
          h('span', { class: 'chip' }, f)
        )
      )
    },
  },
  {
    prop: 'operator_ip',
    label: '来源 IP',
    width: 120,
    formatter: (row: Api.ConfigChangeLog.Item) =>
      h('span', { class: 'code muted' }, row.operator_ip || '--'),
  },
])

async function getData() {
  loading.value = true
  try {
    const res: any = await getConfigChangeLogs({
      page: pagination.current,
      page_size: pagination.size,
      target_type: (filterTarget.value || undefined) as any,
      action: (filterAction.value || undefined) as any,
      search: searchKeyword.value || undefined,
    })
    const payload = res?.data || res
    data.value = payload?.items || []
    pagination.total = payload?.total || 0
  } catch (e) {
    data.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

function handleSizeChange(size: number) {
  pagination.size = size
  pagination.current = 1
  getData()
}
function handleCurrentChange(page: number) {
  pagination.current = page
  getData()
}

function exportCsv() {
  // 简化为导出当前页
  const headers = ['时间', '操作人', '动作', '对象', '变更字段', '来源IP']
  const rows = data.value.map((d) => [
    d.created_at || '',
    String(d.operator_id || ''),
    d.action,
    `${d.target_type}/${d.target_key}`,
    (d.changed_fields || []).join(','),
    d.operator_ip || '',
  ])
  const csv = [headers, ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeef' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `config-change-logs-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出当前页')
}

onMounted(getData)
</script>

<style scoped lang="scss">
.config-logs-page {
  padding: 16px;
  .toolbar {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 14px;
  }
  .grow-spacer {
    flex: 1;
  }
  .code {
    font-family: ui-monospace, Menlo, monospace;
    color: #185fa5;
  }
  .muted {
    color: #888780;
  }
  .changes {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chip {
    background: #f1efe8;
    border: 1px solid #d3d1c7;
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 11px;
    color: #5f5e5a;
    font-family: ui-monospace, Menlo, monospace;
  }
  .hint-block {
    margin-top: 12px;
    padding: 10px 14px;
    background: #fafaf8;
    border-radius: 6px;
    font-size: 12px;
    color: #5f5e5a;
  }
}
</style>