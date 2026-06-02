<template>
  <div class="system-config-page art-full-height" id="table-full-screen">
    <ElCard shadow="never" class="art-table-card config-card">
      <ElRow :gutter="16" class="config-row">
        <!-- 左侧：分类列表 -->
        <ElCol :span="6" class="category-col">
          <div class="category-header">
            <span class="title">配置分类</span>
            <ElButton link type="primary" @click="refreshCategories">刷新</ElButton>
          </div>
          <div class="category-list">
            <div
              v-for="c in categories"
              :key="c.category"
              class="category-item"
              :class="{ active: activeCategory === c.category }"
              @click="selectCategory(c.category)"
            >
              <ElIcon><Folder /></ElIcon>
              <span class="name">{{ c.category }}</span>
              <ElBadge :value="c.count" class="count-badge" type="primary" />
            </div>
            <ElEmpty
              v-if="categories.length === 0"
              description="暂无配置分类"
              :image-size="60"
            />
          </div>
        </ElCol>

        <!-- 右侧：当前分类下的配置项 -->
        <ElCol :span="18" class="config-col">
          <div class="search-wrapper">
            <ArtSearchBar
              v-model="searchParams"
              :items="searchItems"
              @reset="resetSearch"
              @search="searchData"
            />
          </div>

          <ElCard shadow="never" class="art-table-card config-table-card">
            <ArtTableHeader
              v-model:columns="columnChecks"
              @refresh="refreshAll"
            >
              <template #left>
                <ElButton @click="showDialog('add')" v-ripple>新增配置</ElButton>
              </template>
            </ArtTableHeader>

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
        </ElCol>
      </ElRow>
    </ElCard>

    <!-- 新增/编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? '新增配置' : '编辑配置'"
      width="640px"
      align-center
      :close-on-click-modal="false"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-width="100px">
        <ElFormItem label="分类" prop="category">
          <ElInput
            v-model="form.category"
            :disabled="dialogType === 'edit'"
            placeholder="如: general / security / captcha / sync"
          />
        </ElFormItem>
        <ElFormItem label="键" prop="key">
          <ElInput
            v-model="form.key"
            :disabled="dialogType === 'edit'"
            placeholder="英文标识，如 session_timeout_minutes"
          />
        </ElFormItem>
        <ElFormItem label="值类型" prop="value_type">
          <ElSelect
            v-model="form.value_type"
            :disabled="dialogType === 'edit'"
            style="width: 100%"
            @change="onValueTypeChange"
          >
            <ElOption label="字符串 (string)" value="string" />
            <ElOption label="数字 (number)" value="number" />
            <ElOption label="布尔 (boolean)" value="boolean" />
            <ElOption label="JSON (json)" value="json" />
            <ElOption label="密码 (password)" value="password" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="配置值" prop="value">
          <ElSwitch
            v-if="form.value_type === 'boolean'"
            v-model="form.valueBool"
          />
          <ElInputNumber
            v-else-if="form.value_type === 'number'"
            v-model="form.valueNumber"
            style="width: 100%"
          />
          <ElInput
            v-else
            v-model="form.value"
            :type="form.value_type === 'json' ? 'textarea' : 'text'"
            :rows="form.value_type === 'json' ? 4 : 1"
            :show-password="form.value_type === 'password'"
            placeholder="配置值"
          />
        </ElFormItem>
        <ElFormItem label="是否加密">
          <ElSwitch v-model="form.is_encrypted" />
        </ElFormItem>
        <ElFormItem label="说明">
          <ElInput
            v-model="form.description"
            type="textarea"
            :rows="2"
            placeholder="配置项说明"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, h, resolveComponent, nextTick, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getConfigList,
  getConfigCategories,
  addConfig,
  updateConfig,
  deleteConfig,
} from '@/api/systemConfig'
import { useTable } from '@/composables/useTable'
import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
import type { SearchFormItem } from '@/types'

defineOptions({ name: 'SystemConfig' })

// ========== 左侧分类 ==========
interface CategoryInfo {
  category: string
  count: number
}
const categories = ref<CategoryInfo[]>([])
const activeCategory = ref<string>('')

const refreshCategories = async () => {
  try {
    const res: any = await getConfigCategories()
    categories.value = Array.isArray(res) ? res : []
    // 默认选中第一个分类
    if (categories.value.length > 0 && !activeCategory.value) {
      activeCategory.value = categories.value[0].category
    } else if (
      activeCategory.value &&
      !categories.value.find((c) => c.category === activeCategory.value)
    ) {
      activeCategory.value = categories.value[0]?.category || ''
    }
  } catch (err) {
    console.error('加载分类失败:', err)
  }
}

