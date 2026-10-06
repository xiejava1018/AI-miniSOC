<!--
  AI 资产台账 / 影子 AI（OH-UI.7 · S13）

  作为「AI 模型管理」页的第二个 Tab 嵌入（而非新建顶级菜单）。
  v1 数据底座：列表+看板；不含影子 AI 自动识别（独立任务）。
  credential 类不展示明文凭据（后端本就禁存，这里只展示元数据）。
-->
<template>
  <div class="ai-asset-ledger">
    <!-- 看板计数 -->
    <div class="kpi-row" v-loading="dashLoading">
      <div class="kpi-card">
        <div class="kpi-num">{{ dash.total }}</div>
        <div class="kpi-label">AI 资产总数</div>
      </div>
      <div class="kpi-card shadow">
        <div class="kpi-num">{{ dash.shadow_ai_count }}</div>
        <div class="kpi-label">影子 AI</div>
      </div>
      <div class="kpi-card" v-for="(v, k) in dash.by_kind" :key="k">
        <div class="kpi-num">{{ v }}</div>
        <div class="kpi-label">{{ kindLabel[k] || k }}</div>
      </div>
    </div>

    <ElCard shadow="never" class="art-table-card">
      <div class="toolbar">
        <ElSelect
          v-model="kindFilter"
          placeholder="类型"
          clearable
          style="width: 140px"
          @change="loadList"
        >
          <ElOption v-for="(label, v) in kindLabel" :key="v" :label="label" :value="v" />
        </ElSelect>
        <ElSelect
          v-model="statusFilter"
          placeholder="状态"
          clearable
          style="width: 150px; margin-left: 8px"
          @change="loadList"
        >
          <ElOption label="已登记" value="registered" />
          <ElOption label="影子" value="shadow" />
          <ElOption label="已批准" value="sanctioned" />
          <ElOption label="已下线" value="decommissioned" />
        </ElSelect>
        <div class="grow-spacer" />
        <ElButton type="primary" @click="openCreate">+ 登记 AI 资产</ElButton>
      </div>

      <ElAlert
        v-if="dash.red_line"
        type="info"
        :closable="false"
        show-icon
        style="margin: 8px 0 12px"
        :title="dash.red_line"
      />

      <ArtTable
        :data="rows"
        :columns="columns"
        :loading="loading"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :pagination="pagination"
        :layout="{ marginTop: 10 }"
        @pagination:current-change="onPage"
      />
    </ElCard>

    <!-- 登记抽屉 -->
    <ElDrawer
      v-model="drawerVisible"
      title="登记 AI 资产"
      size="520px"
      :close-on-click-modal="false"
    >
      <ElForm :model="form" label-width="100px">
        <ElFormItem label="类型 *">
          <ElSelect v-model="form.kind" style="width: 100%">
            <ElOption v-for="(label, v) in kindLabel" :key="v" :label="label" :value="v" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="名称 *">
          <ElInput v-model="form.name" placeholder="资产名称" />
        </ElFormItem>
        <ElFormItem label="提供方">
          <ElInput v-model="form.provider" placeholder="openai / internal / ..." />
        </ElFormItem>
        <ElFormItem label="版本">
          <ElInput v-model="form.version" />
        </ElFormItem>
        <ElFormItem label="责任人">
          <ElInput v-model="form.owner" />
        </ElFormItem>
        <ElFormItem label="所属部门">
          <ElInput v-model="form.business_unit" />
        </ElFormItem>
        <ElFormItem label="状态">
          <ElSelect v-model="form.status" style="width: 100%">
            <ElOption label="已登记" value="registered" />
            <ElOption label="影子" value="shadow" />
            <ElOption label="已批准" value="sanctioned" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="风险等级">
          <ElSelect v-model="form.risk_level" style="width: 100%">
            <ElOption label="低" value="low" />
            <ElOption label="中" value="medium" />
            <ElOption label="高" value="high" />
            <ElOption label="严重" value="critical" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="描述">
          <ElInput v-model="form.description" type="textarea" :rows="2" />
        </ElFormItem>

        <ElAlert
          v-if="form.kind === 'credential'"
          type="warning"
          :closable="false"
          show-icon
          title="凭据类资产只登记元数据，禁止填写 api_key / token / secret 等明文"
          style="margin-bottom: 12px"
        />
      </ElForm>
      <template #footer>
        <ElButton @click="drawerVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" @click="onSave">保存</ElButton>
      </template>
    </ElDrawer>

    <!-- 详情抽屉 -->
    <ElDrawer v-model="detailVisible" title="AI 资产详情" size="520px">
      <ElDescriptions :column="1" border v-if="detail">
        <ElDescriptionsItem label="类型">{{ kindLabel[detail.kind] }}</ElDescriptionsItem>
        <ElDescriptionsItem label="名称">{{ detail.name }}</ElDescriptionsItem>
        <ElDescriptionsItem label="提供方">{{ detail.provider || '-' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="版本">{{ detail.version || '-' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="责任人">{{ detail.owner || '-' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="部门">{{ detail.business_unit || '-' }}</ElDescriptionsItem>
        <ElDescriptionsItem label="状态">
          <ElTag :type="statusTag[detail.status]">{{ statusLabel[detail.status] }}</ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="风险">
          <ElTag :type="riskTag[detail.risk_level]">{{ riskLabel[detail.risk_level] }}</ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem label="发现来源">{{ detail.discovery_source }}</ElDescriptionsItem>
        <ElDescriptionsItem label="类型详情">
          <pre class="json-pre">{{ JSON.stringify(detail.details, null, 2) }}</pre>
        </ElDescriptionsItem>
      </ElDescriptions>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createAIAsset,
  getAIAsset,
  getAIAssetDashboard,
  listAIAssets,
  type AIAsset,
  type AIAssetDashboard,
  type AIAssetKind,
  type AIAssetRisk,
  type AIAssetStatus,
} from '@/api/aiAsset'

const kindLabel: Record<string, string> = {
  model: '模型',
  data: '数据',
  agent: 'Agent',
  tool: '工具',
  credential: '凭据',
  compute: '算力',
}
const statusLabel: Record<string, string> = {
  registered: '已登记',
  shadow: '影子',
  sanctioned: '已批准',
  decommissioned: '已下线',
}
const statusTag: Record<string, any> = {
  registered: 'info',
  shadow: 'danger',
  sanctioned: 'success',
  decommissioned: '',
}
const riskLabel: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '严重',
}
const riskTag: Record<string, any> = {
  low: 'success', medium: 'info', high: 'warning', critical: 'danger',
}

const dash = reactive<AIAssetDashboard>({
  total: 0, by_kind: {}, by_status: {}, by_risk: {}, shadow_ai_count: 0,
})
const dashLoading = ref(false)
const rows = ref<AIAsset[]>([])
const loading = ref(false)
const kindFilter = ref<AIAssetKind>()
const statusFilter = ref<AIAssetStatus>()
const page = ref(1)

const pagination = reactive({
  current: 1,
  size: 20,
  total: 0,
})

const columns: any[] = [
  { prop: 'kind', label: '类型', width: 100,
    render: ({ row }: any) => kindLabel[row.kind] },
  { prop: 'name', label: '名称', minWidth: 160 },
  { prop: 'provider', label: '提供方', width: 120 },
  { prop: 'version', label: '版本', width: 120 },
  { prop: 'owner', label: '责任人', width: 110 },
  { prop: 'status', label: '状态', width: 90,
    render: ({ row }: any) =>
      h(ElTag, { type: statusTag[row.status] }, () => statusLabel[row.status]) },
  { prop: 'risk_level', label: '风险', width: 80,
    render: ({ row }: any) =>
      h(ElTag, { type: riskTag[row.risk_level] }, () => riskLabel[row.risk_level]) },
  { prop: 'op', label: '操作', width: 80, fixed: 'right',
    render: ({ row }: any) =>
      h(ElButton, { link: true, type: 'primary', onClick: () => openDetail(row.id) },
        () => '详情') },
]

import { h } from 'vue'
import { ElTag, ElButton } from 'element-plus'

// ---------------- 数据加载 ----------------

async function loadDash() {
  dashLoading.value = true
  try {
    const d = await getAIAssetDashboard()
    Object.assign(dash, d)
  } finally {
    dashLoading.value = false
  }
}

async function loadList() {
  loading.value = true
  try {
    const r = await listAIAssets({
      kind: kindFilter.value,
      status: statusFilter.value,
      limit: 100,
    })
    rows.value = r.items
    pagination.total = r.total
  } finally {
    loading.value = false
  }
}

function onPage(p: number) {
  page.value = p
}

// ---------------- 登记 ----------------

const drawerVisible = ref(false)
const saving = ref(false)
const form = reactive<{
  kind: AIAssetKind
  name: string
  provider: string
  version: string
  owner: string
  business_unit: string
  status: AIAssetStatus
  risk_level: AIAssetRisk
  description: string
}>({
  kind: 'model', name: '', provider: '', version: '', owner: '',
  business_unit: '', status: 'registered', risk_level: 'medium',
  description: '',
})

function openCreate() {
  Object.assign(form, {
    kind: 'model', name: '', provider: '', version: '', owner: '',
    business_unit: '', status: 'registered', risk_level: 'medium',
    description: '',
  })
  drawerVisible.value = true
}

async function onSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  saving.value = true
  try {
    await createAIAsset({ ...form })
    ElMessage.success('已登记')
    drawerVisible.value = false
    await Promise.all([loadDash(), loadList()])
  } finally {
    saving.value = false
  }
}

// ---------------- 详情 ----------------

const detailVisible = ref(false)
const detail = ref<AIAsset | null>(null)

async function openDetail(id: string) {
  detail.value = await getAIAsset(id)
  detailVisible.value = true
}

onMounted(() => {
  loadDash()
  loadList()
})
</script>

<style scoped>
.kpi-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.kpi-card {
  flex: 1;
  min-width: 120px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 18px;
}
.kpi-card.shadow {
  border-color: var(--el-color-danger-light-5);
}
.kpi-num {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
}
.kpi-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 4px;
}
.toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.grow-spacer {
  flex: 1;
}
.json-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
}
</style>
