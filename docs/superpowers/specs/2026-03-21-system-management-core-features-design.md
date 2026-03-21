# 系统管理核心功能实现设计

**项目**: AI-miniSOC
**模块**: 系统管理核心功能
**版本**: v1.0
**日期**: 2026-03-21
**状态**: 待实施

---

## 1. 概述

### 1.1 目标

实现系统管理模块的4个核心功能，完善RBAC权限体系：
1. **角色管理** - 角色CRUD、菜单权限分配、系统角色保护
2. **菜单管理** - 菜单CRUD、2级树形结构、图标配置
3. **动态菜单加载** - 基于角色的菜单动态渲染
4. **审计日志** - 完整操作审计、查询导出

### 1.2 技术栈

- **后端**: FastAPI + SQLAlchemy + PostgreSQL
- **前端**: Vue 3 + TypeScript + Element Plus + Pinia
- **权限模型**: 基于菜单的RBAC（Role-Based Access Control）

---

## 2. 角色管理模块

### 2.1 后端API设计

#### API端点

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/roles/` | 角色列表（分页） | admin |
| GET | `/api/v1/roles/{id}` | 角色详情 | admin |
| POST | `/api/v1/roles/` | 创建角色 | admin |
| PUT | `/api/v1/roles/{id}` | 更新角色 | admin |
| DELETE | `/api/v1/roles/{id}` | 删除角色 | admin |
| GET | `/api/v1/roles/{id}/menus` | 获取角色菜单 | admin |
| PUT | `/api/v1/roles/{id}/menus` | 分配菜单权限 | admin |
| GET | `/api/v1/roles/{id}/users` | 获取使用该角色的用户 | admin |

#### 系统角色严格保护规则

```python
# is_system=True 的角色：
- ❌ 不能删除（返回403 Forbidden）
- ❌ 不能修改 code 字段
- ✅ 可以修改 name、description
- ✅ 删除前检查是否有用户使用，有则返回400 Bad Request
```

#### Pydantic Schemas

```python
# app/schemas/role.py
class RoleBase(BaseModel):
    name: str = Field(max_length=50)
    description: Optional[str] = None

class RoleCreate(RoleBase):
    code: str = Field(max_length=50)
    menu_ids: List[int] = []  # 关联的菜单ID列表

class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    menu_ids: Optional[List[int]] = None

class RoleResponse(RoleBase):
    id: int
    code: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    user_count: int = 0  # 使用该角色的用户数

class RoleMenusRequest(BaseModel):
    menu_ids: List[int]