const selectCategory = (cat: string) => {
  activeCategory.value = cat
  // useTable 不支持直接改 searchParams.category 触发刷新（因为 searchParams 是 reactive），
  // 显式重置 searchParams 并刷新
  searchParams.category = cat
  searchParams.search = ''
  refreshAll()
}

// ========== 右侧表格 ==========
const tableApi = useTable<any>({
  core: {
    apiFn: getConfigList,
    apiParams: {
      page: 1,
      page_size: 20,
      category: '',
      search: '',
    },
    paginationKey: {
      current: 'page',
      size: 'page_size'
    },
    columnsFactory: () => [
      {
        prop: 'category',
        label: '分类',
        align: 'center',
        width: 100,
        formatter: (row: any) => row.category || '--',
      },
      {
        prop: 'key',
        label: '键',
        align: 'center',
        minWidth: 180,
        formatter: (row: any) =>
          h('span', { class: 'config-key' }, row.key || '--'),
      },
      {
        prop: 'value',
        label: '值',
        align: 'center',
        minWidth: 180,
        formatter: (row: any) => formatValueCell(row),
      },
      {
        prop: 'value_type',
        label: '类型',
        align: 'center',
        width: 90,
        formatter: (row: any) =>
          h(
            resolveComponent('ElTag'),
            { size: 'small', type: 'info', effect: 'light' },
            { default: () => row.value_type || '--' }
          ),
      },
      {
        prop: 'is_encrypted',
        label: '加密',
        align: 'center',
        width: 70,
        formatter: (row: any) =>
          row.is_encrypted
            ? h(resolveComponent('ElTag'), { size: 'small', type: 'warning' }, { default: () => '是' })
            : h('span', { style: 'color: #999' }, '否'),
      },
      {
        prop: 'description',
        label: '说明',
        align: 'center',
        minWidth: 200,
        showOverflowTooltip: true,
        formatter: (row: any) => row.description || '--',
      },
      {
        prop: 'updated_at',
        label: '更新时间',
        align: 'center',
        width: 170,
        formatter: (row: any) => {
          if (!row.updated_at) return '--'
          return new Date(row.updated_at).toLocaleString('zh-CN')
        },
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
              type: 'edit',
              style: 'margin-right: 8px;',
              onClick: () => showDialog('edit', row),
            }),
            h(ArtButtonTable, {
              type: 'delete',
              onClick: () => handleDelete(row),
            }),
          ]),
      },
    ],
  },
  hooks: {
    onError: (error) => ElMessage.error(error.message),
  },
})

const {
  data: tableData,
  loading: isLoading,
  columns,
  columnChecks,
  pagination: paginationState,
  searchParams,
  getData: searchData,
  resetSearchParams: resetSearch,
  handleSizeChange: onPageSizeChange,
  handleCurrentChange: onCurrentPageChange,
  refreshAll,
} = tableApi as any

const searchItems = computed<SearchFormItem[]>(() => [
  {
    label: '搜索',
    key: 'search',
    type: 'input',
    span: 8,
    clearable: true,
    placeholder: '搜索键 / 值 / 说明',
  },
])

// 切换分类时同步 searchParams
watch(
  () => searchParams.category,
  (val) => {
    if (val !== activeCategory.value) {
      activeCategory.value = val
    }
  }
)

// ========== 表格辅助函数 ==========
function formatValueCell(row: any) {
  if (row.value === null || row.value === undefined || row.value === '') {
    return h('span', { style: 'color: #999' }, '--')
  }
  if (row.value_type === 'password' || row.is_encrypted) {
    return h('span', { class: 'masked-value' }, '••••••••')
  }
  if (row.value_type === 'boolean') {
    const isTrue = String(row.value) === 'true'
    return h(
      resolveComponent('ElTag'),
      { size: 'small', type: isTrue ? 'success' : 'info', effect: 'light' },
      { default: () => (isTrue ? 'true' : 'false') }
    )
  }
  return h('span', {}, String(row.value))
}

// ========== 弹窗 ==========
const dialogType = ref<'add' | 'edit'>('add')
const dialogVisible = ref(false)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  id: 0,
  category: '',
  key: '',
  value: '',
  valueBool: false,
  valueNumber: 0,
  value_type: 'string' as Api.SystemConfig.ValueType,
  is_encrypted: false,
  description: '',
})

