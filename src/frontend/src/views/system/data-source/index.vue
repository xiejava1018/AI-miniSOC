<!--
  数据源管理（X1E-11 配置中心）

  设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §6.2 / §6.3
-->
<template>
  <div class="data-source-page art-full-height">
    <ElCard shadow="never" class="art-table-card">
      <!-- 工具栏 -->
      <div class="toolbar">
        <ElSelect
          v-model="filterType"
          placeholder="全部类型"
          clearable
          style="width: 160px"
          @change="getData"
        >
          <ElOption
            v-for="t in typeOptions"
            :key="t.value"
            :label="t.label"
            :value="t.value"
          />
        </ElSelect>
        <ElInput
          v-model="searchKeyword"
          placeholder="搜索编码或名称"
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
        <ElButton @click="onBatchTest" :loading="batchTesting">批量测试</ElButton>
        <ElButton type="primary" @click="onAdd">+ 新增数据源</ElButton>
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

    </ElCard>

    <!-- 抽屉（新增/编辑） -->
    <ElDrawer
      v-model="drawerVisible"
      :direction="rtl"
      :size="720"
      :with-header="false"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <div class="drawer-wrap">
        <div class="drawer-head">
          <h3>{{ isEdit ? '编辑数据源' : '新增数据源' }}</h3>
          <span class="close" @click="drawerVisible = false">✕</span>
        </div>
        <div class="muted">字段随类型动态变化；保存后连接参数立即生效（60s 内）</div>

        <!-- 基本信息 -->
        <div class="sec-title">基本信息</div>
        <ElForm
          ref="formRef"
          :model="form"
          :rules="rules"
          label-width="110px"
          label-position="top"
        >
          <div class="grid-2">
            <ElFormItem label="数据源编码 *" prop="source_code">
              <ElInput
                v-model="form.source_code"
                :disabled="isEdit"
                placeholder="小写字母数字连字符，3-64 位"
              />
            </ElFormItem>
            <ElFormItem label="数据源类型 *" prop="source_type">
              <ElSelect
                v-model="form.source_type"
                :disabled="isEdit"
                placeholder="选择类型"
                style="width: 100%"
                @change="onTypeChange"
              >
                <ElOption
                  v-for="t in typeOptions"
                  :key="t.value"
                  :label="t.label"
                  :value="t.value"
                />
              </ElSelect>
            </ElFormItem>
          </div>
          <ElFormItem label="显示名称 *" prop="name">
            <ElInput v-model="form.name" placeholder="如 生产 Wazuh（192.168.0.40）" />
          </ElFormItem>

          <!-- 连接参数 -->
          <div class="sec-title">连接参数</div>
          <ElFormItem label="服务地址 *" prop="endpoint">
            <ElInput v-model="form.endpoint" placeholder="以 http:// 或 https:// 开头" />
          </ElFormItem>
          <div class="grid-3">
            <ElFormItem label="认证方式">
              <ElSelect v-model="form.auth_type" style="width: 100%">
                <ElOption label="Basic 用户名密码" value="basic" />
                <ElOption label="Token" value="token" />
                <ElOption label="API Key" value="apikey" />
                <ElOption label="无" value="none" />
              </ElSelect>
            </ElFormItem>
            <ElFormItem label="超时（秒）">
              <ElInputNumber v-model="form.timeout_seconds" :min="1" :max="300" style="width: 100%" />
            </ElFormItem>
            <ElFormItem label="重试次数">
              <ElInputNumber v-model="form.retry_times" :min="0" :max="10" style="width: 100%" />
            </ElFormItem>
          </div>
          <ElFormItem v-if="form.auth_type !== 'none'" label="用户名">
            <ElInput v-model="form.auth_username" placeholder="可选" />
          </ElFormItem>
          <ElFormItem v-if="form.auth_type !== 'none'" label="密码 / 密钥">
            <ElInput
              v-model="form.auth_secret"
              type="password"
              show-password
              :placeholder="isEdit ? '留空表示不修改' : '必填'"
              autocomplete="new-password"
              @focus="onPasswordFocus"
            />
            <div class="hint">编辑态显示占位符；留空表示不修改</div>
          </ElFormItem>
          <ElFormItem>
            <ElCheckbox v-model="form.verify_ssl">校验 SSL 证书</ElCheckbox>
            <span style="margin-left: 24px">
              <ElCheckbox v-model="form.enabled">启用此数据源</ElCheckbox>
            </span>
            <span style="margin-left: 24px">
              <ElCheckbox v-model="form.is_default">设为同类型默认实例</ElCheckbox>
            </span>
          </ElFormItem>

          <!-- 测试结果 -->
          <div class="sec-title">
            测试结果
            <span v-if="lastTestedAt" class="muted" style="font-size: 11px; margin-left: 8px">
              测试于 {{ lastTestedAt }}
            </span>
          </div>
          <div v-if="testResult" class="checks">
            <div
              v-for="(c, i) in testResult.checks"
              :key="i"
              :class="['check-row', c.ok ? 'ok' : 'warn']"
            >
              <span :class="['dot', c.ok ? 'ok' : 'warn']" />
              <span class="name">{{ c.name }}</span>
              <span class="msg">：{{ c.message }}</span>
            </div>
            <div v-if="testResult.latency_ms" class="latency">
              耗时 {{ testResult.latency_ms }} ms
            </div>
          </div>
          <div v-else class="muted" style="padding: 8px 0">
            点击「测试连接」验证参数
          </div>

          <div class="footer">
            <ElButton :loading="testing" @click="onTest">测试连接</ElButton>
            <ElButton @click="drawerVisible = false">取消</ElButton>
            <ElButton
              type="primary"
              :loading="submitting"
              @click="onSubmit"
            >
              保存
            </ElButton>
          </div>
        </ElForm>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, resolveComponent, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getDataSourceList,
  getDataSourceTypes,
  addDataSource,
  updateDataSource,
  deleteDataSource,
  toggleDataSource,
  setDefaultDataSource,
  testDataSourceConnection,
} from '@/api/dataSource'

