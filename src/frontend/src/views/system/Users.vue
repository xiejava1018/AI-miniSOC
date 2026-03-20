<template>
  <div class="users-page">
    <!-- 页面头部 -->
    <el-page-header @back="goBack" class="page-header">
      <template #content>
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/dashboard' }">
            首页
          </el-breadcrumb-item>
          <el-breadcrumb-item>系统管理</el-breadcrumb-item>
          <el-breadcrumb-item>用户管理</el-breadcrumb-item>
        </el-breadcrumb>
      </template>
      <template #extra>
        <el-button
          v-if="isAdmin"
          type="primary"
          @click="showCreateDialog"
          data-testid="add-user-button"
        >
          <el-icon><Plus /></el-icon>
          添加用户
        </el-button>
      </template>
    </el-page-header>

    <!-- 搜索和筛选 -->
    <el-card class="filter-card" shadow="never">
      <el-form :model="usersStore.filters" inline>
        <el-form-item label="搜索">
          <el-input
            v-model="searchInput"
            placeholder="搜索用户名/邮箱/姓名"
            clearable
            style="width: 250px"
            @clear="handleSearch"
            data-testid="user-search-input"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select
            v-model="usersStore.filters.role_id"
            placeholder="选择角色"
            clearable
            style="width: 150px"
            @change="handleSearch"
          >
            <el-option
              v-for="role in roles"
              :key="role.id"
              :label="role.name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="usersStore.filters.status"
            placeholder="选择状态"
            clearable
            style="width: 120px"
            @change="handleSearch"
          >
            <el-option label="正常" value="active" />
            <el-option label="已锁定" value="locked" />
            <el-option label="已禁用" value="disabled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch" data-testid="search-button">
            查询
          </el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 用户表格 -->
    <el-card class="table-card" shadow="never">
      <el-table
        :data="usersStore.users"
        v-loading="usersStore.loading"
        stripe
        border
        style="width: 100%"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="full_name" label="姓名" width="120" />
        <el-table-column prop="email" label="邮箱" width="180" />
        <el-table-column prop="role_name" label="角色" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login" label="最后登录" width="160">
          <template #default="{ row }">
            {{ row.last_login ? formatDate(row.last_login) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="viewUser(row)"
            >
              查看
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="primary"
              @click="editUser(row)"
            >
              编辑
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="warning"
              @click="resetPassword(row)"
            >
              重置密码
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              :type="row.is_locked ? 'success' : 'warning'"
              @click="toggleLock(row)"
            >
              {{ row.is_locked ? '解锁' : '锁定' }}
            </el-button>
            <el-button
              v-if="isAdmin"
              link
              type="danger"
              @click="deleteUser(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="usersStore.pagination.page"
        v-model:page-size="usersStore.pagination.page_size"
        :total="usersStore.pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="usersStore.fetchUsers"
        @size-change="usersStore.fetchUsers"
        style="margin-top: 20px; justify-content: center"
      />
    </el-card>

    <!-- 创建/编辑用户对话框 -->
    <UserDialog
      v-model="dialogVisible"
      :user="currentUser"
      :roles="roles"
      :mode="dialogMode"
      @submit="handleDialogSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useUsersStore } from '@/stores/users'
import { useRolesStore } from '@/stores/roles'
import UserDialog from '@/components/UserDialog.vue'
import type { User, UserCreate, UserUpdate } from '@/types/user'

const router = useRouter()
const authStore = useAuthStore()
const usersStore = useUsersStore()
const rolesStore = useRolesStore()

const searchInput = ref('')
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const currentUser = ref<User>()

const isAdmin = computed(() => authStore.isAdmin)
const roles = computed(() => rolesStore.roles)

onMounted(() => {
  usersStore.fetchUsers()
  rolesStore.fetchRoles()
})

function goBack() {
  router.push('/dashboard')
}

function handleSearch() {
  usersStore.filters.search = searchInput.value || undefined
  usersStore.pagination.page = 1
  usersStore.fetchUsers()
}

function handleReset() {
  searchInput.value = ''
  usersStore.resetFilters()
  usersStore.fetchUsers()
}

function getStatusType(status: string) {
  const typeMap: Record<string, any> = {
    active: 'success',
    locked: 'danger',
    disabled: 'info'
  }
  return typeMap[status] || 'info'
}

function getStatusLabel(status: string) {
  const labelMap: Record<string, string> = {
    active: '正常',
    locked: '已锁定',
    disabled: '已禁用'
  }
  return labelMap[status] || status
}

function formatDate(dateString: string) {
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

function viewUser(user: User) {
  // TODO: 实现用户详情查看
  ElMessage.info('用户详情功能开发中')
}

function showCreateDialog() {
  dialogMode.value = 'create'
  currentUser.value = undefined
  dialogVisible.value = true
}

function editUser(user: User) {
  dialogMode.value = 'edit'
  currentUser.value = user
  dialogVisible.value = true
}

async function handleDialogSubmit(data: UserCreate | UserUpdate) {
  try {
    if (dialogMode.value === 'create') {
      await usersStore.createUser(data as UserCreate)
      ElMessage.success('用户创建成功')
    } else {
      await usersStore.updateUser(currentUser.value!.id, data as UserUpdate)
      ElMessage.success('用户更新成功')
    }
    dialogVisible.value = false
  } catch (error: any) {
    ElMessage.error(error.detail || '操作失败')
  }
}

async function resetPassword(user: User) {
  try {
    await ElMessageBox.confirm(
      `确定要重置用户 "${user.username}" 的密码吗？`,
      '重置密码',
      {
        type: 'warning',
        confirmButtonText: '确定',
        cancelButtonText: '取消'
      }
    )

    const newPassword = await usersStore.resetPassword(user.id)

    await ElMessageBox.alert(
      `新密码: ${newPassword}`,
      '密码已重置',
      {
        confirmButtonText: '复制',
        callback: () => {
          navigator.clipboard.writeText(newPassword)
          ElMessage.success('密码已复制到剪贴板')
        }
      }
    )
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.detail || '重置密码失败')
    }
  }
}

async function toggleLock(user: User) {
  const action = user.is_locked ? '解锁' : '锁定'
  const title = user.is_locked ? '解锁用户' : '锁定用户'

  try {
    await ElMessageBox.prompt(
      `${action}原因（可选）`,
      title,
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /^.{0,500}$/,
        inputErrorMessage: '原因不能超过500字符'
      }
    )

    await usersStore.toggleLock(user.id, !user.is_locked, '')
    ElMessage.success(`${action}成功`)
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.detail || `${action}失败`)
    }
  }
}

async function deleteUser(user: User) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.username}" 吗？此操作不可恢复！`,
      '删除用户',
      {
        type: 'error',
        confirmButtonText: '确定',
        cancelButtonText: '取消'
      }
    )

    await usersStore.deleteUser(user.id)
    ElMessage.success('用户已删除')
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.detail || '删除失败')
    }
  }
}
</script>

<style scoped>
.users-page {
  padding: 24px;
  background-color: var(--el-bg-color-page);
  min-height: 100vh;
}

.page-header {
  margin-bottom: 24px;
}

.filter-card {
  margin-bottom: 16px;
}

.filter-card :deep(.el-card__body) {
  padding: 16px;
}

.table-card :deep(.el-card__body) {
  padding: 16px;
}
</style>