const rules = reactive<FormRules>({
  category: [
    { required: true, message: '请输入分类', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅支持英文、数字、下划线、中划线', trigger: 'blur' },
  ],
  key: [
    { required: true, message: '请输入键', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_.-]+$/, message: '仅支持英文、数字、下划线、点、中划线', trigger: 'blur' },
  ],
  value_type: [{ required: true, message: '请选择值类型', trigger: 'change' }],
})

const showDialog = (type: 'add' | 'edit', row?: any) => {
  dialogType.value = type
  dialogVisible.value = true

  nextTick(() => {
    formRef.value?.clearValidate()
    if (type === 'edit' && row) {
      form.id = row.id
      form.category = row.category
      form.key = row.key
      form.value_type = row.value_type || 'string'
      form.is_encrypted = row.is_encrypted ?? false
      form.description = row.description || ''
      // 还原不同类型值
      if (row.value_type === 'boolean') {
        form.valueBool = String(row.value) === 'true'
        form.value = ''
        form.valueNumber = 0
      } else if (row.value_type === 'number') {
        form.valueNumber = Number(row.value) || 0
        form.value = ''
        form.valueBool = false
      } else {
        form.value = row.value ?? ''
        form.valueBool = false
        form.valueNumber = 0
      }
    } else {
      form.id = 0
      form.category = activeCategory.value || 'general'
      form.key = ''
      form.value = ''
      form.valueBool = false
      form.valueNumber = 0
      form.value_type = 'string'
      form.is_encrypted = false
      form.description = ''
    }
  })
}

const onValueTypeChange = () => {
  // 切换类型时清空对应值字段
  if (form.value_type === 'boolean') {
    form.valueBool = false
  } else if (form.value_type === 'number') {
    form.valueNumber = 0
  } else {
    form.value = ''
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      let payloadValue: string | null = ''
      if (form.value_type === 'boolean') {
        payloadValue = String(form.valueBool)
      } else if (form.value_type === 'number') {
        payloadValue = String(form.valueNumber)
      } else {
        payloadValue = form.value || ''
      }

      const payload: Api.SystemConfig.ConfigPayload = {
        category: form.category,
        key: form.key,
        value: payloadValue,
        value_type: form.value_type,
        is_encrypted: form.is_encrypted,
        description: form.description || null,
      }

      if (dialogType.value === 'add') {
        await addConfig(payload)
      } else {
        await updateConfig(form.id, payload)
      }

      dialogVisible.value = false
      refreshCategories()
      refreshAll()
    } catch (err) {
      console.error('保存失败:', err)
    } finally {
      submitLoading.value = false
    }
  })
}

const handleDelete = (row: any) => {
  ElMessageBox.confirm(
    `确定删除配置项 [${row.category}.${row.key}] 吗？`,
    '删除确认',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        await deleteConfig(row.id)
        ElMessage.success('删除成功')
        refreshCategories()
        refreshAll()
      } catch (err) {
        console.error('删除配置出错:', err)
      }
    })
    .catch(() => {})
}

onMounted(() => {
  refreshCategories()
})
</script>

<style lang="scss" scoped>
.system-config-page {
  .config-row {
    min-height: calc(100vh - 200px);
  }

  .category-col {
    border-right: 1px solid var(--el-border-color-lighter);
    padding-right: 12px;
  }

  .category-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 8px 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    margin-bottom: 8px;

    .title {
      font-size: 14px;
      font-weight: 600;
    }
  }

  .category-list {
    .category-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 6px;
      cursor: pointer;
      margin-bottom: 4px;
      transition: background 0.15s;
      color: var(--el-text-color-regular);

      &:hover {
        background: var(--el-fill-color-light);
      }

      &.active {
        background: var(--el-color-primary-light-9);
        color: var(--el-color-primary);
        font-weight: 500;
      }

      .name {
        flex: 1;
      }

      .count-badge {
        margin-right: 0;
      }
    }
  }

  .config-col {
    padding-left: 12px;
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .search-wrapper {
    margin-bottom: 12px;
  }

  .config-table-card {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .config-key {
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    color: var(--el-color-primary);
  }

  .masked-value {
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    color: var(--el-text-color-secondary);
  }

  .operation-column-container {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}
</style>
