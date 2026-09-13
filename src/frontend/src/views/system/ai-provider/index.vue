<!--
  AI 模型管理（多 AI Provider 配置，2026-09-13 独立化拆分）

  与数据源管理的分工：数据源 = 被采集的安全数据输入；AI Provider = 平台智能能力底座。
  场景路由：ai_client.ai_chat(scene=...) → 精确匹配 scenes → 默认实例 → .env GLM 回落。
-->
<template>
  <div class="ai-provider-page art-full-height">
    <ElCard shadow="never" class="art-table-card">
      <!-- 工具栏（与数据源管理一致：搜索框 append 按钮 + 新增放右侧） -->
      <div class="toolbar">
        <ElInput
          v-model="searchKeyword"
          placeholder="搜索编码/名称"
          style="width: 260px"
          clearable
          @keyup.enter="getData"
          @clear="getData"
        >
          <template #append>
            <ElButton @click="getData">搜索</ElButton>
          </template>
        </ElInput>
        <div class="grow-spacer" />
        <ElButton type="primary" @click="showDialog()">+ 新增模型</ElButton>
      </div>

      <!-- 回落状态提示：无实例时显式声明 env 回落生效中（防“看不到数据以为没配”的困惑） -->
      <ElAlert
        v-if="!loading && rows.length === 0 && !searchKeyword"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>当前未配置 AI 模型实例，全部 AI 功能回落 <b>.env GLM 环境变量</b>（glm-4-flash）生效中</template>
        新增实例并测试通过后，勾选场景即可让对应功能（报告/查询/画像等）切换到该模型，60 秒内生效、无需重启；未勾选场景继续用默认实例或环境变量回落。
      </ElAlert>

      <ArtTable
        :data="rows"
        :columns="columns"
        :pagination="paginationState"
        :loading="loading"
        table-layout="fixed"
        :table-config="{ rowKey: 'id' }"
        :layout="{ marginTop: 10 }"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 新增/编辑抽屉 -->
    <ElDrawer
      v-model="drawerVisible"
      :title="isEdit ? '编辑 AI 模型' : '新增 AI 模型'"
      size="600px"
      :close-on-click-modal="false"
      class="ai-provider-drawer"
    >
      <div class="drawer-wrap">
        <div class="drawer-head">
          <h3>{{ isEdit ? '编辑 AI 模型' : '新增 AI 模型' }}</h3>
        </div>
        <p class="muted">
          OpenAI 兼容协议（GLM / DeepSeek / 通义千问 / Kimi / OpenAI / Ollama 本地模型等）。
          保存后 60 秒内生效，无需重启。
        </p>

        <div class="sec-title">基本信息</div>
        <ElForm ref="formRef" :model="form" :rules="rules" label-width="110px">
          <ElFormItem label="编码 *" prop="provider_code">
            <ElInput
              v-model="form.provider_code"
              :disabled="isEdit"
              placeholder="如 glm-main / deepseek"
            />
            <div class="hint">小写字母数字连字符，3-64 位</div>
          </ElFormItem>
          <ElFormItem label="显示名称 *" prop="name">
            <ElInput v-model="form.name" placeholder="如 生产 GLM" />
          </ElFormItem>

          <div class="sec-title">连接参数</div>
          <ElFormItem label="Base URL *" prop="base_url">
            <ElInput
              v-model="form.base_url"
              placeholder="如 https://open.bigmodel.cn/api/paas/v4（结尾不带 /）"
            />
          </ElFormItem>
          <ElFormItem label="模型名 *" prop="model_name">
            <ElInput v-model="form.model_name" placeholder="如 glm-4-flash / deepseek-chat" />
          </ElFormItem>
          <ElFormItem label="API Key" prop="api_key">
            <ElInput
              v-model="form.api_key"
              type="password"
              show-password
              autocomplete="new-password"
              :placeholder="isEdit ? '留空表示不修改' : '必填'"
              @focus="onKeyFocus"
            />
          </ElFormItem>
          <div class="grid-2">
            <ElFormItem label="超时（秒）">
              <ElInputNumber v-model="form.timeout_seconds" :min="5" :max="300" style="width: 100%" />
            </ElFormItem>
            <ElFormItem label="max_tokens">
              <ElInputNumber v-model="form.max_tokens" :min="64" :max="131072" style="width: 100%" />
            </ElFormItem>
          </div>

          <div class="sec-title">场景路由</div>
          <ElFormItem label="适用场景">
            <ElSelect v-model="form.scenes" multiple placeholder="留空 = 仅作备选" style="width: 100%">
              <ElOption v-for="s in sceneOptions" :key="s.value" :label="s.label" :value="s.value" />
            </ElSelect>
            <div class="hint">
              命中场景优先使用本实例；未命中场景走默认实例或 .env 回落
            </div>
          </ElFormItem>

          <ElFormItem>
            <ElCheckbox v-model="form.enabled">启用</ElCheckbox>
            <span style="margin-left: 24px">
              <ElCheckbox v-model="form.is_default">设为默认实例</ElCheckbox>
            </span>
          </ElFormItem>

          <!-- 测试结果 -->
          <template v-if="testResult">
            <div class="sec-title">测试结果</div>
            <div class="checks">
              <div v-for="(c, i) in testResult.checks" :key="i" :class="['check-row', c.ok ? 'ok' : 'warn']">
                <span :class="['dot', c.ok ? 'ok' : 'warn']" />
                <span class="cname">{{ c.name }}</span>
                <span class="msg">：{{ c.message }}</span>
              </div>
              <div v-if="testResult.latency_ms" class="latency">耗时 {{ testResult.latency_ms }} ms</div>
            </div>
          </template>
        </ElForm>

        <div class="footer">
          <ElButton :loading="testing" @click="onTest">测试连接</ElButton>
          <div class="grow-spacer" />
          <ElButton @click="drawerVisible = false">取消</ElButton>
          <ElButton type="primary" :loading="saving" @click="onSave">保存</ElButton>
        </div>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, resolveComponent, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormRules } from 'element-plus'