```

#### 服务层实现

```python
# app/services/role_service.py
class RoleService:
    def get_roles(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> Tuple[List[Role], int]:
        """获取角色列表"""
        query = db.query(Role)
        if search:
            query = query.filter(
                (Role.name.ilike(f"%{search}%")) |
                (Role.code.ilike(f"%{search}%"))
            )
        total = query.count()
        roles = query.offset(skip).limit(limit).all()
        return roles, total

    def create_role(
        self,
        role_data: RoleCreate,
        creator_id: int
    ) -> Role:
        """创建角色"""
        # 检查code唯一性
        if db.query(Role).filter(Role.code == role_data.code).first():
            raise ValueError("角色代码已存在")

        role = Role(
            name=role_data.name,
            code=role_data.code,
            description=role_data.description,
            is_system=False
        )
        db.add(role)
        db.flush()

        # 分配菜单权限
        if role_data.menu_ids:
            menus = db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        db.commit()
        return role

    def update_role(
        self,
        role_id: int,
        role_data: RoleUpdate,
        updater_id: int
    ) -> Role:
        """更新角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")

        # 系统角色不能修改code
        if role.is_system and hasattr(role_data, 'code') and role_data.code != role.code:
            raise ValueError("系统角色不能修改代码")

        if role_data.name:
            role.name = role_data.name
        if role_data.description is not None:
            role.description = role_data.description

        # 更新菜单权限
        if role_data.menu_ids is not None:
            menus = db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        db.commit()
        return role

    def delete_role(self, role_id: int, deleter_id: int) -> None:
        """删除角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")

        # 系统角色不能删除
        if role.is_system:
            raise ValueError("系统角色不能删除")

        # 检查是否有用户使用
        user_count = db.query(User).filter(User.role_id == role_id).count()
        if user_count > 0:
            raise ValueError(f"该角色正在被 {user_count} 个用户使用，无法删除")

        db.delete(role)
        db.commit()

    def assign_menus(
        self,
        role_id: int,
        menu_ids: List[int]
    ) -> Role:
        """分配菜单权限"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")

        menus = db.query(Menu).filter(Menu.id.in_(menu_ids)).all()
        role.menus = menus
        db.commit()
        return role
```

### 2.2 前端实现

#### 页面组件

```vue
<!-- src/views/system/Roles.vue -->
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
    <el-table :data="roles" v-loading="loading">
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
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button link type="primary" @click="openMenusDialog(row)">权限</el-button>
          <el-button
            link
            type="danger"
            @click="handleDelete(row)"
            :disabled="row.is_system"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.pageSize"
      :total="pagination.total"
      @current-change="fetchRoles"
    />

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle">
      <el-form :model="form" :rules="rules" ref="formRef">
        <el-form-item label="角色名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="角色代码" prop="code">
          <el-input v-model="form.code" :disabled="isEdit && currentRole?.is_system" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
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
```

#### Store实现

```typescript
// src/stores/roles.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api/role'

export interface Role {
  id: number
  name: string
  code: string
  description?: string
  is_system: boolean
  user_count: number
  created_at: string
  updated_at: string
}

export const useRolesStore = defineStore('roles', () => {
  const roles = ref<Role[]>([])
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    pageSize: 20,
    total: 0
  })

  async function fetchRoles(params?: { page?: number; search?: string }) {
    loading.value = true
    try {
      const response = await api.getRoles({
        page: params?.page || pagination.value.page,
        page_size: pagination.value.pageSize,
        search: params?.search
      })
      roles.value = response.items
      pagination.value.total = response.total
    } finally {
      loading.value = false
    }
  }

  async function createRole(data: any) {
    await api.createRole(data)
    await fetchRoles()
  }

  async function updateRole(id: number, data: any) {
    await api.updateRole(id, data)
    await fetchRoles()
  }

  async function deleteRole(id: number) {
    await api.deleteRole(id)
    await fetchRoles()
  }

  async function assignMenus(roleId: number, menuIds: number[]) {
    await api.assignMenus(roleId, { menu_ids: menuIds })
  }

  return {
    roles,
    loading,
    pagination,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
    assignMenus
  }
})
```

---

## 3. 菜单管理模块

### 3.1 后端API设计

#### API端点

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/menus/` | 菜单列表（平铺） | 所有用户 |
| GET | `/api/v1/menus/tree` | 菜单树 | 所有用户 |
| GET | `/api/v1/menus/check-access` | 检查菜单访问权限 | 所有用户 |
| POST | `/api/v1/menus/` | 创建菜单 | admin |
| GET | `/api/v1/menus/{id}` | 菜单详情 | admin |
| PUT | `/api/v1/menus/{id}` | 更新菜单 | admin |
| DELETE | `/api/v1/menus/{id}` | 删除菜单 | admin |

#### Pydantic Schemas

```python
# app/schemas/menu.py
class MenuBase(BaseModel):
    name: str = Field(max_length=50)
    # 注意: 父级菜单的path设为空字符串""，不使用None
    path: str = Field(max_length=200)
    icon: Optional[str] = Field(None, max_length=50)
    sort_order: int = 0
    is_visible: bool = True

class MenuCreate(MenuBase):
    parent_id: Optional[int] = None

class MenuUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    path: Optional[str] = Field(None, max_length=200)
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_visible: Optional[bool] = None

class MenuResponse(MenuBase):
    id: int
    parent_id: Optional[int]
    created_at: datetime
    updated_at: datetime

class MenuTreeResponse(MenuResponse):
    children: List['MenuTreeResponse'] = []

MenuTreeResponse.model_rebuild()
```

#### 服务层实现

```python
# app/services/menu_service.py
class MenuService:
    def get_menu_tree(self) -> List[Menu]:
        """获取菜单树（所有用户可访问）"""
        menus = db.query(Menu).filter(Menu.is_visible == True).all()
        return self._build_tree(menus)

    def _build_tree(self, menus: List[Menu]) -> List[Menu]:
        """构建树形结构"""
        menu_dict = {menu.id: menu for menu in menus}
        root_menus = []

        for menu in menus:
            if menu.parent_id is None:
                root_menus.append(menu)
            else:
                parent = menu_dict.get(menu.parent_id)
                if parent:
                    if not hasattr(parent, 'children'):
                        parent.children = []
                    parent.children.append(menu)

        # 排序
        for menu in root_menus:
            if hasattr(menu, 'children'):
                menu.children.sort(key=lambda x: x.sort_order)

        return sorted(root_menus, key=lambda x: x.sort_order)

    def create_menu(self, menu_data: MenuCreate) -> Menu:
        """创建菜单"""
        menu = Menu(**menu_data.model_dump())
        db.add(menu)
        db.commit()
        return menu

    def update_menu(self, menu_id: int, menu_data: MenuUpdate) -> Menu:
        """更新菜单"""
        menu = db.query(Menu).filter(Menu.id == menu_id).first()
        if not menu:
            raise ValueError("菜单不存在")

        # 防止循环引用
        if menu_data.parent_id:
            if menu_data.parent_id == menu_id:
                raise ValueError("不能将自己设为父菜单")

        for field, value in menu_data.model_dump(exclude_unset=True).items():
            setattr(menu, field, value)

        db.commit()
        return menu

    def delete_menu(self, menu_id: int) -> None:
        """删除菜单"""
        menu = db.query(Menu).filter(Menu.id == menu_id).first()
        if not menu:
            raise ValueError("菜单不存在")

        # 检查是否有子菜单
        child_count = db.query(Menu).filter(Menu.parent_id == menu_id).count()
        if child_count > 0:
            raise ValueError(f"该菜单有 {child_count} 个子菜单，无法删除")

        db.delete(menu)
        db.commit()

    def check_menu_access(self, user_id: int, path: str) -> bool:
        """检查用户是否有访问指定菜单的权限"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.role:
            return False

        # 检查用户角色的菜单权限
        return user.has_menu_access(path)
```

### 3.2 前端实现

#### 页面组件

```vue
<!-- src/views/system/Menus.vue -->
<template>
  <div class="menus-container">
    <div class="toolbar">
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon> 创建菜单
      </el-button>
    </div>

    <!-- 菜单树 -->
    <el-table
      :data="menuTree"
      row-key="id"
      :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
      default-expand-all
    >
      <el-table-column prop="name" label="菜单名称" width="200" />
      <el-table-column prop="path" label="路径" />
      <el-table-column prop="icon" label="图标" width="150">
        <template #default="{ row }">
          <el-icon v-if="row.icon"><component :is="row.icon" /></el-icon>
          <span>{{ row.icon }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="sort_order" label="排序" width="100" />
      <el-table-column prop="is_visible" label="可见" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_visible ? 'success' : 'info'">
            {{ row.is_visible ? '显示' : '隐藏' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle">
      <el-form :model="form" :rules="rules" ref="formRef">
        <el-form-item label="父级菜单">
          <el-tree-select
            v-model="form.parent_id"
            :data="menuOptions"
            :props="{ label: 'name', value: 'id' }"
            clearable
            check-strictly
          />
        </el-form-item>
        <el-form-item label="菜单名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="路径">
          <el-input v-model="form.path" placeholder="例如: /system/users" />
        </el-form-item>
        <el-form-item label="图标">
          <el-select v-model="form.icon" filterable>
            <el-option
              v-for="icon in iconOptions"
              :key="icon"
              :label="icon"
              :value="icon"
            >
              <el-icon><component :is="icon" /></el-icon>
              <span>{{ icon }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="可见">
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
```

---

## 4. 动态菜单加载

### 4.1 后端实现

#### 修改认证API返回

```python
# app/api/auth.py
@router.post("/login")
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 生成token
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    # 获取用户菜单
    user_menus = user.role.menus if user.role else []
    menu_tree = build_menu_tree(user_menus)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
        "menus": menu_tree  # 新增
    }

@router.get("/me")
async def get_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户信息"""
    # 刷新菜单
    db.refresh(current_user)
    user_menus = current_user.role.menus if current_user.role else []
    menu_tree = build_menu_tree(user_menus)

    return {
        "user": UserResponse.model_validate(current_user),
        "menus": menu_tree
    }

def build_menu_tree(menus: List[Menu]) -> List[dict]:
    """构建菜单树"""
    menu_dict = {m.id: m.to_dict(include_children=False) for m in menus}
    tree = []

    for menu in menus:
        data = menu_dict[menu.id]
        if menu.parent_id is None:
            tree.append(data)
        else:
            parent = menu_dict.get(menu.parent_id)
            if parent:
                if 'children' not in parent:
                    parent['children'] = []
                parent['children'].append(data)

    # 排序
    for item in tree:
        if 'children' in item:
            item['children'].sort(key=lambda x: x['sort_order'])

    return sorted(tree, key=lambda x: x['sort_order'])
```

### 4.2 前端实现

#### 修改Auth Store

```typescript
// src/stores/auth.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/auth'

export interface MenuItem {
  id: number
  parent_id?: number
  name: string
  path: string | null
  icon: string
  sort_order: number
  is_visible: boolean
  children?: MenuItem[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<any>(null)
  const menus = ref<MenuItem[]>([])

  const isAuthenticated = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role?.code === 'admin')

  async function login(credentials: { username: string; password: string }) {
    const response = await api.login(credentials)
    token.value = response.access_token
    user.value = response.user
    menus.value = response.menus

    localStorage.setItem('token', response.access_token)
    localStorage.setItem('refresh_token', response.refresh_token)
    localStorage.setItem('user', JSON.stringify(response.user))
    localStorage.setItem('menus', JSON.stringify(response.menus))
  }

  async function logout() {
    await api.logout()
    clearAuth()
  }

  function clearAuth() {
    token.value = null
    user.value = null
    menus.value = []
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    localStorage.removeItem('menus')
  }

  async function fetchCurrentUser() {
    const response = await api.getCurrentUser()
    user.value = response.user
    menus.value = response.menus
    localStorage.setItem('user', JSON.stringify(response.user))
    localStorage.setItem('menus', JSON.stringify(response.menus))
  }

  return {
    token,
    user,
    menus,
    isAuthenticated,
    isAdmin,
    login,
    logout,
    clearAuth,
    fetchCurrentUser
  }
})
```

#### 修改App.vue动态渲染菜单

```vue
<!-- src/App.vue -->
<template>
  <aside class="sidebar" v-if="authStore.isAuthenticated">
    <nav class="sidebar-nav">
      <template v-for="item in authStore.menus" :key="item.id">
        <!-- 有子菜单 -->
        <div v-if="item.children && item.children.length > 0" class="nav-group">
          <div class="nav-group-title">
            <component :is="item.icon" class="nav-icon" />
            <span class="nav-label">{{ item.name }}</span>
          </div>
          <router-link
            v-for="child in item.children"
            :key="child.id"
            :to="child.path"
            class="nav-item nav-child"
          >
            <component :is="child.icon" class="nav-icon" />
            <span class="nav-label">{{ child.name }}</span>
          </router-link>
        </div>
        <!-- 无子菜单 -->
        <router-link
          v-else
          :to="item.path"
          class="nav-item"
        >
          <component :is="item.icon" class="nav-icon" />
          <span class="nav-label">{{ item.name }}</span>
        </router-link>
      </template>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { onMounted } from 'vue'

const authStore = useAuthStore()

onMounted(async () => {
  if (authStore.token && !authStore.user) {
    await authStore.fetchCurrentUser()
  }
})
</script>
```

#### 路由守卫增强

```typescript
// src/router/index.ts
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 检查认证
  if (to.meta.requiresAuth !== false && !authStore.isAuthenticated) {
    return next('/login')
  }

  // 检查菜单权限
  if (authStore.isAuthenticated && to.path !== '/login') {
    const hasPermission = checkMenuPermission(authStore.menus, to.path)
    if (!hasPermission) {
      return next('/403')
    }
  }

  next()
})

function checkMenuPermission(menus: MenuItem[], path: string): boolean {
  for (const menu of menus) {
    if (menu.path === path) return true
    if (menu.children) {
      if (checkMenuPermission(menu.children, path)) return true
    }
  }
  return false
}
```

---

## 5. 审计日志模块

### 5.1 审计装饰器

```python
# app/core/audit.py
from functools import wraps
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from fastapi import Request
import json
import uuid

def audit_log(action: str, resource_type: str):
    """
    审计日志装饰器

    用法:
    @audit_log("CREATE", "User")
    async def create_user(...):
        ...

    注意: 被装饰的函数需要接收 request: Request 参数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中提取db、current_user、request
            db: Session = kwargs.get('db')
            current_user = kwargs.get('current_user')
            request: Request = kwargs.get('request')

            # 提取客户端信息
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get('user-agent')

            # 生成请求ID
            request_id = str(uuid.uuid4())

            # 对于更新操作，捕获变更前的数据
            old_values = None
            if action in ['UPDATE', 'DELETE'] and 'id' in kwargs:
                resource_id = kwargs.get('id')
                if resource_id and resource_type == 'User':
                    old_obj = db.query(User).filter(User.id == resource_id).first()
                    if old_obj:
                        old_values = {
                            'username': old_obj.username,
                            'email': old_obj.email,
                            'full_name': old_obj.full_name,
                            'status': old_obj.status,
                            'role_id': old_obj.role_id
                        }

            # 记录开始
            log = AuditLog(
                user_id=current_user.id if current_user else None,
                username=current_user.username if current_user else 'system',
                action=action,
                resource_type=resource_type,
                request_id=request_id,
                ip_address=ip_address,
                user_agent=user_agent,
                old_values=json.dumps(old_values) if old_values else None,
                status='success'
            )

            try:
                result = await func(*args, **kwargs)

                # 记录成功
                if hasattr(result, 'id'):
                    log.resource_id = result.id
                    log.resource_name = getattr(result, 'username', None) or getattr(result, 'name', None)

                # 对于更新操作，捕获变更后的数据
                if action == 'UPDATE' and result:
                    new_values = {
                        'username': result.username,
                        'email': result.email,
                        'full_name': result.full_name,
                        'status': result.status,
                        'role_id': result.role_id
                    }
                    log.new_values = json.dumps(new_values)

                db.add(log)
                db.commit()

                return result

            except Exception as e:
                # 记录失败
                log.status = 'failure'
                log.error_message = str(e)
                db.add(log)
                db.commit()
                raise

        return wrapper
    return decorator
```

### 5.2 审计操作定义

```python
# app/constants/audit_actions.py

# 认证操作
AUDIT_LOGIN = "LOGIN"
AUDIT_LOGOUT = "LOGOUT"
AUDIT_PASSWORD_CHANGE = "PASSWORD_CHANGE"
AUDIT_PASSWORD_RESET = "PASSWORD_RESET"

# 用户管理
AUDIT_USER_CREATE = "USER_CREATE"
AUDIT_USER_UPDATE = "USER_UPDATE"
AUDIT_USER_DELETE = "USER_DELETE"
AUDIT_USER_LOCK = "USER_LOCK"
AUDIT_USER_UNLOCK = "USER_UNLOCK"

# 角色管理
AUDIT_ROLE_CREATE = "ROLE_CREATE"
AUDIT_ROLE_UPDATE = "ROLE_UPDATE"
AUDIT_ROLE_DELETE = "ROLE_DELETE"
AUDIT_ROLE_ASSIGN_MENUS = "ROLE_ASSIGN_MENUS"

# 菜单管理
AUDIT_MENU_CREATE = "MENU_CREATE"
AUDIT_MENU_UPDATE = "MENU_UPDATE"
AUDIT_MENU_DELETE = "MENU_DELETE"

# 数据操作
AUDIT_ASSET_CREATE = "ASSET_CREATE"
AUDIT_ASSET_UPDATE = "ASSET_UPDATE"
AUDIT_ASSET_DELETE = "ASSET_DELETE"
AUDIT_INCIDENT_CREATE = "INCIDENT_CREATE"
AUDIT_INCIDENT_UPDATE = "INCIDENT_UPDATE"
AUDIT_ALERT_HANDLE = "ALERT_HANDLE"

# 敏感操作
AUDIT_DATA_EXPORT = "DATA_EXPORT"
AUDIT_CONFIG_CHANGE = "CONFIG_CHANGE"
AUDIT_API_KEY_VIEW = "API_KEY_VIEW"
```

### 5.3 后端API实现

```python
# app/api/audit.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.auth import get_current_user
from app.schemas.user import UserResponse
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])

@router.get("")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取审计日志列表"""
    query = db.query(AuditLog)

    # 筛选条件
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    if status:
        query = query.filter(AuditLog.status == status)

    # 分页
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()) \
             .offset((page - 1) * page_size) \
             .limit(page_size) \
             .all()

    return {
        "total": total,
        "items": [log.to_dict() for log in logs],
        "page": page,
        "page_size": page_size
    }

@router.get("/{log_id}")
async def get_audit_log(
    log_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取审计日志详情"""
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="日志不存在")
    return log.to_dict()

@router.get("/export")
async def export_audit_logs(
    format: str = Query("csv", regex="^(csv|excel)$"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """导出审计日志"""
    # TODO: 实现导出功能
    pass
```

### 5.4 前端实现

```vue
<!-- src/views/system/AuditLogs.vue -->
<template>
  <div class="audit-logs-container">
    <!-- 筛选器 -->
    <el-form :model="filters" inline>
      <el-form-item label="用户">
        <el-select v-model="filters.user_id" clearable filterable>
          <el-option
            v-for="user in users"
            :key="user.id"
            :label="user.username"
            :value="user.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="操作类型">
        <el-select v-model="filters.action" clearable>
          <el-option label="登录" value="LOGIN" />
          <el-option label="登出" value="LOGOUT" />
          <el-option label="创建用户" value="USER_CREATE" />
          <!-- 更多选项 -->
        </el-select>
      </el-form-item>
      <el-form-item label="时间范围">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleExport">导出</el-button>
      </el-form-item>
    </el-form>

    <!-- 审计日志列表 -->
    <el-table :data="logs" v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户" width="120" />
      <el-table-column prop="action" label="操作" width="150" />
      <el-table-column prop="resource_type" label="资源类型" width="120" />
      <el-table-column prop="resource_name" label="资源名称" width="150" />
      <el-table-column prop="ip_address" label="IP地址" width="140" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'">
            {{ row.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetailDialog(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.pageSize"
      :total="pagination.total"
      @current-change="fetchLogs"
    />

    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="日志详情" width="600px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="用户">{{ currentLog?.username }}</el-descriptions-item>
        <el-descriptions-item label="操作">{{ currentLog?.action }}</el-descriptions-item>
        <el-descriptions-item label="资源类型">{{ currentLog?.resource_type }}</el-descriptions-item>
        <el-descriptions-item label="资源ID">{{ currentLog?.resource_id }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ currentLog?.ip_address }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ currentLog?.status }}</el-descriptions-item>
        <el-descriptions-item label="变更前" :span="2">
          <pre>{{ formatJSON(currentLog?.old_values) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="变更后" :span="2">
          <pre>{{ formatJSON(currentLog?.new_values) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>
```

---

## 6. 数据库初始化

### 6.1 角色初始化

```sql
-- 系统内置角色
INSERT INTO soc_roles (name, code, description, is_system) VALUES
('管理员', 'admin', '系统管理员，拥有所有权限', true),
('普通用户', 'user', '普通用户，可使用业务功能', true),
('只读用户', 'readonly', '只读用户，仅可查看数据', true)
ON CONFLICT (code) DO NOTHING;
```

### 6.2 菜单初始化

```sql
-- 业务菜单
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('概览仪表板', '/dashboard', 'DataAnalysis', 1, true),
('资产管理', '/assets', 'Monitor', 2, true),
('事件管理', '/incidents', 'Warning', 3, true),
('告警管理', '/alerts', 'Bell', 4, true)
ON CONFLICT (path) DO NOTHING;

-- 系统管理（父菜单 - 使用空字符串作为path）
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('系统管理', '', 'Setting', 5, true)
ON CONFLICT (name, path) DO NOTHING;

-- 系统管理子菜单
INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '用户管理',
    '/system/users',
    'User',
    1,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/users');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '角色管理',
    '/system/roles',
    'Lock',
    2,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/roles');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '菜单管理',
    '/system/menus',
    'Menu',
    3,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/menus');

INSERT INTO soc_menus (parent_id, name, path, icon, sort_order, is_visible)
SELECT
    (SELECT id FROM soc_menus WHERE name='系统管理'),
    '审计日志',
    '/system/audit',
    'Document',
    4,
    true
WHERE NOT EXISTS (SELECT 1 FROM soc_menus WHERE path='/system/audit');
```

### 6.3 角色菜单权限初始化

```sql
-- 管理员拥有所有菜单
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT
    (SELECT id FROM soc_roles WHERE code='admin'),
    id
FROM soc_menus
ON CONFLICT DO NOTHING;

-- 普通用户拥有业务菜单（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT
    (SELECT id FROM soc_roles WHERE code='user'),
    id
FROM soc_menus
WHERE path NOT LIKE '/system%' OR path IS NULL
ON CONFLICT DO NOTHING;

-- 只读用户仅有查看权限
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT
    (SELECT id FROM soc_roles WHERE code='readonly'),
    id
FROM soc_menus
WHERE path IN ('/dashboard', '/assets', '/incidents', '/alerts')
ON CONFLICT DO NOTHING;
```

---

## 7. 实施步骤

### Phase 1: 数据库和后端基础
1. 执行数据库初始化SQL
2. 创建后端Schemas
3. 实现RoleService
4. 实现MenuService
5. 添加角色和菜单API

### Phase 2: 前端页面
1. 创建Roles.vue和roles.ts
2. 创建Menus.vue和menus.ts
3. 实现角色CRUD和权限分配
4. 实现菜单CRUD和Tree组件

### Phase 3: 动态菜单
1. 修改认证API返回菜单
2. 修改auth store保存菜单
3. 修改App.vue动态渲染
4. 增强路由守卫权限检查

### Phase 4: 审计日志
1. 实现审计装饰器
2. 添加审计日志API
3. 创建AuditLogs.vue
4. 在关键操作添加审计

### Phase 5: 测试
1. 单元测试
2. 集成测试
3. E2E测试

---

## 8. 测试计划

### 角色管理测试
- 创建自定义角色
- 编辑角色（系统角色限制）
- 删除角色（系统角色保护、用户检查）
- 分配菜单权限

### 菜单管理测试
- 创建父子菜单
- 编辑菜单
- 删除菜单（子菜单检查）
- 菜单树展示

### 动态菜单测试
- 不同角色登录看到不同菜单
- 无权限访问被拦截
- 菜单正确渲染

### 审计日志测试
- 所有操作被记录
- 筛选查询功能
- 日志详情查看
- 数据导出

---

**文档版本**: v1.0
**最后更新**: 2026-03-21
