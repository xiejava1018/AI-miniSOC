<template>
  <div class="asset-list-page art-full-height">
    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchState"
      :items="searchItems"
      @reset="resetSearch"
      @search="searchData"
    />

    <ElCard shadow="never" class="art-table-card">
      <!-- 表格头部 -->
      <ArtTableHeader
        :columnList="columnOptions"
        v-model:columns="columnChecks"
        @refresh="handleRefresh"
      >
        <template #left>
          <ElButton @click="showDialog('add')" v-ripple>添加资产</ElButton>
          <ElButton type="warning" @click="handleSyncWazuh" v-ripple>Wazuh同步</ElButton>
        </template>
      </ArtTableHeader>

      <!-- 表格 -->
      <ArtTable
        :data="tableData"
        :columns="columns"
        :pagination="paginationState"
        :loading="isLoading"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="onPageSizeChange"
        @pagination:current-change="onCurrentPageChange"
      />
    </ElCard>

    <!-- 新增/编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? '添加资产' : '编辑资产'"
      width="680px"
      align-center
      :close-on-click-modal="false"
    >
      <ElForm ref="formRef" :model="formData" :rules="computedRules" label-width="90px">
        <!-- 第一档：核心识别 -->
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="资产名称" prop="name">
              <ElInput v-model="formData.name" placeholder="请输入资产名称" />
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="IP地址" prop="asset_ip">
              <ElInput
                v-model="formData.asset_ip"
                :disabled="dialogType === 'edit'"
                placeholder="请输入IP地址"
              />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <!-- 第二档：业务分类（决定告警/事件处置优先级） -->
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="资产类型" prop="asset_type">
              <ElSelect v-model="formData.asset_type" placeholder="请选择资产类型" style="width: 100%">
                <ElOption
                  v-for="opt in assetTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="重要性" prop="criticality">
              <ElSelect v-model="formData.criticality" placeholder="请选择重要性" style="width: 100%">
                <ElOption
                  v-for="opt in criticalityOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>

        <!-- 第三档：网络位置 + 状态（决定应急响应） -->
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="网络区域" prop="network_zone">
              <ElSelect v-model="formData.network_zone" placeholder="请选择网络区域" style="width: 100%">
                <ElOption
                  v-for="opt in networkZoneOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="状态" prop="asset_status">
              <ElSelect v-model="formData.asset_status" placeholder="请选择状态" style="width: 100%">
                <ElOption
                  v-for="opt in assetStatusOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>

        <!-- 第四档：管理归属 -->
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="负责人" prop="owner">
              <ElInput v-model="formData.owner" placeholder="请输入负责人" />
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="业务单元" prop="business_unit">
              <ElInput v-model="formData.business_unit" placeholder="请输入业务单元" />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <!-- 第五档：技术细节（次要识别，编辑时常不变） -->
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="网络段" prop="network_segment">
              <ElInput v-model="formData.network_segment" placeholder="默认: default" />
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="MAC地址" prop="mac_address">
              <ElInput
                v-model="formData.mac_address"
                :disabled="dialogType === 'edit'"
                placeholder="请输入MAC地址"
              />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <!-- 备注 -->
        <ElRow>
          <ElCol :span="24">
            <ElFormItem label="描述" prop="asset_description">
              <ElInput
                v-model="formData.asset_description"
                type="textarea"
                :rows="3"
                placeholder="请输入资产描述"
              />
            </ElFormItem>
          </ElCol>
        </ElRow>
      </ElForm>

      <template #footer>
        <div class="dialog-footer">
          <ElButton @click="dialogVisible = false">取 消</ElButton>
          <ElButton type="primary" @click="handleSubmit">确 定</ElButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, nextTick, computed, h, resolveComponent, onMounted } from 'vue'
  import { useRouter } from 'vue-router'
  import {
    getAssetList,
    addAsset,
    updateAsset,
    deleteAsset as apiDeleteAsset,
    syncFromWazuh
  } from '@/api/asset'
  import { useDictStore } from '@/store/modules/dict'
  import { FormInstance } from 'element-plus'
  import { ElMessageBox, ElMessage } from 'element-plus'
  import { useTable } from '@/composables/useTable'
  import { SearchFormItem } from '@/types'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'

  const router = useRouter()
  const dictStore = useDictStore()

  // 状态变量
  const dialogType = ref('add')
  const dialogVisible = ref(false)

  // 字典派生
  const assetTypeLabelMap = computed(() => dictStore.getLabelMap('asset_type'))
  const assetTypeColorMap = computed(() => dictStore.getColorMap('asset_type'))
  const criticalityLabelMap = computed(() => dictStore.getLabelMap('asset_criticality'))
  const criticalityColorMap = computed(() => dictStore.getColorMap('asset_criticality'))
  const statusLabelMap = computed(() => dictStore.getLabelMap('asset_status'))
  const statusColorMap = computed(() => dictStore.getColorMap('asset_status'))
  const networkZoneLabelMap = computed(() => dictStore.getLabelMap('network_zone'))
  const networkZoneColorMap = computed(() => dictStore.getColorMap('network_zone'))
  const assetTypeOptions = computed(() => dictStore.getOptions('asset_type'))
  const criticalityOptions = computed(() => dictStore.getOptions('asset_criticality'))
  const assetStatusOptions = computed(() => dictStore.getOptions('asset_status'))
  const networkZoneOptions = computed(() => dictStore.getOptions('network_zone'))

  // useTable
  const tableApi = useTable<any>({
    core: {
      apiFn: getAssetList,
      apiParams: {
        asset_ip: '',
        name: '',
        asset_type: '',
        criticality: '',
        asset_status: '',
        network_zone: ''
      },
      columnsFactory: () => [
        {
          prop: 'name',
          label: '资产名称',
          align: 'center',
          minWidth: 140,
          formatter: (row: any) =>
            h(
              'span',
              {
                style: 'cursor: pointer; color: var(--el-color-primary);',
                onClick: () => handleViewDetail(row)
              },
              row.name || '--'
            )
        },
        {
          prop: 'asset_ip',
          label: 'IP地址',
          align: 'center',
          minWidth: 140,
          formatter: (row: any) => row.asset_ip || '--'
        },
        {
          prop: 'mac_address',
          label: 'MAC地址',
          align: 'center',
          minWidth: 160,
          formatter: (row: any) => row.mac_address || '--'
        },
        {
          prop: 'asset_type',
          label: '资产类型',
          align: 'center',
          width: 100,
          formatter: (row: any) =>
            h(
              resolveComponent('ElTag'),
              { type: (assetTypeColorMap.value[row.asset_type] as any) || 'info', effect: 'light' },
              { default: () => assetTypeLabelMap.value[row.asset_type] || row.asset_type || '--' }
            )
        },
        {
          prop: 'criticality',
          label: '重要性',
          align: 'center',
          width: 80,
          formatter: (row: any) => {
            const label = criticalityLabelMap.value[row.criticality]
            return label
              ? h(
                  resolveComponent('ElTag'),
                  { type: (criticalityColorMap.value[row.criticality] as any) || 'info', effect: 'light' },
                  { default: () => label }
                )
              : '--'
          }
        },
        {
          prop: 'network_zone',
          label: '网络区域',
          align: 'center',
          width: 100,
          formatter: (row: any) => {
            const label = networkZoneLabelMap.value[row.network_zone]
            return label
              ? h(
                  resolveComponent('ElTag'),
                  { type: (networkZoneColorMap.value[row.network_zone] as any) || 'info', effect: 'light' },
                  { default: () => label }
                )
              : '--'
          }
        },
        {
          prop: 'asset_status',
          label: '状态',
          align: 'center',
          width: 80,
          formatter: (row: any) => {
            const label = statusLabelMap.value[row.asset_status]
            return label
              ? h(
                  resolveComponent('ElTag'),
                  { type: (statusColorMap.value[row.asset_status] as any) || 'info', effect: 'light' },
                  { default: () => label }
                )
              : '--'
          }
        },
        {
          prop: 'os_name',
          label: '操作系统',
          align: 'center',
          minWidth: 160,
          formatter: (row: any) => row.os_name || '--'
        },
        {
          prop: 'owner',
          label: '负责人',
          align: 'center',
          width: 100,
          formatter: (row: any) => row.owner || '--'
        },
        {
          prop: 'updated_at',
          label: '更新时间',
          align: 'center',
          minWidth: 170,
          formatter: (row: any) => {
            if (!row.updated_at) return '--'
            const d = new Date(row.updated_at)
            return d.toLocaleString('zh-CN')
          }
        },
        {
          prop: 'operation',
          label: '操作',
          align: 'center',
          width: 160,
          fixed: 'right',
          formatter: (row: any) =>
            h('div', { class: 'operation-column-container' }, [
              h(ArtButtonTable, {
                type: 'view',
                style: 'margin-right: 8px;',
                onClick: () => handleViewDetail(row)
              }),
              h(ArtButtonTable, {
                type: 'edit',
                style: 'margin-right: 8px;',
                onClick: () => showDialog('edit', row)
              }),
              h(ArtButtonTable, {
                type: 'delete',
                onClick: () => handleDelete(row)
              })
            ])
        }
      ]
    },
    hooks: {
      onError: (error) => ElMessage.error(error.message)
    }
  })

  const {
    data: tableData,
    loading: isLoading,
    columns,
    columnChecks,
    pagination: paginationState,
    searchParams: searchState,
    getData: searchData,
    resetSearchParams: resetSearch,
    handleSizeChange: onPageSizeChange,
    handleCurrentChange: onCurrentPageChange,
    refreshAll
  } = tableApi as any

  // 表单数据
  const formData = reactive({
    id: '',
    name: '',
    asset_ip: '',
    network_segment: 'default',
    network_zone: 'other',
    asset_type: 'other',
    criticality: 'normal',
    asset_status: '',
    owner: '',
    business_unit: '',
    asset_description: '',
    mac_address: ''
  })

  // 搜索配置
  const searchItems = computed<SearchFormItem[]>(() => [
    {
      label: 'IP地址',
      key: 'asset_ip',
      type: 'input',
      span: 6,
      clearable: true,
      placeholder: '请输入IP地址'
    },
    {
      label: '资产名称',
      key: 'name',
      type: 'input',
      span: 6,
      clearable: true,
      placeholder: '请输入资产名称'
    },
    {
      label: '资产类型',
      key: 'asset_type',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择类型',
      options: assetTypeOptions.value
    },
    {
      label: '重要性',
      key: 'criticality',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择重要性',
      options: criticalityOptions.value
    },
    {
      label: '网络区域',
      key: 'network_zone',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择网络区域',
      options: networkZoneOptions.value
    },
    {
      label: '状态',
      key: 'asset_status',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择状态',
      options: assetStatusOptions.value
    },
    {
      label: '数据来源',
      key: 'data_source',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择来源',
      options: [
        { label: '手动', value: 'manual' },
        { label: 'Wazuh', value: 'wazuh' },
        { label: 'TP-Link', value: 'tplink-router' }
      ]
    }
  ])

  // 列配置选项
  const columnOptions = [
    { label: '资产名称', prop: 'name' },
    { label: 'IP地址', prop: 'asset_ip' },
    { label: 'MAC地址', prop: 'mac_address' },
    { label: '资产类型', prop: 'asset_type' },
    { label: '重要性', prop: 'criticality' },
    { label: '网络区域', prop: 'network_zone' },
    { label: '状态', prop: 'asset_status' },
    { label: '操作系统', prop: 'os_name' },
    { label: '负责人', prop: 'owner' },
    { label: '更新时间', prop: 'updated_at' },
    { label: '操作', prop: 'operation' }
  ]

  const formRef = ref<FormInstance>()

  // 刷新
  const handleRefresh = () => {
    refreshAll()
  }

  // 查看详情
  const handleViewDetail = (row: any) => {
    router.push(`/assets/detail/${row.id}`)
  }

  // 显示弹窗
  const showDialog = (type: string, row?: any) => {
    dialogVisible.value = true
    dialogType.value = type

    if (type === 'edit' && row) {
      formData.id = row.id
      formData.name = row.name || ''
      formData.asset_ip = row.asset_ip || ''
      formData.network_segment = row.network_segment || 'default'
      formData.network_zone = row.network_zone || 'other'
      formData.asset_type = row.asset_type || 'other'
      formData.criticality = row.criticality || 'normal'
      formData.asset_status = row.asset_status || ''
      formData.owner = row.owner || ''
      formData.business_unit = row.business_unit || ''
      formData.asset_description = row.asset_description || ''
      formData.mac_address = row.mac_address || ''
    } else {
      formData.id = ''
      formData.name = ''
      formData.asset_ip = ''
      formData.network_segment = 'default'
      formData.network_zone = 'other'
      formData.asset_type = 'other'
      formData.criticality = 'normal'
      formData.asset_status = ''
      formData.owner = ''
      formData.business_unit = ''
      formData.asset_description = ''
      formData.mac_address = ''
    }

    nextTick(() => {
      formRef.value?.clearValidate()
    })
  }

  // 删除
  const handleDelete = (row: any) => {
    ElMessageBox.confirm(`确定要删除资产 ${row.name || row.asset_ip} 吗？`, '删除资产', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'error'
    })
      .then(async () => {
        try {
          const res = await apiDeleteAsset(row.id)
          if (res.code === 200) {
            ElMessage.success('删除成功')
            refreshAll()
          } else {
            ElMessage.error(res.msg || '删除失败')
          }
        } catch (err) {
          console.error('删除资产出错:', err)
          ElMessage.error('删除失败')
        }
      })
      .catch(() => {})
  }

  // Wazuh同步
  const handleSyncWazuh = () => {
    ElMessageBox.confirm('确定要从 Wazuh 同步资产信息吗？', 'Wazuh同步', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info'
    })
      .then(async () => {
        try {
          const res = await syncFromWazuh()
          if (res.code === 200 || res.data) {
            ElMessage.success(res.data?.message || '同步任务已创建')
            setTimeout(() => refreshAll(), 2000)
          } else {
            ElMessage.error(res.msg || '同步失败')
          }
        } catch (err) {
          console.error('Wazuh同步出错:', err)
          ElMessage.error('同步失败')
        }
      })
      .catch(() => {})
  }

  // 验证规则
  const baseRules = {
    asset_ip: [
      { required: true, message: '请输入IP地址', trigger: 'blur' },
      {
        pattern: /^(\d{1,3}\.){3}\d{1,3}$/,
        message: '请输入正确的IP地址格式',
        trigger: 'blur'
      }
    ],
    mac_address: [
      {
        pattern: /^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/,
        message: '请输入正确的MAC地址格式',
        trigger: 'blur'
      }
    ]
  }

  const computedRules = computed(() => baseRules)

  // 提交
  const handleSubmit = async () => {
    if (!formRef.value) return

    await formRef.value.validate(async (valid) => {
      if (valid) {
        try {
          const submitData = { ...formData }
          // 清除空字符串字段
          Object.keys(submitData).forEach((key) => {
            if ((submitData as any)[key] === '') {
              delete (submitData as any)[key]
            }
          })

          let res
          if (dialogType.value === 'add') {
            res = await addAsset(submitData)
          } else {
            res = await updateAsset(submitData.id, submitData)
          }

          if (res.code === 200) {
            ElMessage.success(dialogType.value === 'add' ? '添加成功' : '更新成功')
            dialogVisible.value = false
            refreshAll()
          } else {
            ElMessage.error(res.msg || (dialogType.value === 'add' ? '添加失败' : '更新失败'))
          }
        } catch (err) {
          console.error('提交出错:', err)
          ElMessage.error(dialogType.value === 'add' ? '添加失败' : '更新失败')
        }
      }
    })
  }
</script>

<style lang="scss" scoped>
  .asset-list-page {
    .operation-column-container {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }
</style>
