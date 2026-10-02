<!--
  暴露面分析页（OH-UI.9，S2 暴露面归位前端消费）

  三区块：
    ① 外网 IP→内网反查  （lookup，按 WAN IP 反查所有映射）
    ② 全量 NAT 规则      （rules，暴露面分析的核心数据源）
    ③ 资产对外暴露面映射  （assets/{id}/mapping，资产详情页配套）

  数据源：src/frontend/src/api/exposure.ts（三个端点 client）
  设计依据：docs/design/2026-09-30-资产管理AI能力建设-UI缺口补遗.md §三.E + 暴露面分析
-->
<template>
  <div class="exposure-page art-full-height">
    <!-- ============ ① 外网 IP→内网反查 ============ -->
    <ElCard shadow="never" class="art-table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">外网 IP → 内网资产反查</span>
          <span class="card-hint">攻击溯源 / S2 暴露面归位入口</span>
        </div>
      </template>

      <ElForm :inline="true" @submit.prevent="onLookup" class="lookup-form">
        <ElFormItem label="WAN IP">
          <ElInput
            v-model="lookupForm.wan_ip"
            placeholder="如 175.11.169.102"
            style="width: 240px"
            clearable
            @keyup.enter="onLookup"
          />
        </ElFormItem>
        <ElFormItem label="只看启用">
          <ElSwitch v-model="activeOnly" />
        </ElFormItem>
        <ElButton type="primary" :loading="lookupLoading" @click="onLookup">反查</ElButton>
        <ElButton text @click="resetLookup">清空</ElButton>
      </ElForm>

      <div v-if="lookupSummary.total != null" class="lookup-coverage">
        <span class="coverage-label">总规则</span>
        <span class="coverage-value">{{ lookupSummary.total }}</span>
        <span class="coverage-divider">|</span>
        <span class="coverage-label" style="color: var(--el-color-success)">已定位</span>
        <span class="coverage-value">{{ lookupSummary.located }}</span>
        <span class="coverage-divider">|</span>
        <span class="coverage-label" style="color: var(--el-color-warning)">未定位</span>
        <span class="coverage-value">{{ lookupSummary.unlocated }}</span>
        <span v-if="lookupSummary.wan_ip" class="coverage-wanip">
          公网入口 IP：<strong>{{ lookupSummary.wan_ip }}</strong>
        </span>
      </div>

      <ArtTable
        :loading="lookupLoading"
        :data="lookupData"
        :columns="lookupColumns"
        :pagination="false"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 12 }"
        empty-text="输入 WAN IP 反查，或暂未配置 NAT"
      />
    </ElCard>

    <!-- ============ ② 全量 NAT 规则 ============ -->
    <ElCard shadow="never" class="art-table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">全量 NAT 端口映射规则</span>
          <span class="card-hint">暴露面分析核心数据源</span>
        </div>
      </template>

      <ArtSearchBar
        v-model="searchParams"
        :items="searchItems"
        @search="refresh"
        @reset="resetSearchParams"
      />

      <ArtTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 12 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- ============ ③ 资产对外暴露面映射 ============ -->
    <ElCard shadow="never" class="art-table-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">资产对外暴露面映射</span>
          <span class="card-hint">"这台资产哪些端口暴露在公网"</span>
        </div>
      </template>

      <ElForm :inline="true" @submit.prevent="onAssetLookup" class="lookup-form">
        <ElFormItem label="资产 ID">
          <ElInput
            v-model="assetLookupForm.asset_id"
            placeholder="如 c661cc77-..."
            style="width: 360px"
            clearable
            @keyup.enter="onAssetLookup"
          />
        </ElFormItem>
        <ElButton type="primary" :loading="assetLookupLoading" @click="onAssetLookup"
          >查询</ElButton
        >
        <ElButton text @click="resetAssetLookup">清空</ElButton>
      </ElForm>

      <div v-if="assetLookupResult.asset" class="asset-summary">
        <div class="asset-summary-row">
          <span class="summary-label">资产</span>
          <span class="summary-value"
            >{{ assetLookupResult.asset.name }}（{{ assetLookupResult.asset.asset_ip }}）</span
          >
        </div>
        <div class="asset-summary-row">
          <span class="summary-label">是否对外暴露</span>
          <ElTag v-if="assetLookupResult.exposed" type="success" size="small">已暴露</ElTag>
          <ElTag v-else type="info" size="small">未暴露</ElTag>
          <span class="summary-divider">|</span>
          <span class="summary-label">映射数</span>
          <span class="summary-value">{{ assetLookupResult.exposure_count }}</span>
        </div>
      </div>

      <ArtTable
        :loading="assetLookupLoading"
        :data="assetLookupResult.items"
        :columns="assetLookupColumns"
        :pagination="false"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 12 }"
        empty-text="输入资产 ID 查询"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted } from 'vue'
  import { ElMessage, type FormInstance } from 'element-plus'
  import {
    exposureLookup as apiExposureLookup,
    exposureRules as apiExposureRules,
    assetExposureMapping as apiAssetExposureMapping
  } from '@/api/exposure'
  import { useTable } from '@/composables/useTable'
  import { getAssetList } from '@/api/asset'

  defineOptions({ name: 'AssetExposurePage' })

  // ============ ① 外网 IP→内网反查 ============
  const lookupForm = reactive({ wan_ip: '' })
  const activeOnly = ref(true)
  const lookupLoading = ref(false)
  const lookupData = ref<any[]>([])
  const lookupSummary = ref<{
    total: number | null
    located: number
    unlocated: number
    wan_ip: string
  }>({
    total: null,
    located: 0,
    unlocated: 0,
    wan_ip: ''
  })

  async function onLookup() {
    if (!lookupForm.wan_ip.trim()) {
      ElMessage.warning('请输入 WAN IP')
      return
    }
    lookupLoading.value = true
    try {
      const r: any = await apiExposureLookup({
        wan_ip: lookupForm.wan_ip.trim(),
        enabled_only: activeOnly.value
      })
      const d = r?.data || {}
      lookupData.value = d.items || []
      lookupSummary.value = {
        total: d.total ?? 0,
        located: d.located ?? 0,
        unlocated: d.unlocated ?? 0,
        wan_ip: d.wan_ip || lookupForm.wan_ip.trim()
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '反查失败')
      lookupData.value = []
      lookupSummary.value = { total: null, located: 0, unlocated: 0, wan_ip: '' }
    } finally {
      lookupLoading.value = false
    }
  }

  function resetLookup() {
    lookupForm.wan_ip = ''
    activeOnly.value = true
    lookupData.value = []
    lookupSummary.value = { total: null, located: 0, unlocated: 0, wan_ip: '' }
  }

  const lookupColumns = computed(() => [
    { prop: 'wan_port', label: '外网端口', align: 'center', minWidth: 100 },
    { prop: 'protocol', label: '协议', align: 'center', minWidth: 80 },
    { prop: 'internal_ip', label: '内网 IP', align: 'center', minWidth: 140 },
    { prop: 'internal_port', label: '内网端口', align: 'center', minWidth: 100 },
    {
      prop: 'rule_name',
      label: '规则名',
      align: 'center',
      minWidth: 140,
      showOverflowTooltip: true
    },
    {
      prop: 'asset',
      label: '关联资产',
      align: 'center',
      minWidth: 200,
      showOverflowTooltip: true,
      formatter: (row: any) => {
        const a = row.asset
        if (!a) return '—（未定位）'
      }
    },
    {
      prop: 'last_seen_at',
      label: '上次观测',
      align: 'center',
      minWidth: 170,
      formatter: (row: any) =>
        row.last_seen_at
          ? new Date(row.last_seen_at).toLocaleString('zh-CN', { hour12: false })
          : '—'
    }
  ])

  // ============ ② 全量 NAT 规则（useTable） ============
  const searchItems = [
    {
      label: '内网 IP',
      key: 'wan_ip',
      value: '',
      type: 'input',
      placeholder: '过滤内网目标 IP',
      labelWidth: '40px'
    }
  ]

  const {
    columns,
    data,
    loading,
    pagination,
    searchParams,
    getData: getDataByPage,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshAll: refreshRules
  } = useTable<any>({
    core: {
      apiFn: apiExposureRules as any,
      apiParams: {
        page: 1,
        page_size: 20
      },
      paginationKey: { current: 'page', size: 'page_size' },
      columnsFactory: () => [
        {
          prop: 'wan_ip',
          label: '公网入口',
          align: 'center',
          minWidth: 140,
          showOverflowTooltip: true
        },
        { prop: 'wan_port', label: '外网端口', align: 'center', minWidth: 100 },
        { prop: 'protocol', label: '协议', align: 'center', minWidth: 80 },
        { prop: 'internal_ip', label: '内网 IP', align: 'center', minWidth: 140 },
        { prop: 'internal_port', label: '内网端口', align: 'center', minWidth: 100 },
        {
          prop: 'rule_name',
          label: '规则名',
          align: 'center',
          minWidth: 140,
          showOverflowTooltip: true
        },
        {
          prop: 'enabled',
          label: '启用',
          align: 'center',
          minWidth: 80,
          formatter: (row: any) => (row.enabled ? '是' : '否')
        },
        {
          prop: 'last_seen_at',
          label: '上次观测',
          align: 'center',
          minWidth: 170,
          formatter: (row: any) =>
            row.last_seen_at
              ? new Date(row.last_seen_at).toLocaleString('zh-CN', { hour12: false })
              : '—'
        }
      ]
    }
  })

  // 把 useTable 的 wan_ip 搜索参数映射到 rules API 参数 internal_ip（搜索项命名为 wan_ip 仅为 UI 直觉）
  function refresh() {
    const ip = (searchParams.value as any).wan_ip?.trim()
    // useTable 调 apiFn 时把 searchParams 平摊到 params；
    // 这里通过一次性把 wan_ip 改名为 internal_ip 再传。
    if (ip) (searchParams.value as any).internal_ip = ip
    getDataByPage()
  }
  function reset() {
    resetSearchParams()
  }

  // 覆盖 useTable 默认 refresh（点一次内容展开时 wan_ip → internal_ip 改名）
  ;(searchParams.value as any).wan_ip = ''

  // ============ ③ 资产对外暴露面映射 ============
  const assetLookupForm = reactive({ asset_id: '' })
  const assetLookupLoading = ref(false)
  const assetLookupResult = ref<{
    asset: any | null
    exposed: boolean
    exposure_count: number
    items: any[]
  }>({
    asset: null,
    exposed: false,
    exposure_count: 0,
    items: []
  })

  async function onAssetLookup() {
    if (!assetLookupForm.asset_id.trim()) {
      ElMessage.warning('请输入资产 ID')
      return
    }
    assetLookupLoading.value = true
    try {
      const r: any = await apiAssetExposureMapping(assetLookupForm.asset_id.trim(), {
        enabled_only: true
      })
      const d = r?.data || {}
      assetLookupResult.value = {
        asset: d.asset || null,
        exposed: d.exposed ?? false,
        exposure_count: d.exposure_count ?? 0,
        items: d.items || []
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '查询失败')
      assetLookupResult.value = { asset: null, exposed: false, exposure_count: 0, items: [] }
    } finally {
      assetLookupLoading.value = false
    }
  }

  function resetAssetLookup() {
    assetLookupForm.asset_id = ''
    assetLookupResult.value = { asset: null, exposed: false, exposure_count: 0, items: [] }
  }

  const assetLookupColumns = [
    {
      prop: 'wan_ip',
      label: '公网入口',
      align: 'center',
      minWidth: 140,
      showOverflowTooltip: true
    },
    { prop: 'wan_port', label: '外网端口', align: 'center', minWidth: 100 },
    { prop: 'protocol', label: '协议', align: 'center', minWidth: 80 },
    { prop: 'internal_port', label: '内网端口', align: 'center', minWidth: 100 },
    {
      prop: 'rule_name',
      label: '规则名',
      align: 'center',
      minWidth: 140,
      showOverflowTooltip: true
    },
    {
      prop: 'enabled',
      label: '启用',
      align: 'center',
      minWidth: 80,
      formatter: (row: any) => (row.enabled ? '是' : '否')
    },
    {
      prop: 'last_seen_at',
      label: '上次观测',
      align: 'center',
      minWidth: 170,
      formatter: (row: any) =>
        row.last_seen_at
          ? new Date(row.last_seen_at).toLocaleString('zh-CN', { hour12: false })
          : '—'
    }
  ]

  onMounted(() => {
    refreshRules()
  })
</script>

<style lang="scss" scoped>
  .exposure-page {
    display: flex;
    flex-direction: column;
    gap: 12px;

    .card-header {
      display: flex;
      align-items: baseline;
      gap: 12px;
    }
    .card-title {
      font-weight: 600;
      font-size: 15px;
    }
    .card-hint {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }

    .lookup-form {
      margin-bottom: 12px;
    }

    .lookup-coverage {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .coverage-label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
    .coverage-value {
      font-weight: 600;
      font-size: 14px;
    }
    .coverage-divider {
      color: var(--el-border-color);
    }
    .coverage-wanip {
      margin-left: auto;
      font-size: 13px;
    }

    .asset-summary {
      padding: 12px 16px;
      background: var(--el-fill-color-light);
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .asset-summary-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 4px 0;
    }
    .summary-label {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      min-width: 80px;
    }
    .summary-value {
      font-size: 14px;
      font-weight: 500;
    }
    .summary-divider {
      color: var(--el-border-color);
      margin: 0 8px;
    }
  }
</style>