import {
  getAIProviderList,
  getAIScenes,
  addAIProvider,
  updateAIProvider,
  deleteAIProvider,
  setDefaultAIProvider,
  testAIProvider,
} from '@/api/aiProvider'

defineOptions({ name: 'AIProviderPage' })

// 全局样式（ArtTable 内渲染的节点拿不到本页 scoped 属性，须全局，见 data-source 同款坑）
const loading = ref(false)
const rows = ref<any[]>([])
const searchKeyword = ref('')
const sceneOptions = ref<{ value: string; label: string }[]>([])
const paginationState = reactive({ current: 1, size: 20, total: 0 })

const drawerVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<any>(null)

const defaultForm = () => ({
  provider_code: '',
  name: '',
  base_url: 'https://',
  protocol: 'openai',
  model_name: '',
  api_key: '',
  scenes: [] as string[],
  max_tokens: 4096,
  timeout_seconds: 60,
  enabled: true,
  is_default: false,
})
const form = reactive(defaultForm())

const rules = reactive<FormRules>({
  provider_code: [
    { required: true, message: '请输入编码', trigger: 'blur' },
    { pattern: /^[a-z][a-z0-9-]{2,63}$/, message: '小写字母、数字和连字符，3-64 位', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  base_url: [
    { required: true, message: '请输入 Base URL', trigger: 'blur' },
    {
      validator: (_r: any, v: string, cb: any) => {
        if (!/^https?:\/\//.test(v)) cb(new Error('需以 http:// 或 https:// 开头'))
        else if (v.endsWith('/')) cb(new Error('结尾不应包含 /'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
  model_name: [{ required: true, message: '请输入模型名', trigger: 'blur' }],
})

const columns = computed(() => [
  { prop: 'provider_code', label: '编码', width: 140 },
  { prop: 'name', label: '名称', width: 160 },
  {
    prop: 'model_name',
    label: '模型',
    width: 160,
    formatter: (row: any) => h('span', { class: 'mono' }, row.model_name),
  },
  {
    prop: 'base_url',
    label: 'Base URL',
    minWidth: 220,
    showOverflowTooltip: true,
  },
  {
    prop: 'scenes',
    label: '场景',
    minWidth: 180,
    formatter: (row: any) =>
      h(
        'span',
        { class: 'scenes' },
        row.scenes?.length ? row.scenes.join('、') : '（备选）'
      ),
  },
  {
    prop: 'status',
    label: '状态',
    width: 150,
    formatter: (row: any) => {
      const tags = []
      tags.push(
        h(
          resolveComponent('ElTag'),
          { type: row.enabled ? 'success' : 'info', size: 'small', effect: 'plain' },
          { default: () => (row.enabled ? '启用' : '停用') }
        )
      )
      if (row.is_default) {
        tags.push(
          h(
            resolveComponent('ElTag'),
            { type: 'primary', size: 'small', effect: 'plain', style: 'margin-left: 4px' },
            { default: () => '默认' }
          )
        )
      }
      return h('div', { style: 'display:flex;align-items:center' }, tags)
    },
  },
  {
    prop: 'health_status',
    label: '健康',
    width: 100,
    formatter: (row: any) => {
      const map: Record<string, { text: string; cls: string }> = {
        normal: { text: '正常', cls: 'ok' },
        abnormal: { text: '异常', cls: 'err' },
        untested: { text: '未测', cls: 'gray' },
      }
      const m = map[row.health_status || 'untested']
      return h('span', { class: ['health', m.cls] }, [
        h('span', { class: ['dot', m.cls] }),
        m.text,
      ])
    },
  },
  {
    prop: 'actions',
    label: '操作',
    width: 300,
    fixed: 'right',
    formatter: (row: any) => {
      const btn = (text: string, onClick: () => void, opts: { type?: string } = {}) =>
        h(
          resolveComponent('ElButton'),
          { link: true, type: (opts.type || 'primary') as any, size: 'small', onClick },
          { default: () => text }
        )
      return h('div', { class: 'actions' }, [
        btn('测试', () => onTestById(row)),
        btn('编辑', () => showDialog(row)),
        btn('设为默认', () => onSetDefault(row)),
        btn(row.enabled ? '停用' : '启用', () => onToggle(row)),
        btn('删除', () => onDelete(row), { type: 'danger' }),
      ])
    },
  },
])

// 健康状态推导：24h 内 last_test_ok=true → normal；false → abnormal；无记录 → untested
function withHealth(row: any) {
  let hs = 'untested'
  if (row.last_test_at) {
    const fresh = Date.now() - new Date(row.last_test_at).getTime() < 24 * 3600 * 1000
    if (row.last_test_ok === true && fresh) hs = 'normal'
    else if (row.last_test_ok === false) hs = 'abnormal'
    else if (row.last_test_ok === true) hs = 'stale'
  }
  return { ...row, health_status: hs }
}

async function getData() {
  loading.value = true
  try {
    const res: any = await getAIProviderList({ search: searchKeyword.value || undefined })
    const payload = res?.data || res
    const items: any[] = payload?.items || []
    rows.value = items.map(withHealth)
    paginationState.total = payload?.total ?? items.length
  } finally {
    loading.value = false
  }
}

async function loadScenes() {
  try {
    const res: any = await getAIScenes()
    sceneOptions.value = res?.data?.scenes || res?.scenes || []
  } catch {
    sceneOptions.value = []
  }
}

function showDialog(row?: any) {
  isEdit.value = !!row
  editingId.value = row?.id ?? null
  testResult.value = null
  Object.assign(form, defaultForm(), row ? { ...row, api_key: '' } : {})
  drawerVisible.value = true
}

function onKeyFocus(e: FocusEvent) {
  if (isEdit.value) {
    ;(e.target as HTMLInputElement).value = ''
    form.api_key = ''
  }
}

async function onTest() {
  testing.value = true
  try {
    let payload: any
    if (isEdit.value && editingId.value) {
      payload = { id: editingId.value }
    } else {
      payload = {
        draft: {
          provider_code: form.provider_code || 'draft',
          name: form.name || 'draft',
          base_url: form.base_url,
          protocol: form.protocol,
          model_name: form.model_name,
          api_key: form.api_key || null,
          scenes: form.scenes,
          max_tokens: form.max_tokens,
          timeout_seconds: form.timeout_seconds,
          enabled: form.enabled,
          is_default: form.is_default,
        },
      }
    }
    const res: any = await testAIProvider(payload)
    const result = res?.data || res
    testResult.value = result
    if (result.ok) ElMessage.success(result.message || '连接成功')
    else ElMessage.warning(result.message || '连接失败')
  } catch (e: any) {
    testResult.value = { ok: false, latency_ms: 0, message: e?.message || '测试请求失败', checks: [] }
  } finally {
    testing.value = false
  }
}

async function onTestById(row: any) {
  ElMessage.info(`正在测试 ${row.provider_code}...`)
  try {
    const res: any = await testAIProvider({ id: row.id })
    const result = res?.data || res
    if (result.ok) ElMessage.success(`${row.provider_code}: ${result.message}`)
    else ElMessage.warning(`${row.provider_code}: ${result.message}`)
    await getData()
  } catch (e: any) {
    ElMessage.error(e?.message || '测试失败')
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload: any = { ...form, api_key: form.api_key || null }
    if (isEdit.value && editingId.value) {
      await updateAIProvider(editingId.value, payload)
    } else {
      await addAIProvider(payload)
    }
    drawerVisible.value = false
    await getData()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onSetDefault(row: any) {
  await ElMessageBox.confirm(`将把「${row.provider_code}」设为默认 AI 实例，继续？`, '设为默认', {
    type: 'warning',
  })
  await setDefaultAIProvider(row.id)
  await getData()
}

async function onToggle(row: any) {
  await updateAIProvider(row.id, { enabled: !row.enabled })
  await getData()
}

async function onDelete(row: any) {
  await ElMessageBox.confirm(`确定删除「${row.provider_code}」？使用该实例的场景将回落默认/环境变量`, '删除确认', {
    type: 'warning',
  })
  await deleteAIProvider(row.id)
  await getData()
}

function handleSizeChange(size: number) {
  paginationState.size = size
  getData()
}
function handleCurrentChange(page: number) {
  paginationState.current = page
  getData()
}

onMounted(() => {
  loadScenes()
  getData()
})
</script>

<style lang="scss">
// ArtTable formatter 渲染节点挂的是 ArtTable 的 scopeId，本页 scoped 样式匹配不到
// （data-source 页同款坑），故用全局 + 页面前缀
.ai-provider-page {
  .toolbar {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 14px;
  }
  .grow-spacer {
    flex: 1;
  }
  .muted {
    color: #888780;
    font-size: 12px;
  }
  .mono {
    font-family: ui-monospace, Menlo, monospace;
  }
  .scenes {
    font-size: 12px;
    color: #5f5e5a;
  }
  .health {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
  }
  .health.ok { color: #639922; }
  .health.err { color: #ef9f27; }
  .health.gray { color: #888780; }
  .health.stale { color: #ef9f27; }
  .dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .dot.ok { background: #639922; }
  .dot.err { background: #ef9f27; }
  .dot.gray { background: #b4b2a9; }
  .dot.stale { background: #ef9f27; }
}
.ai-provider-drawer {
  .drawer-wrap {
    padding: 18px;
  }
  .hint {
    font-size: 11px;
    color: #888780;
    margin-top: 4px;
  }
  .muted {
    color: #888780;
    font-size: 12px;
  }
  .sec-title {
    font-size: 13px;
    font-weight: 500;
    margin: 18px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #f0f0ee;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 12px;
  }
  .footer {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid #f0f0ee;
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .grow-spacer {
    flex: 1;
  }
  .check-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 12px;
    &.ok { color: #3b6d11; }
    &.warn { color: #a2650a; }
  }
  .latency {
    font-size: 11px;
    color: #888780;
    margin-top: 6px;
  }
}
</style>

<style scoped lang="scss">
</style>