defineOptions({ name: 'DataSourcePage' })

const rtl = 'rtl'

// 类型选项
const typeOptions = ref<Api.DataSource.TypeItem[]>([])
const filterType = ref<string>('')
const searchKeyword = ref<string>('')

const columns = ref<any[]>([
  {
    prop: 'source_code',
    label: '编码',
    width: 140,
    formatter: (row: Api.DataSource.Item) =>
      h('span', { class: 'code' }, row.source_code),
  },
  { prop: 'source_type', label: '类型', width: 100 },
  { prop: 'name', label: '名称', width: 180 },
  {
    prop: 'endpoint',
    label: '服务地址',
    formatter: (row: Api.DataSource.Item) =>
      h('span', { class: 'code muted', style: 'font-size: 12px' }, row.endpoint),
  },
  {
    prop: 'flags',
    label: '状态',
    width: 130,
    formatter: (row: Api.DataSource.Item) => {
      const tags: any[] = []
      if (row.is_default) {
        tags.push(
          h(resolveComponent('ElTag'), { type: 'primary', size: 'small', effect: 'plain' }, { default: () => '默认' })
        )
      }
      tags.push(
        h(
          resolveComponent('ElTag'),
          {
            type: row.enabled ? 'success' : 'info',
            size: 'small',
            effect: 'plain',
            style: 'margin-left: 4px',
          },
          { default: () => (row.enabled ? '启用' : '停用') }
        )
      )
      return h('div', { style: 'display: flex; align-items: center' }, tags)
    },
  },
  {
    prop: 'health_status',
    label: '健康',
    width: 100,
    formatter: (row: Api.DataSource.Item) => {
      const map: Record<string, { text: string; cls: string }> = {
        normal: { text: '正常', cls: 'ok' },
        abnormal: { text: '异常', cls: 'err' },
        untested: { text: '未测', cls: 'gray' },
        stale: { text: '过期', cls: 'warn' },
      }
      const m = map[row.health_status || 'untested']
      // 在外层 span 上加 cls，以便同步设置文本颜色（不只点）
      return h('span', { class: ['health', m.cls] }, [
        h('span', { class: ['dot', m.cls] }),
        m.text,
      ])
    },
  },
  {
    prop: 'actions',
    label: '操作',
    width: 380,
    fixed: 'right',
    formatter: (row: Api.DataSource.Item) => {
      const link = (text: string, onClick: () => void, opts: { danger?: boolean } = {}) =>
        h(
          'span',
          {
            class: 'link',
            // 显式 cursor: pointer：原先靠 .actions .link CSS 生效，但 flex 布局下偶尔被
            // inherit 覆盖（实测部分浏览器 hover 仍为 text）。inline 写死不依赖 class 解析。
            style: `margin-left: 10px; cursor: pointer;${opts.danger ? ' color:#e24b4a;' : ''}`,
            onClick,
          },
          text
        )
      return h('div', { class: 'actions' }, [
        h('span', { class: 'link', onClick: () => onTestById(row) }, '测试'),
        link('编辑', () => onEdit(row)),
        // 「设为默认」改用提示确认（生产切换默认源影响 resolver）
        link('设为默认', () => onSetDefault(row)),
        link(row.enabled ? '停用' : '启用', () => onToggle(row), {
          danger: row.enabled,
        }),
        link('删除', () => onDelete(row), { danger: true }),
      ])
    },
  },
])

