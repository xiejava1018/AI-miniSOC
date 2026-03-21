<!-- src/frontend/src/views/system/Menus.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useMenusStore } from '@/stores/menus'
import type { Menu, MenuCreate, MenuUpdate } from '@/types/menu'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

// Element Plus图标列表
const iconList = [
  'Setting', 'User', 'Lock', 'Menu', 'Document', 'DataAnalysis', 'Monitor', 'Warning', 'Bell',
  'House', 'Folder', 'Files', 'DocumentCopy', 'Delete', 'Edit', 'Search', 'Refresh',
  'Plus', 'Minus', 'Close', 'Check', 'ArrowRight', 'ArrowDown', 'MoreFilled'
]

const menusStore = useMenusStore()

// 对话框
const dialogVisible = ref(false)
const dialogTitle = ref('创建菜单')
const isEdit = ref(false)
const currentMenu = ref<Menu | null>(null)

// 表单
const form = ref<MenuCreate>({
  name: '',
  path: '',
  icon: '',
  parent_id: undefined,
  sort_order: 0,
  is_visible: true
})

const formRef = ref()

// 表单验证规则
const rules = {
  name: [{ required: true, message: '请输入菜单名称', trigger: 'blur' }],
  path: [{ required: true, message: '请输入菜单路径', trigger: 'blur' }]
}

// 获取菜单树
async function fetchMenuTree() {
  await menusStore.fetchMenuTree()
}

// 打开创建对话框
function openCreateDialog(parent?: Menu) {
  isEdit.value = false
  currentMenu.value = null
  form.value = {
    name: '',
    path: '',
    icon: '',
    parent_id: parent?.id,
    sort_order: 0,
    is_visible: true
  }
  dialogTitle.value = parent ? `创建子菜单 - ${parent.name}` : '创建菜单'
  dialogVisible.value = true
}

// 打开编辑对话框
function openEditDialog(menu: Menu) {
  isEdit.value = true
  currentMenu.value = menu
  form.value = {
    name: menu.name,
    path: menu.path,
    icon: menu.icon,
    parent_id: menu.parent_id,
    sort_order: menu.sort_order,
    is_visible: menu.is_visible
  }
  dialogTitle.value = '编辑菜单'
  dialogVisible.value = true
}

// 提交表单
async function handleSubmit() {
  await formRef.value?.validate()

  try {
    if (isEdit.value && currentMenu.value) {
      await menusStore.updateMenu(currentMenu.value.id, form.value)
    } else {
      await menusStore.createMenu(form.value)
    }
    dialogVisible.value = false
  } catch (error) {
    // 错误已在store中处理
  }
}

// 删除菜单
async function handleDelete(menu: Menu) {
  // 检查是否有子菜单
  if (menu.children && menu.children.length > 0) {
    ElMessage.warning('该菜单包含子菜单，无法删除')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除菜单"${menu.name}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await menusStore.deleteMenu(menu.id)
  } catch {
    // 用户取消
  }
}

// 格式化图标
function formatIcon(icon: string) {
  return icon || '无'
}

onMounted(() => {
  fetchMenuTree()
})
</script>

<template>
  <div class="menus-container">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="openCreateDialog()">
        <el-icon><Plus /></el-icon> 创建根菜单
      </el-button>
    </div>

    <!-- 菜单树表格 -->
    <el-table
      :data="menusStore.menuTree"
      v-loading="menusStore.loading"
      row-key="id"
      :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
      stripe
      default-expand-all
    >
      <el-table-column prop="name" label="菜单名称" width="200" />
      <el-table-column prop="path" label="路径" width="250">
        <template #default="{ row }">
          <el-tag v-if="!row.path" type="info">父菜单</el-tag>
          <span v-else>{{ row.path }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="icon" label="图标" width="120">
        <template #default="{ row }">
          <el-icon v-if="row.icon" class="menu-icon">
            <component :is="row.icon" />
          </el-icon>
          <span v-else class="text-gray">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column prop="is_visible" label="可见" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_visible ? 'success' : 'info'">
            {{ row.is_visible ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openCreateDialog(row)" size="small">
            添加子菜单
          </el-button>
          <el-button link type="primary" @click="openEditDialog(row)">
            编辑
          </el-button>
          <el-button
            link
            type="danger"
            @click="handleDelete(row)"
            :disabled="row.children && row.children.length > 0"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="菜单名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入菜单名称" />
        </el-form-item>
        <el-form-item label="菜单路径" prop="path">
          <el-input v-model="form.path" placeholder="父菜单留空，子菜单填写路径如 /system/users" />
          <div class="form-tip">
            父菜单使用空字符串，子菜单填写实际路由路径
          </div>
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="form.icon" placeholder="选择图标" clearable>
            <el-option
              v-for="icon in iconList"
              :key="icon"
              :label="icon"
              :value="icon"
            >
              <div style="display: flex; align-items: center; gap: 8px;">
                <el-icon><component :is="icon" /></el-icon>
                <span>{{ icon }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="是否可见">
          <el-switch v-model="form.is_visible" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.menus-container {
  padding: 20px;
}

.toolbar {
  margin-bottom: 20px;
}

.menu-icon {
  font-size: 18px;
}

.text-gray {
  color: #909399;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
