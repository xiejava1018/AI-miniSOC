<template>
  <div class="browsing-baseline-page art-full-height" id="table-full-screen">
    <!-- 搜索栏（ip 精确 / domain 模糊） -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="handleReset"
      @search="handleSearch"
    />

    <ElCard shadow="never" class="art-table-card">
      <ArtTableHeader v-model:columns="columnChecks" title="行为基线" @refresh="refresh" />

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        table-layout="fixed"
        :table-config="{ rowKey: 'ip' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { reactive } from 'vue'
  import { useTable } from '@/composables/useTable'
  import { getBrowsingBaseline } from '@/api/browsing'
  import type { SearchFormItem } from '@/types'

  // 筛选条件（空值传 undefined 忽略过滤，对齐后端 ip 精确 / domain ILIKE 语义）
  const searchParams = reactive({
    ip: '',
    domain: ''
  })

  const searchItems: SearchFormItem[] = [
    { label: '内网 IP', key: 'ip', type: 'input', span: 6, clearable: true, placeholder: '如 192.168.0.8' },
    { label: '域名', key: 'domain', type: 'input', span: 6, clearable: true, placeholder: '域名关键字' }
  ]

  // 表格（服务端分页，仿 blacklist 范式；基线为系统维护只读数据，无增删操作）
  const tableApi = useTable<any>({
    core: {
      apiFn: getBrowsingBaseline,
      apiParams: { ip: undefined, domain: undefined },
      columnsFactory: () => [
        { prop: 'ip', label: '内网 IP', align: 'left', showOverflowTooltip: true },
        { prop: 'domain', label: '域名', align: 'left', showOverflowTooltip: true },
        { prop: 'total_count', label: '累计访问次数', align: 'center', width: 120 },
        { prop: 'first_seen', label: '首次观测', align: 'center', width: 170,
          formatter: (r: any) => (r.first_seen || '').replace('T', ' ').slice(0, 19) },
        { prop: 'last_seen', label: '末次观测', align: 'center', width: 170,
          formatter: (r: any) => (r.last_seen || '').replace('T', ' ').slice(0, 19) }
      ]
    }
  })

  const {
    data, loading, columns, columnChecks, pagination,
    handleSizeChange, handleCurrentChange, refresh
  } = tableApi as any

  // 查询：以当前筛选条件刷新（空值 → undefined 忽略）
  const handleSearch = () => {
    refresh({ ip: searchParams.ip || undefined, domain: searchParams.domain || undefined })
  }

  // 重置：清空筛选并刷新全量
  const handleReset = () => {
    searchParams.ip = ''
    searchParams.domain = ''
    refresh({ ip: undefined, domain: undefined })
  }
</script>

<style lang="scss" scoped>
  .browsing-baseline-page {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
</style>
