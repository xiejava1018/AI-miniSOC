<!--
  配置中心（X1E-11 配置中心）
  Schema-driven Form：依据 soc_config_schema 元信息动态渲染表单

  设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §6.4
-->
<template>
  <div class="config-center-page art-full-height">
    <ElCard shadow="never" class="art-table-card">
      <div class="layout">
        <!-- 左侧：分类列表 -->
        <div class="side">
          <div class="side-title">配置分类</div>
          <div class="side-list">
            <div
              v-for="g in groups"
              :key="g.category"
              :class="['item', { active: activeCategory === g.category }]"
              @click="onSelectCategory(g.category)"
            >
              <span class="name">{{ categoryLabel(g.category) }}</span>
              <span class="count">{{ g.count }}</span>
            </div>
            <ElEmpty v-if="groups.length === 0" description="暂无分类" :image-size="60" />
          </div>
        </div>

        <!-- 右侧：当前分类的表单（头部固定，表单区滚动） -->
        <div class="main">
          <div v-if="activeCategory" class="main-inner">
            <div class="main-head">
              <h3>{{ categoryLabel(activeCategory) }}</h3>
              <ElButton @click="onRestoreDefaults">恢复默认</ElButton>
            </div>

            <!-- 表单滚动区 -->
            <div class="form-scroll">
            <!-- 按 group_name 分组展示 -->
            <template v-for="(group, gname) in groupedItems" :key="gname">
              <div class="sec-title">{{ gname || '默认' }}</div>
                <ElForm
                  :model="formValues"
                  label-width="auto"
                  label-position="left"
                >
                <ElFormItem v-for="item in group" :key="item.id" :label="item.label">
                  <!-- boolean -->
                  <ElSwitch
                    v-if="item.value_type === 'boolean'"
                    v-model="formValues[item.key]"
                    :disabled="!item.editable"
                  />
                  <!-- number -->
                  <ElInputNumber
                    v-else-if="item.value_type === 'number'"
                    v-model="formValues[item.key]"
                    :disabled="!item.editable"
                    :min="(item.validation && item.validation.min) || undefined"
                    :max="(item.validation && item.validation.max) || undefined"
                    style="width: 240px"
                  />
                  <!-- password -->
                  <ElInput
                    v-else-if="item.value_type === 'password'"
                    v-model="formValues[item.key]"
                    type="password"
                    show-password
                    :disabled="!item.editable"
                    placeholder="留空表示不修改"
                    autocomplete="new-password"
                    style="width: 320px"
                  />
                  <!-- multiline -->
                  <ElInput
                    v-else-if="item.value_type === 'multiline'"
                    v-model="formValues[item.key]"
                    type="textarea"
                    :autosize="{ minRows: 3, maxRows: 16 }"
                    :disabled="!item.editable"
                    :maxlength="(item.validation && item.validation.maxLength) || undefined"
                  />
                  <!-- list (multi-select) -->
                  <ElSelect
                    v-else-if="item.value_type === 'list' && item.options && item.options.length"
                    v-model="formValues[item.key]"
                    multiple
                    :disabled="!item.editable"
                    style="width: 320px"
                  >
                    <ElOption
                      v-for="o in item.options"
                      :key="o.value"
                      :label="o.label"
                      :value="o.value"
                    />
                  </ElSelect>
                  <!-- json -->
                  <ElInput
                    v-else-if="item.value_type === 'json'"
                    v-model="formValues[item.key]"
                    type="textarea"
                    :autosize="{ minRows: 4, maxRows: 24 }"
                    :disabled="!item.editable"
                    @blur="validateJson(item.key)"
                  />
                  <!-- string (default) -->
                  <ElInput
                    v-else
                    v-model="formValues[item.key]"
                    :disabled="!item.editable"
                    :maxlength="(item.validation && item.validation.maxLength) || undefined"
                    style="width: 320px"
                  />
                  <div
                    v-if="item.help_text || (item.effect_scope && item.effect_scope !== 'immediate') || jsonErrors[item.key]"
                    class="hint"
                  >
                    <span v-if="item.effect_scope === 'next_cycle'" class="effect next">下周期生效</span>
                    <span v-else-if="item.effect_scope === 'restart'" class="effect restart">需重启服务</span>
                    {{ item.help_text }}
                    <span v-if="jsonErrors[item.key]" class="err-inline">{{ jsonErrors[item.key] }}</span>
                  </div>
                </ElFormItem>
              </ElForm>
            </template>

            <!-- 未注册 Schema 的兑底区（规格 §6.4：防止缺 schema 导致配置项不可见） -->
            <template v-if="unregisteredItems.length">
              <div class="sec-title unreg-title">
                未注册配置（{{ unregisteredItems.length }}）
                <span class="muted">— 无 Schema 元信息，谨慎修改；建议向 scripts/seed_config_schema.py 注册</span>
              </div>
              <ElForm :model="unregValues" label-width="auto" label-position="left">
                <ElFormItem v-for="row in unregisteredItems" :key="row.id" :label="row.key">
                  <ElInput
                    v-model="unregValues[row.id]"
                    :type="String(row.value ?? '').length > 80 ? 'textarea' : 'text'"
                    :autosize="{ minRows: 3, maxRows: 16 }"
                    style="width: 100%"
                  />
                  <div class="hint">{{ row.key }}（类型 {{ row.value_type || 'unknown' }}）</div>
                </ElFormItem>
              </ElForm>
            </template>
            </div><!-- /form-scroll -->

            <!-- 取消/保存固定右下角，表单内容滚动 -->
            <div class="footer">
              <ElButton @click="loadConfigValues">取消</ElButton>
              <ElButton type="primary" :loading="saving" @click="onSave">保存</ElButton>
            </div>
          </div>
          <ElEmpty v-else description="请选择左侧分类" />
        </div>
      </div>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getConfigSchemas } from '@/api/configSchema'
