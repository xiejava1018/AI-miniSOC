<!--
  业务系统管理页（v1 §7.0 WO-0a / §7.2.5 F9，治本方案 2026-09-14）

  重要性三维度：
    - 业务影响（business_impact）：5 档 核心/重要/一般/辅助/可忽略 → 驱动 SLA
    - 数据敏感度（data_sensitivity）：5 档 极高/高/中/低/可公开 → 驱动风险评分
    - 等保等级（protection_level）：5 档 等保五级 ~ 等保一级 → 合规锚点

  对应后端：/api/v1/business-systems/*
  权限：列表/详情 所有登录用户可读；新建/编辑/删除 需 admin（后端 require_admin 兜底）

  布局完全对齐「角色管理」页（views/system/role/index.vue）：
  ArtSearchBar + ArtTableHeader(v-model:columns) + ArtTable(useTable) + ElDialog
-->
<template>
  <div class="business-system-page art-full-height" id="table-full-screen">
    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="resetSearchParams"
      @search="getDataByPage"
    />

    <ElCard shadow="never" class="art-table-card">
      <!-- 表格头部 -->
      <ArtTableHeader v-model:columns="columnChecks" @refresh="refresh">
        <template #left>
          <ElButton @click="showDialog('add')">新建业务系统</ElButton>
        </template>
      </ArtTableHeader>

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

      <!-- 新建/编辑 弹窗 -->
      <ElDialog
        v-model="dialogVisible"
        :title="dialogType === 'add' ? '新建业务系统' : '编辑业务系统'"
        width="560px"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <ElForm ref="formRef" :model="form" :rules="rules" label-width="100px" @submit.prevent>
          <ElFormItem label="编码" prop="code">
            <ElInput v-model="form.code" placeholder="小写英文/数字/-/_，如 soc-platform" maxlength="50" />
          </ElFormItem>
          <ElFormItem label="名称" prop="name">
            <ElInput v-model="form.name" placeholder="如 SOC 安全平台" maxlength="100" />
          </ElFormItem>

          <!-- 三维度重要性（治本方案） -->
          <ElDivider content-position="left" style="margin: 12px 0 8px;">
            <span style="font-size: 12px; color: var(--el-text-color-secondary);">
              重要性 · 三维度（业务影响 / 数据敏感度 / 等保等级）
            </span>
          </ElDivider>

          <ElFormItem label="业务影响" prop="business_impact">
            <ElSelect v-model="form.business_impact" placeholder="请选择业务影响" style="width: 100%">
              <ElOption
                v-for="v in BUSINESS_IMPACT_ORDER"
                :key="v"
                :value="v"
                :label="`${BUSINESS_IMPACT_LABEL[v]}（${v}）`"
              />
            </ElSelect>
            <span class="form-tip">驱动 SLA / 推送优先级</span>
          </ElFormItem>

          <ElFormItem label="数据敏感度" prop="data_sensitivity">
            <ElSelect v-model="form.data_sensitivity" placeholder="请选择数据敏感度" style="width: 100%">
              <ElOption
                v-for="v in DATA_SENSITIVITY_ORDER"
                :key="v"
                :value="v"
                :label="`${DATA_SENSITIVITY_LABEL[v]}（${v}）`"
              />
            </ElSelect>
            <span class="form-tip">驱动风险评分加权</span>
          </ElFormItem>

          <ElFormItem label="等保等级" prop="protection_level">
            <ElSelect v-model="form.protection_level" placeholder="请选择等保等级" style="width: 100%">
              <ElOption
                v-for="v in PROTECTION_LEVEL_ORDER"
                :key="v"
                :value="v"
                :label="PROTECTION_LEVEL_LABEL[v]"
              />
            </ElSelect>
            <span class="form-tip">合规锚点（等保 2.0 五级保护对象）</span>
          </ElFormItem>

          <ElFormItem label="部门" prop="department_id">
            <ElSelect
              v-model="form.department_id"
              placeholder="请选择部门（可选）"
              clearable
              filterable
              style="width: 100%"
            >
              <ElOption v-for="d in departmentOptions" :key="d.value" :value="d.value" :label="d.label" />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="责任人" prop="owner">
            <ElInput v-model="form.owner" placeholder="责任人姓名（可不填平台用户）" maxlength="255" />
          </ElFormItem>
          <ElFormItem label="责任人电话" prop="owner_contact">
            <ElInput v-model="form.owner_contact" placeholder="安全风险应急联系电话" maxlength="50" />
          </ElFormItem>
          <ElFormItem label="描述">
            <ElInput
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="可选：用途 / 范围 / 责任边界"
              maxlength="2000"
            />
          </ElFormItem>
        </ElForm>
        <template #footer>
          <div class="dialog-footer">
            <ElButton @click="dialogVisible = false">取消</ElButton>
            <ElButton type="primary" :loading="submitLoading" @click="handleSubmit(formRef)">提交</ElButton>
          </div>
        </template>
      </ElDialog>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, h, resolveComponent, nextTick, onMounted } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import request from '@/utils/http'
  import {
    fetchBusinessSystemList,
    createBusinessSystem,
    updateBusinessSystem,
    deleteBusinessSystem,
    type BusinessSystemItem
  } from '@/api/businessSystem'
  import { useTable } from '@/composables/useTable'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import { SearchFormItem } from '@/types'
  import {
    BUSINESS_IMPACT_LABEL,
    BUSINESS_IMPACT_TYPE,
    BUSINESS_IMPACT_ORDER,
    DATA_SENSITIVITY_LABEL,
    DATA_SENSITIVITY_TYPE,
    DATA_SENSITIVITY_ORDER,
    PROTECTION_LEVEL_LABEL,
    PROTECTION_LEVEL_TYPE,
    PROTECTION_LEVEL_ORDER,
  } from '@/constants/criticality'

  defineOptions({ name: 'BusinessSystemManagement' })

  // 搜索表单配置项（labelWidth 88px 防「名称/编码」换行）
  const searchItems: SearchFormItem[] = [
    {
      label: '名称/编码',
      key: 'keyword',
      type: 'input',
      clearable: true,
      placeholder: '模糊匹配名称或编码',
      labelWidth: '88px'
    }
  ]

  // 部门下拉选项（id→name）
  // 注意：后端 /api/v1/departments 的 page_size 上限 le=100，传 200 会被 422 拒 → 下拉空。
  const departmentOptions = ref<{ label: string; value: number }[]>([])
  async function loadDepartments() {
    try {
      const res: any = await request.get({
        url: '/api/v1/departments',
        params: { page: 1, page_size: 100 },
        keepFullResponse: true
      })
      const items = res?.data?.items || []
      departmentOptions.value = items.map((d: any) => ({ label: d.name, value: d.id }))
    } catch (e) {
      console.error('[BS] 加载部门列表失败', e)
    }
  }

  // 弹窗表单（三维度 + criticality 兼容垫片）
  const form = reactive<{
    id: string
    code: string
    name: string
    business_impact: string
    data_sensitivity: string
    protection_level: string
    criticality: string  // DEPRECATED，提交时不发，后端自动从 data_sensitivity 派生
    department_id: number | null
    owner: string
    owner_contact: string
    description: string
  }>({
    id: '',
    code: '',
    name: '',
    business_impact: 'normal',
    data_sensitivity: 'medium',
    protection_level: 'level_2',
    criticality: 'medium',
    department_id: null,
    owner: '',
    owner_contact: '',
    description: ''
  })
  const dialogType = ref<'add' | 'edit'>('add')
  const dialogVisible = ref(false)
  const submitLoading = ref(false)
  const formRef = ref<FormInstance>()

  // 表单验证规则
  const rules = reactive<FormRules>({
    code: [
      { required: true, message: '请输入编码', trigger: 'blur' },
      {
        pattern: /^[a-zA-Z][a-zA-Z0-9_-]{1,49}$/,
        message: '以字母开头，仅含字母数字/-/_，长度 2~50',
        trigger: 'blur'
      }
    ],
    name: [
      { required: true, message: '请输入名称', trigger: 'blur' },
      { min: 2, max: 100, message: '长度在 2 到 100 个字符', trigger: 'blur' }
    ],
    business_impact: [{ required: true, message: '请选择业务影响', trigger: 'change' }],
    data_sensitivity: [{ required: true, message: '请选择数据敏感度', trigger: 'change' }],
    protection_level: [{ required: true, message: '请选择等保等级', trigger: 'change' }]
  })

  // useTable：后端分页参数是 page/page_size，响应用自定义 adapter 解 data.items
  const {
    columns,
    columnChecks,
    data,
    loading,
    pagination,
    searchParams,
    getData: getDataByPage,
    resetSearchParams,
    handleSizeChange,
    handleCurrentChange,
    refreshAll: refresh
  } = useTable<any>({
    core: {
      apiFn: fetchBusinessSystemList,
      apiParams: {
        page: 1,
        page_size: 10,
        keyword: ''
      },
      // useTable 发请求时用 page/page_size（与后端参数一致）
      paginationKey: {
        current: 'page',
        size: 'page_size'
      },
      columnsFactory: () => [
        {
          prop: 'code',
          label: '编码',
          align: 'center',
          minWidth: 140,
          showOverflowTooltip: true
        },
        {
          prop: 'name',
          label: '名称',
          align: 'center',
          minWidth: 140,
          showOverflowTooltip: true
        },
        {
          prop: 'business_impact',
          label: '业务影响',
          align: 'center',
          width: 95,
          formatter: (row: BusinessSystemItem) =>
            h(
              resolveComponent('ElTag'),
              { type: BUSINESS_IMPACT_TYPE[row.business_impact] || 'info', size: 'small', effect: 'plain' },
              { default: () => BUSINESS_IMPACT_LABEL[row.business_impact] || row.business_impact }
            )
        },
        {
          prop: 'data_sensitivity',
          label: '数据敏感度',
          align: 'center',
          width: 95,
          formatter: (row: BusinessSystemItem) =>
            h(
              resolveComponent('ElTag'),
              { type: DATA_SENSITIVITY_TYPE[row.data_sensitivity] || 'info', size: 'small', effect: 'plain' },
              { default: () => DATA_SENSITIVITY_LABEL[row.data_sensitivity] || row.data_sensitivity }
            )
        },
        {
          prop: 'protection_level',
          label: '等保等级',
          align: 'center',
          width: 90,
          formatter: (row: BusinessSystemItem) =>
            h(
              resolveComponent('ElTag'),
              { type: PROTECTION_LEVEL_TYPE[row.protection_level] || 'info', size: 'small', effect: 'plain' },
              { default: () => PROTECTION_LEVEL_LABEL[row.protection_level] || row.protection_level }
            )
        },
        {
          prop: 'department_name',
          label: '部门',
          align: 'center',
          width: 110,
          showOverflowTooltip: true,
          formatter: (row: BusinessSystemItem) => row.department_name || '--'
        },
        {
          prop: 'owner',
          label: '责任人',
          align: 'center',
          width: 100,
          showOverflowTooltip: true,
          formatter: (row: BusinessSystemItem) => row.owner || '--'
        },
        {
          prop: 'owner_contact',
          label: '责任人电话',
          align: 'center',
          width: 130,
          showOverflowTooltip: true,
          formatter: (row: BusinessSystemItem) => row.owner_contact || '--'
        },
        {
          prop: 'asset_count',
          label: '关联资产',
          align: 'center',
          width: 90
        },
        {
          prop: 'operation',
          label: '操作',
          align: 'center',
          width: 160,
          fixed: 'right',
          formatter: (row: BusinessSystemItem) =>
            h('div', { class: 'operation-column-container' }, [
              h(ArtButtonTable, {
                type: 'edit',
                style: 'margin-right: 8px;',
                onClick: () => showDialog('edit', row)
              }),
              h(ArtButtonTable, {
                type: 'delete',
                onClick: () => deleteAction(row)
              })
            ])
        }
      ]
    },
    transform: {
      // 后端 envelope：{ code, msg, data: { items, total, page, page_size } }
      responseAdapter: (res: any) => ({
        records: res?.data?.items || [],
        total: res?.data?.total || 0,
        current: res?.data?.page,
        size: res?.data?.page_size
      })
    },
    hooks: {
      onError: (error) => ElMessage.error(error.message)
    }
  })

  // 弹窗
  const showDialog = (type: 'add' | 'edit', row?: BusinessSystemItem) => {
    dialogType.value = type
    dialogVisible.value = true
    nextTick(() => {
      formRef.value?.resetFields()
      if (type === 'edit' && row) {
        form.id = row.id
        form.code = row.code
        form.name = row.name
        form.business_impact = row.business_impact || 'normal'
        form.data_sensitivity = row.data_sensitivity || 'medium'
        form.protection_level = row.protection_level || 'level_2'
        form.criticality = row.criticality || 'medium'
        form.department_id = row.department_id ?? null
        form.owner = row.owner || ''
        form.owner_contact = row.owner_contact || ''
        form.description = row.description || ''
      } else {
        form.id = ''
        form.code = ''
        form.name = ''
        form.business_impact = 'normal'
        form.data_sensitivity = 'medium'
        form.protection_level = 'level_2'
        form.criticality = 'medium'
        form.department_id = null
        form.owner = ''
        form.owner_contact = ''
        form.description = ''
      }
    })
  }

  // 删除
  // 注意：成功提示由 http 拦截器根据 showSuccessMessage 自动弹（"删除成功"），
  // 这里不再手动 ElMessage.success，避免双提示。失败仍走 catch + 后端 envelope msg。
  const deleteAction = (row: BusinessSystemItem) => {
    ElMessageBox.confirm(
      `确定删除业务系统「${row.name}」吗？将同时解除 ${row.asset_count} 个资产关联。`,
      '删除确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
      .then(async () => {
        try {
          await deleteBusinessSystem(row.id)
          refresh()
        } catch (err) {
          console.error('删除业务系统出错:', err)
          ElMessage.error('删除失败，请稍后再试')
        }
      })
      .catch(() => {})
  }

  // 提交（三维度全部发送，criticality 字段不发送，由后端自动从 data_sensitivity 派生）
  const handleSubmit = async (formEl: FormInstance | undefined) => {
    if (!formEl) return
    await formEl.validate(async (valid) => {
      if (!valid) return
      submitLoading.value = true
      try {
        const payload = {
          code: form.code.toLowerCase().trim(),
          name: form.name.trim(),
          // === 治本方案：三维度 ===
          business_impact: form.business_impact,
          data_sensitivity: form.data_sensitivity,
          protection_level: form.protection_level,
          department_id: form.department_id || null,
          owner: form.owner.trim() || null,
          owner_contact: form.owner_contact.trim() || null,
          description: form.description || null
          // 注意：criticality 字段不在此处提交；后端会自动从 data_sensitivity 派生写入
        }
        if (dialogType.value === 'add') {
          await createBusinessSystem(payload)
        } else {
          await updateBusinessSystem(form.id, payload)
        }
        dialogVisible.value = false
        refresh()
      } catch (err) {
        console.error('保存业务系统出错:', err)
      } finally {
        submitLoading.value = false
      }
    })
  }

  onMounted(loadDepartments)
</script>

<style lang="scss" scoped>
  .business-system-page {
    .operation-column-container {
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .form-tip {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      margin-left: 8px;
    }
  }
</style>
