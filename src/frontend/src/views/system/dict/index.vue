<template>
  <div class="dict-page art-full-height" id="table-full-screen">
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
          <ElButton @click="showDialog('add')">新增字典</ElButton>
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

      <!-- 字典弹窗 -->
      <ElDialog
        v-model="dialogVisible"
        :title="dialogType === 'add' ? '新增字典' : '编辑字典'"
        width="540px"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <ElForm ref="formRef" :model="form" :rules="rules" label-width="100px" @submit.prevent>
          <ElFormItem label="字典类型" prop="dict_type">
            <ElSelect
              v-model="form.dict_type"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入字典类型"
              style="width: 100%"
            >
              <ElOption
                v-for="t in dictTypes"
                :key="t"
                :label="t"
                :value="t"
              />
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="字典编码" prop="dict_code">
            <ElInput v-model="form.dict_code" placeholder="英文编码，如 server" />
          </ElFormItem>
          <ElFormItem label="字典标签" prop="dict_label">
            <ElInput v-model="form.dict_label" placeholder="显示名称，如 服务器" />
          </ElFormItem>
          <ElFormItem label="标签颜色">
            <ElSelect v-model="form.color" clearable placeholder="选择颜色（可选）" style="width: 100%">
              <ElOption
                v-for="c in colorOptions"
                :key="c.value"
                :label="c.label"
                :value="c.value"
              >
                <ElTag :type="c.value as any" size="small">{{ c.label }}</ElTag>
              </ElOption>
            </ElSelect>
          </ElFormItem>
          <ElFormItem label="排序">
            <ElInputNumber v-model="form.sort_order" :min="0" :max="9999" />
          </ElFormItem>
          <ElFormItem label="是否启用">
            <ElSwitch v-model="form.is_active" />
          </ElFormItem>
          <ElFormItem label="默认值">
            <ElSwitch v-model="form.is_default" />
          </ElFormItem>
          <ElFormItem label="备注">
            <ElInput v-model="form.remark" type="textarea" :rows="3" placeholder="备注说明" />
          </ElFormItem>
        </ElForm>
        <template #footer>
          <div class="dialog-footer">
            <ElButton @click="dialogVisible = false">取消</ElButton>
            <ElButton type="primary" @click="handleSubmit(formRef)" :loading="submitLoading">
              提交
            </ElButton>
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
import { getDictList, getDictTypes, addDict, updateDict, deleteDict } from '@/api/dict'
import { useDictStore } from '@/store/modules/dict'
import { useTable } from '@/composables/useTable'
import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
import type { SearchFormItem } from '@/types'

const dictStore = useDictStore()
const dictTypes = ref<string[]>([])

const colorOptions = [
  { label: '主要', value: 'primary' },
  { label: '成功', value: 'success' },
  { label: '警告', value: 'warning' },
  { label: '危险', value: 'danger' },
  { label: '信息', value: 'info' },
]

// 搜索表单配置
const searchItems: SearchFormItem[] = [
  {
    label: '字典类型',
    key: 'dict_type',
    type: 'select',
    clearable: true,
    placeholder: '请选择字典类型',
    options: [],
  },
  {
    label: '搜索',
    key: 'search',
    type: 'input',
    clearable: true,
    placeholder: '编码/标签',
  },
]

// 表单
const form = reactive({
  id: 0,
  dict_type: '',
  dict_code: '',
  dict_label: '',
  color: '' as string | null,
  sort_order: 0,
  is_active: true,
  is_default: false,
  remark: '' as string | null,
})
const dialogType = ref('add')
const dialogVisible = ref(false)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()