import { getConfigsByCategory, addConfig, updateConfig } from '@/api/systemConfig'

defineOptions({ name: 'ConfigCenterPage' })

// Schema 数据
const allItems = ref<Api.ConfigSchema.Item[]>([])
const groups = ref<Api.ConfigSchema.Group[]>([])
const activeCategory = ref<string>('')
const formValues = reactive<Record<string, any>>({})
const saving = ref(false)

const itemsInCategory = computed<Api.ConfigSchema.Item[]>(() =>
  allItems.value.filter(
    (i) =>
      i.category === activeCategory.value &&
      i.group_name !== DEPRECATED_GROUP &&
      i.editable !== false // 只读项（如运行时事实）不在界面展示
  )
)

const groupedItems = computed<Record<string, Api.ConfigSchema.Item[]>>(() => {
  const map: Record<string, Api.ConfigSchema.Item[]> = {}
  for (const it of itemsInCategory.value) {
    const g = it.group_name || '默认'
    ;(map[g] = map[g] || []).push(it)
  }
  // 已按 sort_order 排序（API 排序）
  return map
})

// 当前分类下未注册 schema 的 soc_system_config 行（兑底显示，规格 §6.4）
const unregisteredItems = ref<any[]>([])
const unregValues = reactive<Record<number, string>>({})

// 分类 code → 中文名（全量覆盖，未命中时回退原码）
const CATEGORY_LABELS: Record<string, string> = {
  alert_governance: '告警治理',
  browsing_detection: '行为检测',
  captcha: '登录验证码',
  general: '品牌信息',
  push_rules: '推送规则',
  risk_rules: '风险规则',
  reports: '报告',
  security: '安全策略',
  sync: '数据同步',
  frontend: '前端',
}
function categoryLabel(c: string) {
  return CATEGORY_LABELS[c] || c
}

// 废弃项不展示（group_name = '已废弃'，如 sync.wazuh_api_url 已迁移到数据源管理）
const DEPRECATED_GROUP = '已废弃'

async function loadSchema() {
  const res: any = await getConfigSchemas()
  const payload = res?.data || res
  // payload: { items: Item[], groups: Group[] }
  allItems.value = payload?.items || []
  // 分组在客户端重算（排除废弃项与只读项，左侧计数才准）
  const countMap: Record<string, number> = {}
  for (const it of allItems.value) {
    if (it.group_name === DEPRECATED_GROUP || it.editable === false) continue
    countMap[it.category] = (countMap[it.category] || 0) + 1
  }
  groups.value = Object.keys(countMap).map((c) => ({ category: c, count: countMap[c] }))
  if (!activeCategory.value && groups.value.length) {
    activeCategory.value = groups.value[0].category
    await loadConfigValues()
  }
}

