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

        <!-- 右侧：当前分类的表单 -->
        <div class="main">
          <div v-if="activeCategory">
            <div class="main-head">
              <h3>{{ categoryLabel(activeCategory) }} <span class="muted">({{ activeCategory }})</span></h3>
              <ElButton @click="onRestoreDefaults">恢复默认</ElButton>
            </div>

            <!-- 按 group_name 分组展示 -->
            <template v-for="(group, gname) in groupedItems" :key="gname">
              <div class="sec-title">{{ gname || '默认' }}</div>
              <ElForm
                :model="formValues"
                label-width="200px"
                label-position="left"
              >
                <ElFormItem
                  v-for="item in group"
                  :key="item.id"
                  :label="item.label + (item.label.endsWith('*') ? '' : ' *')"
                >
                  <template #label>
                    <span>{{ item.label }}</span>
                    <span
                      v-if="item.effect_scope === 'immediate'"
                      class="effect now"
                    >立即生效</span>
                    <span
                      v-else-if="item.effect_scope === 'next_cycle'"
                      class="effect next"
                    >下周期生效</span>
                    <span
                      v-else-if="item.effect_scope === 'restart'"
                      class="effect restart"
                    >需重启服务</span>
                  </template>
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
                    :rows="4"
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
                    :rows="4"
                    :disabled="!item.editable"
                  />
                  <!-- string (default) -->
                  <ElInput
                    v-else
                    v-model="formValues[item.key]"
                    :disabled="!item.editable"
                    :maxlength="(item.validation && item.validation.maxLength) || undefined"
                    style="width: 320px"
                  />
                  <div v-if="item.help_text" class="hint">{{ item.help_text }}</div>
                </ElFormItem>
              </ElForm>
            </template>

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
  allItems.value.filter((i) => i.category === activeCategory.value)
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

function categoryLabel(c: string) {
  // 简单从已知 cat 推断友好名
  const map: Record<string, string> = {
    alert_governance: '告警治理',
    browsing_detection: '行为检测',
    risk_rules: '风险规则',
    push_rules: '推送规则',
    reports: '报告',
    general: '通用',
    frontend: '前端',
  }
  return map[c] || c
}

async function loadSchema() {
  const res: any = await getConfigSchemas()
  const payload = res?.data || res
  // payload: { items: Item[], groups: Group[] }
  allItems.value = payload?.items || []
  groups.value = payload?.groups || []
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
    if (it.value_type === 'boolean') {
      v = String(v).trim().toLowerCase() in ('true', '1', 'yes', 'on')
    } else if (it.value_type === 'number') {
      v = Number(v) || 0
    } else if (it.value_type === 'json') {
      try {
        v = v ? JSON.parse(v) : {}
      } catch {
        v = {}
      }
    } else if (it.value_type === 'list') {
      v = v ? String(v).split(',').filter(Boolean) : []
    }
    formValues[it.key] = v
  }
}

function onSelectCategory(c: string) {
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
        let v: any = it.default_value ?? ''
        if (it.value_type === 'boolean') {
          v = String(v).trim().toLowerCase() in ('true', '1', 'yes', 'on')
        } else if (it.value_type === 'number') {
          v = Number(v) || 0
        } else if (it.value_type === 'json') {
          try { v = v ? JSON.parse(v) : {} } catch { v = {} }
        } else if (it.value_type === 'list') {
          v = v ? String(v).split(',').filter(Boolean) : []
        }
        formValues[it.key] = v
      }
      ElMessage.success('已恢复默认值（未保存）')
    })
    .catch(() => {})
}

async function onSave() {
  saving.value = true
  try {
    // 把当前分类下所有项的 value 写回 system_configs（PUT 或 POST）
    // 这里简化为逐项调用 addConfig / updateConfig（系统配置 API 已支持）
    const res: any = await getConfigsByCategory(activeCategory.value)
    const existing: any[] = res?.data || res || []
    for (const it of itemsInCategory.value) {
      if (!it.editable) continue
      let v: any = formValues[it.key]
      // 类型转换回字符串
      if (it.value_type === 'boolean') v = v ? 'true' : 'false'
      else if (it.value_type === 'number') v = String(v)
      else if (it.value_type === 'json') v = JSON.stringify(v)
      else if (it.value_type === 'list') v = Array.isArray(v) ? v.join(',') : String(v || '')
      else if (it.value_type === 'password' && !v) continue  // 留空不更新
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
  .layout {
    display: flex;
    gap: 16px;
    align-items: flex-start;
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
  }
  .main-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
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
  .effect {
    float: right;
    font-size: 11px;
    padding: 0 7px;
    border-radius: 4px;
    border: 1px solid;
    line-height: 18px;
    margin-left: 6px;
  }
  .effect.now {
    background: #eaf3de;
    border-color: #97c459;
    color: #3b6d11;
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
  .footer {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid #f0f0ee;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
}
</style>