const rules = reactive<FormRules>({
  dict_type: [{ required: true, message: '请输入字典类型', trigger: 'blur' }],
  dict_code: [
    { required: true, message: '请输入字典编码', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅支持英文、数字、下划线、中划线', trigger: 'blur' },
  ],
  dict_label: [{ required: true, message: '请输入字典标签', trigger: 'blur' }],
})

// useTable
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
  refreshAll: refresh,
} = useTable<any>({
  core: {
    apiFn: getDictList,
    apiParams: {
      page: 1,
      page_size: 20,
      dict_type: undefined,
      search: '',
    },
    paginationKey: {
      current: 'page',
      size: 'page_size'
    },
    columnsFactory: () => [
      {
        prop: 'dict_type',
        label: '字典类型',
        align: 'center',
        width: 140,
      },
      {
        prop: 'dict_code',
        label: '字典编码',
        align: 'center',
        width: 140,
      },
      {
        prop: 'dict_label',
        label: '字典标签',
        align: 'center',
      },
      {
        prop: 'color',
        label: '颜色',
        align: 'center',
        width: 100,
        formatter: (row: any) =>
          row.color
            ? h(
                resolveComponent('ElTag'),
                { type: (row.color as any) || undefined, size: 'small' },
                { default: () => row.color }
              )
            : h('span', { style: 'color: #999' }, '--'),
      },
      {
        prop: 'sort_order',
        label: '排序',
        align: 'center',
        width: 80,
      },
      {
        prop: 'is_active',
        label: '状态',
        align: 'center',
        width: 80,
        formatter: (row: any) =>
          h(
            resolveComponent('ElTag'),
            { type: row.is_active ? 'success' : 'info', size: 'small' },
            { default: () => (row.is_active ? '启用' : '禁用') }
          ),
      },
      {
        prop: 'is_default',
        label: '默认',
        align: 'center',
        width: 80,
        formatter: (row: any) =>
          row.is_default
            ? h(resolveComponent('ElTag'), { type: 'primary', size: 'small' }, { default: () => '是' })
            : h('span', { style: 'color: #999' }, '否'),
      },
      {
        prop: 'operation',
        label: '操作',
        align: 'center',
        width: 140,
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
              onClick: () => deleteAction(row.id),
            }),
          ]),
      },
    ],
  },
  hooks: {
    onError: (error) => ElMessage.error(error.message),
  },
})

// 加载字典类型列表
async function loadDictTypes() {
  try {
    const types = await getDictTypes()
    if (Array.isArray(types)) {
      dictTypes.value = types
      // 更新搜索栏的字典类型下拉选项
      const typeSearchItem = searchItems.find((item) => item.key === 'dict_type')
      if (typeSearchItem) {
        typeSearchItem.options = types.map((t: string) => ({ label: t, value: t }))
      }
    }
  } catch (e) {
    console.warn('加载字典类型失败', e)
  }
}

// 弹窗
const showDialog = (type: string, row?: any) => {
  dialogType.value = type
  dialogVisible.value = true
  nextTick(() => {
    formRef.value?.resetFields()
    if (type === 'edit' && row) {
      form.id = row.id
      form.dict_type = row.dict_type
      form.dict_code = row.dict_code
      form.dict_label = row.dict_label
      form.color = row.color || null
      form.sort_order = row.sort_order ?? 0
      form.is_active = row.is_active ?? true
      form.is_default = row.is_default ?? false
      form.remark = row.remark || null
    } else {
      form.id = 0
      form.dict_type = ''
      form.dict_code = ''
      form.dict_label = ''
      form.color = null
      form.sort_order = 0
      form.is_active = true
      form.is_default = false
      form.remark = null
    }
  })
}

// 删除
const deleteAction = (id: number) => {
  ElMessageBox.confirm('确定删除该字典项吗？', '删除确认', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      try {
        await deleteDict(id)
        // 刷新对应类型的字典缓存
        dictStore.refreshType(form.dict_type)
        refresh()
      } catch (err) {
        console.error('删除字典出错:', err)
      }
    })
    .catch(() => {})
}

// 提交
const handleSubmit = async (formEl: FormInstance | undefined) => {
  if (!formEl) return
  await formEl.validate(async (valid) => {
    if (!valid) return
    submitLoading.value = true
    try {
      const payload: any = {
        dict_type: form.dict_type,
        dict_code: form.dict_code,
        dict_label: form.dict_label,
        color: form.color || null,
        sort_order: form.sort_order,
        is_active: form.is_active,
        is_default: form.is_default,
        remark: form.remark || null,
      }
      if (dialogType.value === 'add') {
        await addDict(payload)
      } else {
        await updateDict(form.id, payload)
      }
      dialogVisible.value = false
      // 刷新字典缓存
      dictStore.refreshType(form.dict_type)
      // 刷新字典类型列表（可能新增了类型）
      loadDictTypes()
      refresh()
    } catch (err) {
      console.error('提交字典出错:', err)
    } finally {
      submitLoading.value = false
    }
  })
}

onMounted(() => {
  loadDictTypes()
})
</script>

<style lang="scss" scoped>
.dict-page {
  .operation-column-container {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}
</style>