async function loadConfigValues() {
  if (!activeCategory.value) return
  const res: any = await getConfigsByCategory(activeCategory.value)
  const rows: any[] = res?.data || res || []
  // 重置
  for (const k of Object.keys(formValues)) delete formValues[k]
  // 系统配置的值 → 表单值
  for (const it of itemsInCategory.value) {
    const row = rows.find((r: any) => r.key === it.key)
    let v: any = row?.value ?? it.default_value ?? ''
    v = coerce(v, it.value_type)
    formValues[it.key] = v
  }
  // 未注册 schema 的行 → 兑底区（字符串原样展示）
  // 注意排除集用全量 schema（含废弃项）：否则废弃项会从主表单漏到兑底区又显示出来
  const schemaKeys = new Set(
    allItems.value.filter((i) => i.category === activeCategory.value).map((i) => i.key)
  )
  unregisteredItems.value = rows.filter((r: any) => !schemaKeys.has(r.key))
  for (const k of Object.keys(unregValues)) delete unregValues[k]
  for (const r of unregisteredItems.value) unregValues[r.id] = String(r.value ?? '')
}

// 字符串值 → 控件类型转换（boolean/number/json/list）
// 注：原实现 `v in ('true','1',...)` 是 Python 写法，JS 里 'in' 作用于字符串直接
// TypeError，选中含 boolean 项的分类时整个表单加载崩溃（已修）。
function coerce(v: any, valueType: string) {
  if (valueType === 'boolean') {
    return ['true', '1', 'yes', 'on'].includes(String(v).trim().toLowerCase())
  }
  if (valueType === 'number') {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }
  if (valueType === 'json') {
    if (typeof v === 'object' && v !== null) return JSON.stringify(v, null, 2)
    try { return v ? JSON.stringify(JSON.parse(v), null, 2) : '{}' } catch { return String(v ?? '') }
  }
  if (valueType === 'list') {
    return Array.isArray(v) ? v : (v ? String(v).split(',').filter(Boolean) : [])
  }
  return v ?? ''
}

async function onSelectCategory(c: string) {
  activeCategory.value = c
  loadConfigValues()
}

function onRestoreDefaults() {
  ElMessageBox.confirm('将当前分类的全部可编辑项恢复为 schema 默认值，确认？', '恢复默认', {
    type: 'warning',
  })
    .then(() => {
      for (const it of itemsInCategory.value) {
        if (!it.editable) continue
        formValues[it.key] = coerce(it.default_value ?? '', it.value_type)
      }
      ElMessage.success('已恢复默认值（未保存）')
    })
    .catch(() => {})
}

// JSON 失焦校验（规格 §6.4：json 类型需失焦时格式校验）
const jsonErrors = reactive<Record<string, string>>({})
function validateJson(key: string) {
  const raw = String(formValues[key] ?? '').trim()
  if (!raw) { delete jsonErrors[key]; return true }
  try { JSON.parse(raw); delete jsonErrors[key]; return true }
  catch (e: any) { jsonErrors[key] = `JSON 格式错误: ${e?.message || ''}`; return false }
}

