<!-- src/frontend/src/views/system/Roles.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRolesStore } from '@/stores/roles'
import { useAuthStore } from '@/stores/auth'
import { roleApi } from '@/api/role'
import { menuApi } from '@/api/menu'
import type { Role, RoleCreate, RoleUpdate } from '@/types/role'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Lock } from '@element-plus/icons-vue'

const rolesStore = useRolesStore()
const authStore = useAuthStore()

// 搜索
const searchText = ref('')

// 对话框
const dialogVisible = ref(false)
const dialogTitle = computed(() => isEdit.value ? '编辑角色' : '创建角色')
const isEdit = ref(false)
const currentRole = ref<Role | null>(null)

// 菜单权限对话框
const menusDialogVisible = ref(false)
const menuTree = ref<any[]>([])
const checkedMenuIds = ref<number[]>([])
const menuTreeRef = ref()

// 表单
const form = ref<RoleCreate>({
  name: '',
  code: '',
  description: '',
  menu_ids: []
})

const formRef = ref()

// 表单验证规则
const rules = {
  name: [{ required: true, message: '请输入角色名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入角色代码', trigger: 'blur' }]
}

// 获取角色列表
async function fetchRoles() {
  await rolesStore.fetchRoles({ search: searchText.value || undefined })
}

// 搜索
function handleSearch() {
  rolesStore.resetFilters()
  fetchRoles()
}

// 打开创建对话框
function openCreateDialog() {
  isEdit.value = false
  currentRole.value = null
  form.value = {
    name: '',
    code: '',
    description: '',
    menu_ids: []
  }
  dialogVisible.value = true
}

// 打开编辑对话框
function openEditDialog(role: Role) {
  isEdit.value = true
  currentRole.value = role
  form.value = {
    name: role.name,
    code: role.code,
    description: role.description,
    menu_ids: []
  }
  dialogVisible.value = true
}

// 提交表单
async function handleSubmit() {
  await formRef.value?.validate()

  try {
    if (isEdit.value && currentRole.value) {
      await rolesStore.updateRole(currentRole.value.id, form.value)
    } else {
      await rolesStore.createRole(form.value)
    }
    dialogVisible.value = false
  } catch (error) {
    // 错误已在store中处理
  }
}

// 删除角色
async function handleDelete(role: Role) {
  try {
    await ElMessageBox.confirm(
      `确定要删除角色"${role.name}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await rolesStore.deleteRole(role.id)
  } catch {
    // 用户取消
  }
}

// 打开菜单权限对话框
async function openMenusDialog(role: Role) {
  currentRole.value = role

  // 获取菜单树
  const tree = await menuApi.getMenuTree()
  menuTree.value = tree

  // 获取角色已有的菜单
  const response = await roleApi.getRoleMenus(role.id)
  checkedMenuIds.value = response.menu_ids || []

  menusDialogVisible.value = true
}

// 分配菜单权限
async function handleAssignMenus() {
  if (!currentRole.value) return

  const checkedKeys = menuTreeRef.value?.getCheckedKeys() || []
  await rolesStore.assignMenus(currentRole.value.id, checkedKeys)
  menusDialogVisible.value = false
}

onMounted(() => {
  fetchRoles()
})
</script>

<template>
  <div class="roles-container">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon> 创建角色
      </el-button>
      <el-input
        v-model="searchText"
        placeholder="搜索角色名称或代码"
        clearable
        @input="handleSearch"
        style="width: 300px; margin-left: 10px"
      />
    </div>

    <!-- 角色列表 -->
    <el-table :data="rolesStore.roles" v-loading="rolesStore.loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="角色名称" width="150" />
      <el-table-column prop="code" label="角色代码" width="150" />
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column prop="user_count" label="用户数" width="100" />
      <el-table-column prop="is_system" label="类型" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.is_system" type="warning">系统</el-tag>
          <el-tag v-else type="success">自定义</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button link type="primary" @click="openMenusDialog(row)">权限</el-button>
          <el-button
            link
            type="danger"
            @click="handleDelete(row)"
            :disabled="row.is_system"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="rolesStore.pagination.page"
      v-model:page-size="rolesStore.pagination.page_size"
      :total="rolesStore.pagination.total"
      @current-change="fetchRoles"
      style="margin-top: 20px"
    />

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入角色名称" />
        </el-form-item>
        <el-form-item label="角色代码" prop="code">
          <el-input
            v-model="form.code"
            placeholder="请输入角色代码"
            :disabled="isEdit && currentRole?.is_system"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            placeholder="请输入角色描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 菜单权限对话框 -->
    <el-dialog v-model="menusDialogVisible" title="菜单权限分配" width="500px">
      <el-tree
        :data="menuTree"
        :props="{ children: 'children', label: 'name' }"
        show-checkbox
        node-key="id"
        :default-checked-keys="checkedMenuIds"
        ref="menuTreeRef"
      />
      <template #footer>
        <el-button @click="menusDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleAssignMenus">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.roles-container {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}
</style>
