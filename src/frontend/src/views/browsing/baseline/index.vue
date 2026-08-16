<template>
  <div class="browsing-baseline-page art-full-height" id="table-full-screen">
    <!-- 搜索栏（ip 精确 / domain 模糊，空值忽略过滤） -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="resetSearchParams"
      @search="getDataByPage"
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
  import { useTable } from '@/composables/useTable'
  import { getBrowsingBaseline } from '@/api/browsing'
  import type { SearchFormItem } from '@/types'

  // 表格（服务端分页，仿 event 页范式：searchParams 由 useTable 提供，
  // ArtSearchBar v-model 双向同步，查询走 getDataByPage 以当前筛选请求）
  // 基线为系统维护只读数据，无增删操作
  const tableApi = useTable<any>({
    core: {
      apiFn: getBrowsingBaseline,
      apiParams: { ip: '', domain: '' },
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
    searchParams, getDataByPage, resetSearchParams,
    handleSizeChange, handleCurrentChange, refresh
  } = tableApi as any

  const searchItems: SearchFormItem[] = [
    { label: '内网 IP', key: 'ip', type: 'input', span: 6, clearable: true, placeholder: '如 192.168.0.8' },
    { label: '域名', key: 'domain', type: 'input', span: 6, clearable: true, placeholder: '域名关键字' }
  ]
</script>

<style lang="scss" scoped>
  .browsing-baseline-page {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
</style>