async function onSave() {
  saving.value = true
  try {
    // json 类型先校验格式，不合法禁止提交
    const jsonItems = itemsInCategory.value.filter((i) => i.value_type === 'json')
    const bad = jsonItems.find((i) => !validateJson(i.key))
    if (bad) {
      ElMessage.error(`「${bad.label}」不是合法的 JSON，请修正后保存`)
      return
    }
    // 把当前分类下所有项的 value 写回 system_configs（PUT 或 POST）
    // 这里简化为逐项调用 addConfig / updateConfig（系统配置 API 已支持）
    const res: any = await getConfigsByCategory(activeCategory.value)
    const existing: any[] = res?.data || res || []
    // 兑底区未注册项：值有变化的才提交
    for (const r of unregisteredItems.value) {
      if (unregValues[r.id] !== String(r.value ?? '')) {
        await updateConfig(r.id, { value: unregValues[r.id] })
      }
    }
    for (const it of itemsInCategory.value) {
      if (!it.editable) continue
      let v: any = formValues[it.key]
      // 类型转换回字符串
      if (it.value_type === 'boolean') v = v ? 'true' : 'false'
      else if (it.value_type === 'number') v = String(v)
      // json：表单里已是字符串，校验通过后原样提交
      else if (it.value_type === 'list') v = Array.isArray(v) ? v.join(',') : String(v || '')
      // 密码/敏感字段留空不修改（规格 §6.4：sensitive 或 password 类型）
      else if ((it.value_type === 'password' || it.sensitive) && !v) continue
      const row = existing.find((r: any) => r.key === it.key)
      if (row) {
        await updateConfig(row.id, { value: String(v ?? '') })
      } else {
        await addConfig({
          category: activeCategory.value,
          key: it.key,
          value: String(v ?? ''),
          value_type: it.value_type,
          is_encrypted: false,
          description: it.help_text || null,
        } as any)
      }
    }
    ElMessage.success('已保存（可能延迟 60s 生效）')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadSchema)
</script>

<style scoped lang="scss">
.config-center-page {
  padding: 16px;
  // 高度链：页面定高(art-full-height) → 卡片 flex → body 100% → layout → main
  // 左侧分类自然高度，右侧表单区头部固定、内容滚动
  .layout {
    display: flex;
    gap: 16px;
    align-items: stretch;
    height: 100%;
  }
  .side {
    width: 220px;
    flex-shrink: 0;
  }
  .side-title {
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 10px;
    color: #5f5e5a;
  }
  .side-list {
    background: #fafaf8;
    border-radius: 8px;
    padding: 6px;
  }
  .item {
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    color: #2c2c2a;
    display: flex;
    justify-content: space-between;
    align-items: center;
    &:hover {
      background: #f1efe8;
    }
  }
  .item.active {
    background: #e6f1fb;
    color: #185fa5;
    font-weight: 500;
  }
  .item .count {
    font-size: 11px;
    color: #888780;
  }
  .main {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .main-inner {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  // 表头（分类名 + 恢复默认）固定，表单区在容器内滚动
  // 自适应滚动区：内容短时高度=内容（按钮就近跟随），内容长时封顶滚动（按钮落右下角）
  .form-scroll {
    flex: 0 1 auto;
    min-height: 0;
    max-height: 100%;
    overflow-y: auto;
    padding-right: 6px;
  }
  .main-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-shrink: 0;
  }
  .main-head h3 {
    font-size: 14px;
    font-weight: 500;
    margin: 0;
  }
  .muted {
    color: #888780;
    font-weight: 400;
    font-size: 12px;
  }
  .sec-title {
    font-size: 13px;
    font-weight: 500;
    margin: 18px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #f0f0ee;
  }
  .hint {
    font-size: 11px;
    color: #888780;
    margin-top: 4px;
  }
  .hint.err {
    color: #e24b4a;
  }
  // 生效方式徽标：仅非立即生效项展示（下周期/需重启），位于提示行内不占标签位
  .effect {
    display: inline-block;
    font-size: 11px;
    padding: 0 7px;
    border-radius: 4px;
    border: 1px solid;
    line-height: 18px;
    margin-right: 8px;
    vertical-align: middle;
  }
  .effect.next {
    background: #faeeda;
    border-color: #ef9f27;
    color: #854f0b;
  }
  .effect.restart {
    background: #fcebeb;
    border-color: #f09595;
    color: #a32d2d;
  }
  .err-inline {
    color: #e24b4a;
    margin-left: 8px;
  }
  .sec-title.unreg-title {
    margin-top: 28px;
    border-bottom: 1px dashed #e6a23c;
    color: #a2650a;
  }
  .footer {
    margin-top: 12px;
    padding-top: 4px;
    flex-shrink: 0;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  // 表单短时按钮跟随内容不至于太远：容器底部对齐到内容结束处
  .main-inner {
    justify-content: flex-start;
  }
}
</style>