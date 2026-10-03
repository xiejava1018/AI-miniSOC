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
    <!-- 绑定覆盖率 KPI（设计 §8.1 T7 · 北极星 H1「关联资产覆盖率 ≥60%」度量） -->
    <ElRow v-if="kpi" :gutter="12" class="kpi-row">
      <ElCol :span="6">
        <ElCard shadow="never" class="kpi-card">
          <div class="kpi-label">业务系统数</div>
          <div class="kpi-value">{{ kpi.systems_count }}</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="kpi-card">
          <div class="kpi-label">已关联资产 / 总资产</div>
          <div class="kpi-value">{{ kpi.linked_assets }} / {{ kpi.total_assets }}</div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="kpi-card">
          <div class="kpi-label">关联资产覆盖率（目标 ≥60%）</div>
          <div class="kpi-value" :class="{ 'kpi-warn': kpi.coverage_rate < 60 }">
            {{ kpi.coverage_rate }}%
          </div>
        </ElCard>
      </ElCol>
      <ElCol :span="6">
        <ElCard shadow="never" class="kpi-card">
          <div class="kpi-label">定级状态（未定级 / 建议待确认）</div>
          <div class="kpi-value" :class="{ 'kpi-warn': kpi.unrated > 0 }">
            {{ kpi.unrated }} / {{ kpi.suggested_pending }}
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

      <!-- 资产明细抽屉（设计 §8.1 T3：业务系统侧查看/编辑成员资产与架构角色） -->
      <ElDrawer
        v-model="assetsDrawerVisible"
        :title="`成员资产 · ${assetsDrawerSystem?.name || ''}`"
        size="70%"
      >
        <ElTable :data="assetsDrawerRows" v-loading="assetsDrawerLoading" border stripe>
          <ElTableColumn prop="name" label="资产名称" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.name || '--' }}</template>
          </ElTableColumn>
          <ElTableColumn prop="asset_ip" label="IP" width="130" show-overflow-tooltip />
          <ElTableColumn label="业务影响" width="90" align="center">
            <template #default="{ row }">
              <ElTag size="small" effect="plain" :type="(BUSINESS_IMPACT_TYPE as any)[row.business_impact] || 'info'">
                {{ BUSINESS_IMPACT_LABEL[row.business_impact] || row.business_impact || '--' }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="数据敏感度" width="90" align="center">
            <template #default="{ row }">
              <ElTag size="small" effect="plain" :type="(DATA_SENSITIVITY_TYPE as any)[row.data_sensitivity] || 'info'">
                {{ DATA_SENSITIVITY_LABEL[row.data_sensitivity] || row.data_sensitivity || '--' }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="等保等级" width="120" align="center">
            <template #default="{ row }">
              <ElTag size="small" effect="plain" :type="(PROTECTION_LEVEL_TYPE as any)[row.protection_level] || 'info'">
                {{ PROTECTION_LEVEL_LABEL[row.protection_level] || row.protection_level }}
              </ElTag>
              <!-- 来源徽标：承=跟随系统就高继承 -->
              <ElTag v-if="row.protection_level_source === 'inherited'" size="small" type="warning" effect="light" class="ml-1">承</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="架构角色" width="150" align="center">
            <template #default="{ row }">
              <ElSelect
                :model-value="row.role"
                size="small"
                placeholder="未指定"
                clearable
                @change="(v: any) => handleRoleChange(row, v)"
              >
                <ElOption v-for="o in roleOptions" :key="o.value" :value="o.value" :label="o.label" />
              </ElSelect>
            </template>
          </ElTableColumn>
        </ElTable>
      </ElDrawer>

      <!-- 定级建议弹窗（设计 §8.1 T6 UI：S4 红线——建议仅供参考，采纳=显式人工确认） -->
      <ElDialog v-model="suggestVisible" title="等保定级建议（辅助定级 · 只建议不裁决）" width="620px">
        <div v-loading="suggestLoading" class="suggest-body">
          <template v-if="suggestBasis">
          <div class="suggest-result">
            建议等级：
            <ElTag size="large" :type="(PROTECTION_LEVEL_TYPE as any)[suggestBasis.suggested_level] || 'info'">
              {{ PROTECTION_LEVEL_LABEL[suggestBasis.suggested_level] }}
            </ElTag>
            <ElTag v-if="suggestFilingHint" size="small" type="info" effect="plain" class="ml-2">
              {{ suggestFilingHint }}
            </ElTag>
          </div>
          <ElAlert type="warning" :closable="false" class="suggest-note">
            {{ suggestBasis?.matrix_inputs?.approximation_note }}
          </ElAlert>
          <ElDescriptions :column="2" border size="small" class="suggest-desc">
            <ElDescriptionsItem label="受侵害客体（代理）">
              {{ suggestBasis?.matrix_inputs?.victim_object_label }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="侵害程度（代理）">
              {{ suggestBasis?.matrix_inputs?.harm_degree_label }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="数据敏感度 →">
              {{ DATA_SENSITIVITY_LABEL[suggestBasis?.matrix_inputs?.proxies?.data_sensitivity] }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="业务影响 →">
              {{ BUSINESS_IMPACT_LABEL[suggestBasis?.matrix_inputs?.proxies?.business_impact] }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="成员资产数">
              {{ suggestBasis?.evidence?.asset_count ?? 0 }}
            </ElDescriptionsItem>
            <ElDescriptionsItem label="公网暴露资产">
              {{ suggestBasis?.evidence?.public_exposed_assets ?? 0 }}
            </ElDescriptionsItem>
          </ElDescriptions>
          <div class="suggest-actions">
            <ElButton
              type="primary"
              :disabled="suggestAdopted"
              @click="handleAdoptSuggestion"
            >
              {{ suggestAdopted ? '已采纳（等级已确认）' : '采纳建议（确认等级）' }}
            </ElButton>
            <span class="suggest-hint">采纳后按「就高」联动成员资产等级（人工设定的资产不受影响）</span>
          </div>
          </template>
        </div>
      </ElDialog>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, h, resolveComponent, nextTick, onMounted } from 'vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import request from '@/utils/http'
  import {
    fetchBusinessSystemList,
    createBusinessSystem,
    updateBusinessSystem,
    deleteBusinessSystem,
    getBusinessSystemAssets,
    suggestProtectionLevel,
    fetchCoverageKpi,
    patchAssetBusinessRole,
    type BusinessSystemItem,
    type CoverageKpi
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
          width: 110,
          formatter: (row: BusinessSystemItem) =>
            h('div', { style: 'display:flex; align-items:center; justify-content:center; gap:4px;' }, [
              h(
                resolveComponent('ElTag'),
                { type: PROTECTION_LEVEL_TYPE[row.protection_level] || 'info', size: 'small', effect: 'plain' },
                { default: () => PROTECTION_LEVEL_LABEL[row.protection_level] || row.protection_level }
              ),
              // 定级状态徽标（设计 §8.1 T7）：unrated=灰 / suggested=橙 / confirmed=绿
              row.rating_status === 'confirmed'
                ? h(resolveComponent('ElTag'), { type: 'success', size: 'small', effect: 'light' }, { default: () => '已确认' })
                : row.rating_status === 'suggested'
                  ? h(resolveComponent('ElTag'), { type: 'warning', size: 'small', effect: 'light' }, { default: () => '建议中' })
                  : h(resolveComponent('ElTag'), { type: 'info', size: 'small', effect: 'light' }, { default: () => '未定级' })
            ])
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
          width: 300,
          fixed: 'right',
          formatter: (row: BusinessSystemItem) =>
            h('div', { class: 'operation-column-container' }, [
              h(ArtButtonTable, {
                type: 'edit',
                style: 'margin-right: 8px;',
                onClick: () => showDialog('edit', row)
              }),
              h(ArtButtonTable, {
                text: '资产',
                style: 'margin-right: 8px;',
                onClick: () => openAssetsDrawer(row)
              }),
              h(ArtButtonTable, {
                text: '定级建议',
                style: 'margin-right: 8px;',
                onClick: () => handleSuggest(row)
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

  // 删除（设计 §8.1 T8 · D9 防护：非空系统需 force=true 二次确认）
  // 注意：成功提示由 http 拦截器根据 showSuccessMessage 自动弹（"删除成功"），
  // 这里不再手动 ElMessage.success，避免双提示。失败仍走 catch + 后端 envelope msg。
  const deleteAction = (row: BusinessSystemItem) => {
    const hasAssets = row.asset_count > 0
    ElMessageBox.confirm(
      hasAssets
        ? `业务系统「${row.name}」下有 ${row.asset_count} 个资产关联。\n删除将解除全部关联并重算成员资产等级（人工设定的保留现值）。确定继续？`
        : `确定删除业务系统「${row.name}」吗？`,
      '删除确认',
      { confirmButtonText: hasAssets ? '确认删除（force）' : '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
      .then(async () => {
        try {
          // 后端 D9：有成员时必须带 force=true，否则 400
          await deleteBusinessSystem(row.id, hasAssets)
          refresh()
          loadKpi()
        } catch (err: any) {
          console.error('删除业务系统出错:', err)
          ElMessage.error(err?.response?.data?.msg || err?.message || '删除失败，请稍后再试')
        }
      })
      .catch(() => {})
  }

  // ===== 绑定覆盖率 KPI（设计 §8.1 T7）=====
  const kpi = ref<CoverageKpi | null>(null)
  async function loadKpi() {
    try {
      kpi.value = await fetchCoverageKpi()
    } catch (e) {
      console.error('[BS] 加载覆盖率 KPI 失败', e)
    }
  }

  // ===== 资产明细抽屉（设计 §8.1 T3）=====
  const assetsDrawerVisible = ref(false)
  const assetsDrawerLoading = ref(false)
  const assetsDrawerSystem = ref<BusinessSystemItem | null>(null)
  const assetsDrawerRows = ref<any[]>([])

  // role 选项（dict_type='asset_business_role'，迁移 d8e9f0a1b2c3 种子；
  // 本地映射零额外请求——字典项与后端 ASSET_BUSINESS_ROLE_VALUES 一致）
  const roleOptions = [
    { value: 'web', label: 'Web 层' },
    { value: 'app', label: '应用层' },
    { value: 'db', label: '数据层' },
    { value: 'mq', label: '消息队列' },
    { value: 'cache', label: '缓存层' },
    { value: 'gateway', label: '网关接入' },
    { value: 'lb', label: '负载均衡' },
    { value: 'other', label: '其他' }
  ]

  async function openAssetsDrawer(row: BusinessSystemItem) {
    assetsDrawerSystem.value = row
    assetsDrawerVisible.value = true
    assetsDrawerLoading.value = true
    try {
      const res: any = await getBusinessSystemAssets(row.id)
      assetsDrawerRows.value = Array.isArray(res) ? res : res?.data || []
    } catch (e) {
      console.error('[BS] 加载成员资产失败', e)
      assetsDrawerRows.value = []
    } finally {
      assetsDrawerLoading.value = false
    }
  }

  async function handleRoleChange(row: any, role: string | null) {
    if (!assetsDrawerSystem.value) return
    try {
      await patchAssetBusinessRole(row.asset_id, assetsDrawerSystem.value.id, role)
      row.role = role
      ElMessage.success('架构角色已更新')
    } catch (err: any) {
      console.error('[BS] 更新角色失败', err)
      ElMessage.error(err?.response?.data?.msg || '角色更新失败')
    }
  }

  // ===== 定级建议（设计 §8.1 T6 UI）=====
  const suggestVisible = ref(false)
  const suggestLoading = ref(false)
  const suggestBasis = ref<Record<string, any> | null>(null)
  const suggestFilingHint = ref('')
  const suggestSystem = ref<BusinessSystemItem | null>(null)
  const suggestAdopted = computed(() => suggestSystem.value?.rating_status === 'confirmed')

  async function handleSuggest(row: BusinessSystemItem) {
    suggestSystem.value = row
    suggestVisible.value = true
    suggestLoading.value = true
    suggestBasis.value = null
    try {
      const res: any = await suggestProtectionLevel(row.id)
      suggestBasis.value = res?.suggestion_basis || res || null
      suggestFilingHint.value = suggestBasis.value?.filing_hint || ''
    } catch (e) {
      console.error('[BS] 定级建议失败', e)
      ElMessage.error('定级建议生成失败')
    } finally {
      suggestLoading.value = false
    }
  }

  // 采纳建议 = 显式人工确认（S4 红线）：PUT protection_level → 后端置 confirmed + 就高传播
  async function handleAdoptSuggestion() {
    if (!suggestSystem.value || !suggestBasis.value) return
    const level = suggestBasis.value.suggested_level
    try {
      await updateBusinessSystem(suggestSystem.value.id, { protection_level: level })
      ElMessage.success(`已确认等级「${PROTECTION_LEVEL_LABEL[level] || level}」，成员资产已按就高联动`)
      suggestVisible.value = false
      refresh()
      loadKpi()
    } catch (err) {
      console.error('[BS] 采纳建议失败', err)
      ElMessage.error('采纳失败，请稍后再试')
    }
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

  onMounted(() => {
    loadDepartments()
    loadKpi()
  })
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
    // KPI 卡（设计 §8.1 T7）
    .kpi-row {
      margin-bottom: 12px;
    }
    .kpi-card {
      :deep(.el-card__body) {
        padding: 12px 16px;
      }
      .kpi-label {
        font-size: 12px;
        color: var(--el-text-color-secondary);
        margin-bottom: 4px;
      }
      .kpi-value {
        font-size: 22px;
        font-weight: 600;
        line-height: 1.2;
      }
      .kpi-warn {
        color: var(--el-color-warning);
      }
    }
    // 定级建议弹窗（设计 §8.1 T6 UI）
    .suggest-body {
      .suggest-result {
        display: flex;
        align-items: center;
        font-size: 15px;
        margin-bottom: 12px;
      }
      .suggest-note {
        margin-bottom: 12px;
      }
      .suggest-desc {
        margin-bottom: 16px;
      }
      .suggest-actions {
        display: flex;
        align-items: center;
        gap: 12px;
        .suggest-hint {
          font-size: 12px;
          color: var(--el-text-color-secondary);
        }
      }
    }
  }
</style>
