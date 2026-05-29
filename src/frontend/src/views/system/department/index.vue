<template>
  <div class="department-page art-full-height">
    <!-- 搜索栏 -->
    <ArtSearchBar
      v-model="searchParams"
      :items="searchItems"
      @reset="resetSearch"
      @search="loadTreeData"
    />

    <ElCard class="art-table-card" shadow="never">
      <!-- 表格头部 -->
      <ArtTableHeader @refresh="loadTreeData">
        <template #left>
          <ElButton @click="showDialog('add')" v-ripple>添加部门</ElButton>
        </template>
      </ArtTableHeader>

      <!-- 树形表格 -->
      <ElTable
        v-loading="loading"
        :data="treeData"
        row-key="id"
        :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
        default-expand-all
        table-layout="fixed"
        class="department-tree-table"
      >
        <ElTableColumn prop="name" label="部门名称" min-width="200" />
        <ElTableColumn prop="sort" label="排序" width="100" align="center" />
        <ElTableColumn prop="user_count" label="人数" width="100" align="center">
          <template #default="{ row }">
            {{ row.user_count ?? 0 }}
          </template>
        </ElTableColumn>
        <ElTableColumn prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <ElTag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <div class="operation-column-container">
              <ArtButtonTable type="edit" style="margin-right: 8px;" @click="showDialog('edit', row)" />
              <ArtButtonTable type="delete" @click="handleDelete(row)" />
            </div>
          </template>
        </ElTableColumn>
      </ElTable>

      <!-- 部门弹窗 -->
      <ElDialog
        v-model="dialogVisible"
        :title="dialogType === 'add' ? '添加部门' : '编辑部门'"
        width="600px"
        align-center
        :close-on-click-modal="false"
        @closed="resetForm"
      >
        <ElForm ref="formRef" :model="formData" :rules="rules" label-width="85px">
          <ElRow :gutter="20">
            <ElCol :span="12">
              <ElFormItem label="部门名称" prop="name">
                <ElInput v-model="formData.name" placeholder="请输入部门名称" />
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="排序" prop="sort">
                <ElInputNumber
                  v-model="formData.sort"
                  style="width: 100%"
                  :min="0"
                  controls-position="right"
                  placeholder="请输入排序号"
                />
              </ElFormItem>
            </ElCol>
          </ElRow>
          <ElRow :gutter="20">
            <ElCol :span="12">
              <ElFormItem label="上级部门" prop="parent_id">
                <ElCascader
                  v-model="formData.parent_id"
                  :options="departmentOptions"
                  :props="cascaderProps"
                  clearable
                  placeholder="请选择上级部门（不选则为顶级）"
                  style="width: 100%"
                  :key="cascaderKey"
                />
              </ElFormItem>
            </ElCol>
            <ElCol :span="12">
              <ElFormItem label="启用">
                <ElSwitch v-model="formData.statusActive" :active-value="1" :inactive-value="2" />
              </ElFormItem>
            </ElCol>
          </ElRow>
        </ElForm>
        <template #footer>
          <div class="dialog-footer">
            <ElButton @click="dialogVisible = false">取消</ElButton>
            <ElButton type="primary" @click="submitForm" :loading="submitLoading">提交</ElButton>
          </div>
        </template>
      </ElDialog>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, nextTick } from 'vue'
  import { ElMessageBox, ElMessage } from 'element-plus'
  import type { FormInstance, FormRules } from 'element-plus'
  import {
    getDepartmentTree,
    addDepartment,
    updateDepartment,
    deleteDepartment as apiDeleteDepartment
  } from '@/api/system/api'
  import ArtButtonTable from '@/components/core/forms/art-button-table/index.vue'
  import { SearchFormItem } from '@/types'

  // ========== 状态 ==========
  const loading = ref(false)
  const treeData = ref<any[]>([])
  const dialogVisible = ref(false)
  const dialogType = ref<'add' | 'edit'>('add')
  const submitLoading = ref(false)
  const currentId = ref<number | null>(null)
  const formRef = ref<FormInstance>()
  const cascaderKey = ref(0)

  // 部门选项（用于 Cascader 选择上级部门）
  const departmentOptions = ref<any[]>([])

  // 搜索参数
  const searchParams = reactive({
    name: '',
    status: undefined as number | undefined
  })

  // 表单数据
  const formData = reactive({
    name: '',
    sort: 0,
    parent_id: undefined as number | undefined,
    statusActive: 1
  })

  // Cascader 配置：允许选择任意层级，不限制只能选叶子节点
  const cascaderProps = {
    value: 'id',
    label: 'name',
    children: 'children',
    checkStrictly: true,
    emitPath: false,
    expandTrigger: 'hover' as const
  }

  // ========== 搜索配置 ==========
  const searchItems: SearchFormItem[] = [
    {
      label: '部门名称',
      key: 'name',
      type: 'input',
      span: 6,
      clearable: true,
      placeholder: '请输入部门名称'
    },
    {
      label: '状态',
      key: 'status',
      type: 'select',
      span: 6,
      clearable: true,
      placeholder: '请选择状态',
      options: [
        { label: '启用', value: 1 },
        { label: '禁用', value: 2 }
      ]
    }
  ]

  // ========== 表单验证 ==========
  const rules = reactive<FormRules>({
    name: [
      { required: true, message: '请输入部门名称', trigger: 'blur' },
      { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
    ]
  })

  // ========== 数据加载 ==========
  const loadTreeData = async () => {
    loading.value = true
    try {
      const res = await getDepartmentTree()
      treeData.value = (res as any) ?? []
    } catch (err) {
      console.error('加载部门树出错:', err)
      ElMessage.error('加载部门列表失败')
    } finally {
      loading.value = false
    }
  }

  // 加载部门选项（用于 Cascader）
  const loadDepartmentOptions = async () => {
    try {
      const res = await getDepartmentTree()
      departmentOptions.value = (res as any) ?? []
    } catch (err) {
      console.error('加载部门选项出错:', err)
    }
  }

  const resetSearch = () => {
    searchParams.name = ''
    searchParams.status = undefined
    loadTreeData()
  }

  // ========== 弹窗操作 ==========
  const resetForm = () => {
    formData.name = ''
    formData.sort = 0
    formData.parent_id = undefined
    formData.statusActive = 1
    currentId.value = null
    cascaderKey.value++
  }

  const showDialog = (type: 'add' | 'edit', row?: any) => {
    dialogType.value = type
    dialogVisible.value = true

    if (type === 'edit' && row) {
      currentId.value = row.id
      formData.name = row.name
      formData.sort = row.sort ?? 0
      formData.parent_id = row.parent_id ?? undefined
      formData.statusActive = row.status ?? 1
    } else {
      resetForm()
    }

    // 强制重新渲染 Cascader（避免旧数据残留）
    nextTick(() => {
      cascaderKey.value++
      formRef.value?.clearValidate()
    })
  }

  // ========== 删除 ==========
  const handleDelete = (row: any) => {
    ElMessageBox.confirm(
      `确定要删除部门「${row.name}」吗？${row.user_count > 0 ? `该部门下有 ${row.user_count} 个用户关联。` : ''}`,
      '删除部门',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
      .then(async () => {
        try {
          const res: any = await apiDeleteDepartment(row.id)
          if (res?.code === 200 || res?.success) {
            ElMessage.success('删除部门成功')
            await Promise.all([loadTreeData(), loadDepartmentOptions()])
          } else {
            ElMessage.error(res?.message || '删除部门失败')
          }
        } catch (err: any) {
          console.error('删除部门出错:', err)
          ElMessage.error(err?.message || '删除部门失败')
        }
      })
      .catch(() => {})
  }

  // ========== 提交 ==========
  const submitForm = async () => {
    if (!formRef.value) return

    await formRef.value.validate(async (valid) => {
      if (!valid) return

      submitLoading.value = true
      try {
        const params = {
          name: formData.name,
          sort: formData.sort,
          parent_id: formData.parent_id ?? null,
          status: formData.statusActive
        }

        let res: any
        if (dialogType.value === 'edit') {
          if (!currentId.value) {
            ElMessage.error('部门ID无效')
            return
          }
          res = await updateDepartment({ id: currentId.value, ...params })
        } else {
          res = await addDepartment(params)
        }

        if (res?.code === 200 || res?.success) {
          ElMessage.success(dialogType.value === 'add' ? '添加成功' : '修改成功')
          dialogVisible.value = false
          await Promise.all([loadTreeData(), loadDepartmentOptions()])
        } else {
          ElMessage.error(res?.message || (dialogType.value === 'add' ? '添加失败' : '修改失败'))
        }
      } catch (err: any) {
        console.error('提交表单出错:', err)
        ElMessage.error(err?.message || (dialogType.value === 'add' ? '添加失败' : '修改失败'))
      } finally {
        submitLoading.value = false
      }
    })
  }

  // ========== 初始化 ==========
  loadTreeData()
  loadDepartmentOptions()
</script>

<style lang="scss" scoped>
  .department-page {
    .operation-column-container {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }
</style>