const data = ref<Api.DataSource.Item[]>([])
const loading = ref(false)
const pagination = reactive({ current: 1, size: 20, total: 0, sizeChange: handleSizeChange, currentChange: handleCurrentChange })

async function getData() {
  loading.value = true
  try {
    const res: any = await getDataSourceList({
      page: pagination.current,
      page_size: pagination.size,
      source_type: (filterType.value || undefined) as any,
      search: searchKeyword.value || undefined,
    })
    // 后端响应包装：{ code, msg, data: { total, items, page, page_size } }
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

// 当前生效来源面板已移除（设计变更：仅在「数据源管理」操作列内做启停/默认切换，不再展示全局来源汇总）。
// /api/v1/data-sources/resolve-status 接口保留（后续 dashboard / data-health 等模块可能复用）。

onMounted(async () => {
  const res: any = await getDataSourceTypes()
  typeOptions.value = (res?.data || res?.items || res || []) as Api.DataSource.TypeItem[]
  await getData()
})

// ------------ 抽屉表单 ------------

const drawerVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const submitting = ref(false)
const testing = ref(false)
const batchTesting = ref(false)
const testResult = ref<Api.DataSource.TestResult | null>(null)
const lastTestedAt = ref<string>('')

const defaultForm = () => ({
  source_code: '',
  source_type: 'wazuh' as Api.DataSource.SourceType,
  name: '',
  endpoint: 'https://',
  auth_type: 'basic' as Api.DataSource.AuthType,
  auth_username: '',
  auth_secret: '',
  verify_ssl: false,
  timeout_seconds: 30,
  retry_times: 3,
  retry_backoff_seconds: 2,
  enabled: true,
  is_default: false,
  config_json: {} as Record<string, any>,
})

const form = reactive(defaultForm())

const rules = reactive<FormRules>({
  source_code: [
    { required: true, message: '请输入数据源编码', trigger: 'blur' },
    {
      pattern: /^[a-z][a-z0-9-]{2,63}$/,
      message: '编码只能包含小写字母、数字和连字符，3-64 位',
      trigger: 'blur',
    },
  ],
  source_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  endpoint: [
    { required: true, message: '请输入服务地址', trigger: 'blur' },
    {
      validator(_: any, value: string, cb: (err?: Error) => void) {
        if (!value) return cb()
        if (!/^https?:\/\//.test(value)) return cb(new Error('地址需以 http:// 或 https:// 开头'))
        if (value.endsWith('/')) return cb(new Error('地址结尾不应包含 /'))
        cb()
      },
      trigger: 'blur',
    },
  ],
})

function onAdd() {
  Object.assign(form, defaultForm())
  isEdit.value = false
  editingId.value = null
  testResult.value = null
  lastTestedAt.value = ''
  drawerVisible.value = true
}

function onEdit(row: Api.DataSource.Item) {
  Object.assign(form, {
    source_code: row.source_code,
    source_type: row.source_type,
    name: row.name,
    endpoint: row.endpoint,
    auth_type: row.auth_type,
    auth_username: row.auth_username || '',
    auth_secret: '',  // 编辑态留空
    verify_ssl: row.verify_ssl,
    timeout_seconds: row.timeout_seconds,
    retry_times: row.retry_times,
    retry_backoff_seconds: row.retry_backoff_seconds,
    enabled: row.enabled,
    is_default: row.is_default,
    config_json: row.config_json || {},
  })
  isEdit.value = true
  editingId.value = row.id
  testResult.value = null
  lastTestedAt.value = ''
  drawerVisible.value = true
}

function onTypeChange() {
  // 切换类型时根据默认值预填 endpoint 与 auth_type
  const t = typeOptions.value.find((x) => x.value === form.source_type)
  if (t) {
    form.endpoint = `${form.endpoint.startsWith('http') ? form.endpoint.split('://')[0] : 'https'}://`
    if (t.auth_types.length && !t.auth_types.includes(form.auth_type)) {
      form.auth_type = t.auth_types[0] as any
    }
  }
}

function onPasswordFocus(e: FocusEvent) {
  // 编辑态聚焦清空占位符
  if (isEdit.value) {
    ;(e.target as HTMLInputElement).value = ''
    form.auth_secret = ''
  }
}

async function onTest() {
  testing.value = true
  try {
    const payload: any = {
      draft: {
        source_code: form.source_code || 'draft',
        source_type: form.source_type,
        name: form.name || 'draft',
        endpoint: form.endpoint,
        auth_type: form.auth_type,
        auth_username: form.auth_username || null,
        auth_secret: form.auth_secret || null,
        verify_ssl: form.verify_ssl,
        timeout_seconds: form.timeout_seconds,
        retry_times: form.retry_times,
        retry_backoff_seconds: form.retry_backoff_seconds,
        enabled: form.enabled,
        is_default: form.is_default,
        config_json: form.config_json,
      },
    }
    const res: any = await testDataSourceConnection(payload)
    const result: Api.DataSource.TestResult = res?.data || res
    testResult.value = result
    lastTestedAt.value = new Date().toLocaleString('zh-CN')
    if (result.ok) {
      ElMessage.success(result.message || '连接成功')
    } else {
      ElMessage.warning(result.message || '连接失败')
    }
  } catch (e: any) {
    testResult.value = {
      ok: false,
      latency_ms: 0,
      message: e?.message || '测试请求失败',
      checks: [],
      details: {},
    }
  } finally {
    testing.value = false
  }
}

async function onTestById(row: Api.DataSource.Item) {
  ElMessage.info(`正在测试 ${row.source_code}...`)
  try {
    const res: any = await testDataSourceConnection({ id: row.id })
    const result: Api.DataSource.TestResult = res?.data || res
    if (result.ok) {
      ElMessage.success(`${row.source_code}：${result.message}`)
    } else {
      ElMessage.warning(`${row.source_code}：${result.message}`)
    }
    await getData()
  } catch (e: any) {
    ElMessage.error(`${row.source_code}：${e?.message || '测试失败'}`)
  }
}

async function onBatchTest() {
  batchTesting.value = true
  try {
    for (const row of data.value) {
      await onTestById(row)
    }
  } finally {
    batchTesting.value = false
  }
}

async function onSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const payload: Api.DataSource.Payload = {
      source_code: form.source_code,
      source_type: form.source_type,
      name: form.name,
      endpoint: form.endpoint,
      auth_type: form.auth_type,
      auth_username: form.auth_username || null,
      auth_secret: form.auth_secret || null,
      verify_ssl: form.verify_ssl,
      timeout_seconds: form.timeout_seconds,
      retry_times: form.retry_times,
      retry_backoff_seconds: form.retry_backoff_seconds,
      enabled: form.enabled,
      is_default: form.is_default,
      config_json: form.config_json,
    }
    if (isEdit.value && editingId.value) {
      await updateDataSource(editingId.value, payload)
      ElMessage.success('已保存，🟢 立即生效')
    } else {
      await addDataSource(payload)
      ElMessage.success('已保存，🟢 立即生效')
    }
    drawerVisible.value = false
    await getData()
  } catch (e: any) {
    // 二次确认：测试未通过仍要保存
    if (testResult.value && !testResult.value.ok) {
      ElMessage.warning('测试未通过，请确认是否仍要保存')
    }
  } finally {
    submitting.value = false
  }
}

async function onSetDefault(row: Api.DataSource.Item) {
  if (row.is_default) {
    ElMessage.info(`${row.source_code} 已是默认实例`)
    return
  }
  try {
    await ElMessageBox.confirm(
      `将 ${row.source_code} 设为该类型的默认实例？\n原默认实例将被替换，业务层 60s 内生效。`,
      '切换默认',
      { type: 'info' }
    )
    await setDefaultDataSource(row.id)
    ElMessage.success(`已将 ${row.source_code} 设为默认`)
    await getData()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(err?.message || '操作失败')
  }
}

async function onToggle(row: Api.DataSource.Item) {
  const next = !row.enabled
  try {
    await toggleDataSource(row.id, next)
    ElMessage.success(`${row.source_code} 已${next ? '启用' : '停用'}`)
    await getData()
  } catch (err: any) {
    ElMessage.error(err?.message || '操作失败')
  }
}

async function onDelete(row: Api.DataSource.Item) {
  try {
    await ElMessageBox.confirm(
      `确定删除数据源 ${row.source_code}？\n删除不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
    await deleteDataSource(row.id)
    ElMessage.success(`已删除 ${row.source_code}`)
    await getData()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(err?.message || '删除失败')
  }
}
</script>

<style scoped lang="scss">
.data-source-page {
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

  .actions .link {
    color: #185fa5;
    cursor: pointer;
    margin-right: 10px;
  }
  .health {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12px;
  }
  // 健康列文本颜色与点同步：
  // 正常=绿、异常=橙、未测=灰、过期=橙（与 design prototype 配色一致）
  .health.ok    { color: #639922; }
  .health.err   { color: #ef9f27; }
  .health.gray  { color: #888780; }
  .health.warn  { color: #ef9f27; }
  .dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .dot.ok { background: #639922; }
  .dot.err { background: #ef9f27; }
  .dot.gray { background: #b4b2a9; }
  .dot.warn { background: #ef9f27; }
}

.drawer-wrap {
  padding: 18px;
  background: #fff;
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.drawer-head h3 {
  font-size: 14px;
  font-weight: 500;
  margin: 0;
}
.drawer-head .close {
  cursor: pointer;
  color: #888780;
}
.muted {
  color: #888780;
  font-size: 12px;
  margin-bottom: 14px;
}
.sec-title {
  font-size: 13px;
  font-weight: 500;
  margin: 18px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0ee;
}
.sec-title:first-of-type {
  margin-top: 0;
}
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.grid-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
}
.hint {
  font-size: 11px;
  color: #888780;
  margin-top: 4px;
}
.checks {
  border: 1px solid #e3e3e0;
  border-radius: 8px;
  padding: 12px;
  background: #fafaf8;
}
.check-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}
.check-row.warn {
  color: #854f0b;
}
.check-row .name {
  font-weight: 500;
}
.latency {
  margin-top: 6px;
  font-size: 11px;
  color: #888780;
}
.footer {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #f0f0ee;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>