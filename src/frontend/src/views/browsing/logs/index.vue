<template>
  <div class="browsing-logs-page art-full-height" id="table-full-screen">
    <!-- 搜索栏（含查询/重置按钮） -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="handleReset"
      @search="handleSearch"
    />

    <ElCard shadow="never" class="art-table-card">
      <ArtTableHeader
        v-model:columns="columnChecks"
        title="行为日志"
        @refresh="handleSearch"
      >
        <template #right>
          <span class="logs-meta" v-if="logs.length">
            命中 {{ logs.length }} 条<template v-if="logs.length >= currentLimit">（已达上限，建议缩小范围）</template>
          </span>
        </template>
      </ArtTableHeader>

      <ArtTable
        :loading="loading"
        :data="pagedLogs"
        :columns="columns"
        :pagination="clientPagination"
        table-layout="fixed"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, h } from 'vue'
  import { ElMessage, ElTag } from 'element-plus'
  import { useTableColumns } from '@/hooks/core/useTableColumns'
  import { queryBrowsingLogs } from '@/api/browsing'
  import type { SearchFormItem } from '@/types'

  const loading = ref(false)
  const logs = ref<any[]>([])

  // Loki 单次查询上限（随时间范围自适应）
  const currentLimit = ref(500)

  // 列配置（ArtTable 体系，与基线/黑名单页风格一致）
  const { columns, columnChecks } = useTableColumns<any>(() => [
    { prop: 'ts', label: '时间', align: 'center', width: 170,
      formatter: (r: any) => (r.ts || '').replace('T', ' ').slice(0, 19) },
    { prop: 'ip', label: '源 IP', align: 'center', width: 130 },
    { prop: 'action', label: '类型', align: 'center', width: 90,
      formatter: (r: any) =>
        h(ElTag, { type: r.action === 'url' ? 'primary' : 'success', size: 'small' },
          () => (r.action === 'url' ? '网址' : r.action === 'app' ? '应用' : '—')) },
    { prop: 'domain', label: '域名/应用', align: 'left', width: 240, showOverflowTooltip: true,
      formatter: (r: any) => r.domain || r.apptype || '—' },
    { prop: 'body', label: '原始日志', align: 'left', showOverflowTooltip: true }
  ])

  // 客户端分页（Loki 一次性拉回后前端切片，适配 ArtTable 分页协议）
  const currentPage = ref(1)
  const pageSize = ref(20)
  const pagedLogs = computed(() => {
    const start = (currentPage.value - 1) * pageSize.value
    return logs.value.slice(start, start + pageSize.value)
  })
  const clientPagination = computed(() => ({
    current: currentPage.value,
    size: pageSize.value,
    total: logs.value.length
  }))
  const handleSizeChange = (size: number) => {
    pageSize.value = size
    currentPage.value = 1
  }
  const handleCurrentChange = (page: number) => {
    currentPage.value = page
  }

  const searchParams = reactive({
    ip: '',
    domain: '',
    apptype: '',
    keyword: '',
    hours: 1
  })

  // 根据时间范围自适应返回条数上限（Loki 单次查询不宜过大）
  const limitByHours = (hours: number) => {
    if (hours <= 1) return 500
    if (hours <= 6) return 1000
    if (hours <= 24) return 2000
    return 5000
  }

  const searchItems: SearchFormItem[] = [
    { label: '源 IP', key: 'ip', type: 'input', span: 6, clearable: true, placeholder: '如 192.168.0.8' },
    { label: '域名', key: 'domain', type: 'input', span: 6, clearable: true, placeholder: '域名关键字' },
    {
      label: '应用类型', key: 'apptype', type: 'select', span: 6, clearable: true, placeholder: '选择类型',
      options: [
        { label: '网络基础协议', value: '网络基础协议' },
        { label: '视频直播', value: '视频直播' },
        { label: '云服务', value: '云服务' },
        { label: '下载工具', value: '下载工具' },
        { label: '生活服务', value: '生活服务' },
        { label: '新闻资讯', value: '新闻资讯' },
        { label: '浏览器应用', value: '浏览器应用' },
        { label: '网络购物', value: '网络购物' },
        { label: 'IM', value: 'IM' },
        { label: '应用商店', value: '应用商店' },
        { label: '搜索引擎', value: '搜索引擎' },
        { label: '证券投资', value: '证券投资' },
        { label: '银行支付', value: '银行支付' }
      ]
    },
    { label: '关键字', key: 'keyword', type: 'input', span: 6, clearable: true, placeholder: '日志内容关键字' },
    {
      label: '时间范围', key: 'hours', type: 'select', span: 6, placeholder: '时间范围',
      options: [
        { label: '最近1小时', value: 1 },
        { label: '最近6小时', value: 6 },
        { label: '最近24小时', value: 24 },
        { label: '最近7天', value: 168 }
      ]
    }
  ]

  const handleSearch = async () => {
    loading.value = true
    try {
      const limit = limitByHours(searchParams.hours)
      currentLimit.value = limit
      const params: Record<string, any> = {
        ip: searchParams.ip || undefined,
        domain: searchParams.domain || undefined,
        apptype: searchParams.apptype || undefined,
        keyword: searchParams.keyword || undefined,
        limit
      }
      // 时间范围：按 hours 计算 start
      if (searchParams.hours) {
        const now = new Date()
        const start = new Date(now.getTime() - searchParams.hours * 3600 * 1000)
        params.start = start.toISOString()
        params.end = now.toISOString()
      }
      const res = await queryBrowsingLogs(params)
      if (res.code === 200 || res.code === 201) {
        logs.value = res.data?.logs || []
        currentPage.value = 1  // 查询后回到第一页
        if (!logs.value.length) {
          ElMessage.info('未查到日志，可尝试扩大时间范围')
        }
      } else {
        ElMessage.error(res.message || '查询失败')
      }
    } catch (e) {
      console.error(e)
      ElMessage.error('查询失败')
    } finally {
      loading.value = false
    }
  }

  const handleReset = () => {
    searchParams.ip = ''
    searchParams.domain = ''
    searchParams.apptype = ''
    searchParams.keyword = ''
  }

  // 初始加载
  handleSearch()
</script>

<style lang="scss" scoped>
  .browsing-logs-page {
    display: flex;
    flex-direction: column;

    .logs-meta {
      font-size: 12px;
      color: var(--el-text-color-secondary, #909399);
      margin-right: 8px;
    }
  }
</style>
