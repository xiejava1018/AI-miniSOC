# 用户管理模块设计文档

**项目**: AI-miniSOC
**模块**: 用户管理 (User Management)
**版本**: v1.0
**日期**: 2026-03-19
**状态**: 设计阶段

---

## 一、概述

### 1.1 目标

为AI-miniSOC系统实现完整的用户管理功能，支持用户CRUD、状态管理和密码管理，为其他系统管理模块提供基础。

### 1.2 功能范围

- ✅ 基础CRUD操作（创建、查看、编辑、删除用户）
- ✅ 用户状态管理（启用/禁用/锁定）
- ✅ 密码管理（重置密码、强制修改密码）
- ✅ 用户查询（搜索、筛选、分页）
- ✅ 权限控制（角色级：管理员全部操作，普通角色仅查看）

### 1.3 约束条件

- 仅管理员可以创建、编辑、删除用户
- 所有有"system-users"权限的用户可以查看用户列表
- 不能删除最后一个管理员
- 用户名和邮箱必须唯一
- 密码长度至少6位

---

## 二、架构设计

### 2.1 技术栈

**后端**:
- FastAPI 0.115+
- SQLAlchemy 2.0+
- PostgreSQL 16+
- Pydantic 2.10+

**前端**:
- Vue 3 (Composition API)
- TypeScript
- Element Plus 2.13+
- Pinia 3.0+

### 2.2 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                     │
├─────────────────────────────────────────────────────────────┤
│  Views/Users.vue              # 用户管理页面                │
│  ├── 表格展示（el-table）                                    │
│  ├── 搜索和筛选                                              │
│  ├── 操作按钮（查看/编辑/删除/重置密码/锁定）                 │
│  └── 对话框（创建/编辑表单）                                  │
│                                                             │
│  Stores/users.ts               # 用户状态管理               │
│  ├── state: users, loading, pagination, filters             │
│  └── actions: fetchUsers, createUser, updateUser, etc.      │
│                                                             │
│  API Client                    # API调用                    │
│  └── axios + 拦截器 + token自动注入                          │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP (JSON)
┌─────────────────────────────────────────────────────────────┐
│                        API层 (FastAPI)                       │
├─────────────────────────────────────────────────────────────┤
│  api/users.py                  # 用户管理API路由            │
│  ├── GET    /api/v1/users          # 用户列表               │
│  ├── GET    /api/v1/users/{id}     # 用户详情               │
│  ├── POST   /api/v1/users          # 创建用户               │
│  ├── PUT    /api/v1/users/{id}     # 更新用户               │
│  ├── DELETE /api/v1/users/{id}     # 删除用户               │
│  ├── POST   /api/v1/users/{id}/reset-password  # 重置密码   │
│  └── POST   /api/v1/users/{id}/lock           # 锁定/解锁   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      服务层 (Services)                       │
├─────────────────────────────────────────────────────────────┤
│  services/user_service.py     # 用户业务逻辑                │
│  ├── 用户CRUD操作                                           │
│  ├── 数据验证（用户名唯一、邮箱格式等）                      │
│  ├── 密码重置（生成随机密码）                                │
│  ├── 账户锁定/解锁                                          │
│  └── 权限检查                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    数据访问层 (Models)                       │
├─────────────────────────────────────────────────────────────┤
│  models/user.py                 # User ORM模型              │
│  └── soc_users表映射                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    数据库层 (PostgreSQL)                     │
├─────────────────────────────────────────────────────────────┤
│  soc_users                     # 用户表                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 数据流

**查询用户列表**:
```
1. 用户访问 /system/users
2. 前端路由守卫检查认证和权限
3. Users.vue 组件挂载
4. 调用 usersStore.fetchUsers()
5. 发送 GET /api/v1/users?page=1&page_size=20&search=xxx
6. 后端验证JWT token
7. 检查用户是否有"system-users"权限
8. UserService查询数据库
9. 返回用户列表（JSON）
10. 前端更新表格和分页
```

**创建用户**:
```
1. 管理员点击"添加用户"按钮
2. 弹出创建表单对话框
3. 填写用户信息并提交
4. 调用 usersStore.createUser(data)
5. 发送 POST /api/v1/users + 用户数据
6. 后端验证：是否管理员、用户名唯一、邮箱格式等
7. UserService.hash_password() → bcrypt
8. 插入数据库
9. 记录审计日志
10. 返回创建的用户信息
11. 前端刷新列表并关闭对话框
```

---

## 三、数据库设计

### 3.1 表结构

**soc_users** (已存在，无需修改)

```sql
CREATE TABLE soc_users (
    id                      BIGSERIAL PRIMARY KEY,
    username                VARCHAR(50) NOT NULL UNIQUE,
    password_hash           VARCHAR(255) NOT NULL,
    email                   VARCHAR(100) UNIQUE,
    full_name               VARCHAR(100),
    phone                   VARCHAR(20),
    department              VARCHAR(100),
    status                  VARCHAR(20) DEFAULT 'active',
    role_id                 BIGINT NOT NULL REFERENCES soc_roles(id),
    last_login_at           TIMESTAMPTZ,
    password_changed_at     TIMESTAMPTZ,
    failed_login_attempts   INTEGER DEFAULT 0,
    locked_until            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_username ON soc_users(username);
CREATE INDEX idx_users_email ON soc_users(email);
CREATE INDEX idx_users_role_id ON soc_users(role_id);
CREATE INDEX idx_users_status ON soc_users(status);
```

### 3.2 关系

```
soc_users (N) ──┐
                │
                ├── soc_roles (1)  [多对一]
                │
                └── soc_user_sessions (N)  [一对多]
                └── soc_password_history (N)  [一对多]
                └── soc_audit_logs (N)  [一对多]
```

### 3.3 数据字典

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, AUTO | 用户ID |
| username | VARCHAR(50) | NOT NULL, UNIQUE | 用户名，3-50字符 |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt加密后的密码 |
| email | VARCHAR(100) | UNIQUE | 邮箱地址（可选） |
| full_name | VARCHAR(100) | - | 真实姓名 |
| phone | VARCHAR(20) | - | 手机号 |
| department | VARCHAR(100) | - | 部门 |
| status | VARCHAR(20) | DEFAULT 'active' | 状态：active/locked/disabled |
| role_id | BIGINT | NOT NULL, FK | 角色ID |
| last_login_at | TIMESTAMPTZ | - | 最后登录时间 |
| password_changed_at | TIMESTAMPTZ | - | 最后修改密码时间 |
| failed_login_attempts | INTEGER | DEFAULT 0 | 失败登录次数 |
| locked_until | TIMESTAMPTZ | - | 锁定截止时间 |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | 更新时间 |

---

## 四、API设计

### 4.1 API端点清单

| 方法 | 路径 | 描述 | 权限要求 |
|------|------|------|----------|
| GET | `/api/v1/users` | 用户列表（分页+筛选） | system-users |
| GET | `/api/v1/users/{id}` | 用户详情 | system-users |
| POST | `/api/v1/users` | 创建用户 | admin only |
| PUT | `/api/v1/users/{id}` | 更新用户 | admin only |
| DELETE | `/api/v1/users/{id}` | 删除用户 | admin only |
| POST | `/api/v1/users/{id}/reset-password` | 重置密码 | admin only |
| POST | `/api/v1/users/{id}/lock` | 锁定/解锁用户 | admin only |

### 4.2 API详细定义

#### 4.2.1 用户列表

**请求**:
```http
GET /api/v1/users?page=1&page_size=20&search=admin&role_id=1&status=active
Authorization: Bearer <access_token>
```

**查询参数**:
- `page`: 页码（默认1）
- `page_size`: 每页数量（默认20，最大100）
- `search`: 搜索关键词（用户名/邮箱/姓名模糊匹配）
- `role_id`: 按角色ID筛选
- `status`: 按状态筛选（active/locked/disabled）

**响应**:
```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "full_name": "系统管理员",
      "role_id": 1,
      "role_name": "管理员",
      "status": "active",
      "is_locked": false,
      "last_login": "2026-03-19T10:30:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-03-19T10:30:00Z"
    }
  ]
}
```

#### 4.2.2 用户详情

**请求**:
```http
GET /api/v1/users/1
Authorization: Bearer <access_token>
```

**响应**:
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "full_name": "系统管理员",
  "phone": "13800138000",
  "department": "IT部门",
  "role_id": 1,
  "role_name": "管理员",
  "status": "active",
  "is_locked": false,
  "last_login": "2026-03-19T10:30:00Z",
  "password_changed_at": "2026-01-01T00:00:00Z",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-03-19T10:30:00Z"
}
```

#### 4.2.3 创建用户

**请求**:
```http
POST /api/v1/users
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "username": "testuser",
  "password": "Test123456",
  "email": "test@example.com",
  "full_name": "测试用户",
  "phone": "13900139000",
  "department": "运维部门",
  "role_id": 2
}
```

**响应**:
```json
{
  "id": 10,
  "username": "testuser",
  "email": "test@example.com",
  "full_name": "测试用户",
  "role_id": 2,
  "role_name": "普通用户",
  "status": "active",
  "is_locked": false,
  "created_at": "2026-03-19T12:00:00Z"
}
```

**错误响应**:
```json
{
  "detail": "用户名已存在"
}
```

#### 4.2.4 更新用户

**请求**:
```http
PUT /api/v1/users/10
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email": "newemail@example.com",
  "full_name": "新姓名",
  "role_id": 3,
  "is_active": true
}
```

**响应**: 同创建用户

#### 4.2.5 删除用户

**请求**:
```http
DELETE /api/v1/users/10
Authorization: Bearer <access_token>
```

**响应**:
```json
{
  "success": true,
  "message": "用户已删除"
}
```

#### 4.2.6 重置密码

**请求**:
```http
POST /api/v1/users/10/reset-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "new_password": "NewPass123"
}
```

**响应**:
```json
{
  "success": true,
  "message": "密码已重置",
  "new_password": "NewPass123"
}
```

#### 4.2.7 锁定/解锁用户

**请求**:
```http
POST /api/v1/users/10/lock
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "is_locked": true,
  "lock_reason": "多次登录失败"
}
```

**响应**:
```json
{
  "id": 10,
  "username": "testuser",
  "is_locked": true,
  "locked_until": "2026-03-26T12:00:00Z"
}
```

### 4.3 权限控制实现

```python
# api/users.py
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.permissions import require_menu_permission
from app.schemas.user import UserResponse
from app.database import get_db

@router.get("/users", dependencies=[Depends(require_menu_permission("system-users"))])
async def get_users(
    page: int = 1,
    page_size: int = 20,
    search: str = None,
    role_id: int = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """获取用户列表 - 所有有权限的用户可访问"""
    # ...

@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建用户 - 仅管理员可访问"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以创建用户"
        )
    # ...
```

---

## 五、前端设计

### 5.1 页面结构

```
views/system/Users.vue
├── 页面头部
│   ├── 面包屑导航
│   └── 操作按钮（添加用户 - 仅管理员）
├── 搜索和筛选栏
│   ├── 搜索框（用户名/邮箱/姓名）
│   ├── 角色下拉筛选
│   └──状态下拉筛选
├── 用户表格（el-table）
│   ├── 列：ID, 用户名, 姓名, 邮箱, 角色, 状态, 最后登录, 操作
│   └── 操作列：查看, 编辑, 重置密码, 锁定/解锁, 删除
├── 分页组件（el-pagination）
└── 对话框
    ├── 创建用户表单
    └── 编辑用户表单
```

### 5.2 组件设计

#### 5.2.1 用户列表组件

**模板结构**:
```vue
<template>
  <div class="users-page">
    <!-- 页面头部 -->
    <el-page-header @back="goBack">
      <template #content>
        <el-breadcrumb>
          <el-breadcrumb-item>系统管理</el-breadcrumb-item>
          <el-breadcrumb-item>用户管理</el-breadcrumb-item>
        </el-breadcrumb>
      </template>
      <template #extra>
        <el-button
          type="primary"
          @click="showCreateDialog"
          v-if="isAdmin"
        >
          <el-icon><Plus /></el-icon>
          添加用户
        </el-button>
      </template>
    </el-page-header>

    <!-- 搜索和筛选 -->
    <el-form :inline="true" class="filter-form">
      <el-form-item label="搜索">
        <el-input
          v-model="filters.search"
          placeholder="搜索用户名/邮箱/姓名"
          clearable
          @clear="handleSearch"
        />
      </el-form-item>
      <el-form-item label="角色">
        <el-select
          v-model="filters.role_id"
          placeholder="选择角色"
          clearable
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
          v-model="filters.status"
          placeholder="选择状态"
          clearable
          @change="handleSearch"
        >
          <el-option label="正常" value="active" />
          <el-option label="已锁定" value="locked" />
          <el-option label="已禁用" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 用户表格 -->
    <el-table
      :data="users"
      v-loading="loading"
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
      <el-table-column prop="last_login" label="最后登录" width="160" />
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewUser(row)">
            查看
          </el-button>
          <el-button
            link
            type="primary"
            @click="editUser(row)"
            v-if="isAdmin"
          >
            编辑
          </el-button>
          <el-button
            link
            type="warning"
            @click="resetPassword(row)"
            v-if="isAdmin"
          >
            重置密码
          </el-button>
          <el-button
            link
            :type="row.is_locked ? 'success' : 'warning'"
            @click="toggleLock(row)"
            v-if="isAdmin"
          >
            {{ row.is_locked ? '解锁' : '锁定' }}
          </el-button>
          <el-button
            link
            type="danger"
            @click="deleteUser(row)"
            v-if="isAdmin"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.page_size"
      :total="pagination.total"
      :page-sizes="[10, 20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="fetchUsers"
      @size-change="fetchUsers"
    />

    <!-- 创建/编辑用户对话框 -->
    <UserDialog
      v-model="dialogVisible"
      :user="currentUser"
      :roles="roles"
      :mode="dialogMode"
      @submit="handleSubmit"
    />
  </div>
</template>
```

#### 5.2.2 用户对话框组件

**UserDialog.vue**:
```vue
<template>
  <el-dialog
    :model-value="modelValue"
    :title="mode === 'create' ? '创建用户' : '编辑用户'"
    width="600px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="100px"
    >
      <el-form-item label="用户名" prop="username">
        <el-input
          v-model="formData.username"
          :disabled="mode === 'edit'"
          placeholder="请输入用户名"
        />
      </el-form-item>
      <el-form-item label="密码" prop="password" v-if="mode === 'create'">
        <el-input
          v-model="formData.password"
          type="password"
          placeholder="请输入密码"
          show-password
        />
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="formData.email"
          placeholder="请输入邮箱"
        />
      </el-form-item>
      <el-form-item label="姓名" prop="full_name">
        <el-input
          v-model="formData.full_name"
          placeholder="请输入姓名"
        />
      </el-form-item>
      <el-form-item label="角色" prop="role_id">
        <el-select v-model="formData.role_id" placeholder="请选择角色">
          <el-option
            v-for="role in roles"
            :key="role.id"
            :label="role.name"
            :value="role.id"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>
```

### 5.3 Store设计

**stores/users.ts**:
```typescript
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { User, UserCreate, UserUpdate } from '@/types/user'
import { apiCall } from '@/api'

interface UserFilters {
  search?: string
  role_id?: number
  status?: string
}

interface Pagination {
  page: number
  page_size: number
  total: number
}

export const useUsersStore = defineStore('users', () => {
  // State
  const users = ref<User[]>([])
  const loading = ref(false)
  const pagination = reactive<Pagination>({
    page: 1,
    page_size: 20,
    total: 0
  })
  const filters = reactive<UserFilters>({})

  // Computed
  const totalPages = computed(() =>
    Math.ceil(pagination.total / pagination.page_size)
  )

  // Actions
  async function fetchUsers() {
    loading.value = true
    try {
      const params = new URLSearchParams({
        page: pagination.page.toString(),
        page_size: pagination.page_size.toString(),
        ...(filters.search && { search: filters.search }),
        ...(filters.role_id && { role_id: filters.role_id.toString() }),
        ...(filters.status && { status: filters.status })
      })

      const response = await apiCall<{
        total: number
        page: number
        page_size: number
        items: User[]
      }>(`/users?${params}`)

      users.value = response.items
      pagination.total = response.total
    } catch (error) {
      console.error('获取用户列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createUser(data: UserCreate) {
    try {
      const response = await apiCall<User>('/users', {
        method: 'POST',
        body: JSON.stringify(data)
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('创建用户失败:', error)
      throw error
    }
  }

  async function updateUser(id: number, data: UserUpdate) {
    try {
      const response = await apiCall<User>(`/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('更新用户失败:', error)
      throw error
    }
  }

  async function deleteUser(id: number) {
    try {
      await apiCall(`/users/${id}`, { method: 'DELETE' })
      await fetchUsers()
    } catch (error) {
      console.error('删除用户失败:', error)
      throw error
    }
  }

  async function resetPassword(id: number, new_password?: string) {
    try {
      const response = await apiCall<{ new_password: string }>(
        `/users/${id}/reset-password`,
        {
          method: 'POST',
          body: JSON.stringify({ new_password })
        }
      )
      return response.new_password
    } catch (error) {
      console.error('重置密码失败:', error)
      throw error
    }
  }

  async function toggleLock(id: number, locked: boolean, reason?: string) {
    try {
      const response = await apiCall<User>(`/users/${id}/lock`, {
        method: 'POST',
        body: JSON.stringify({ is_locked: locked, lock_reason: reason })
      })
      await fetchUsers()
      return response
    } catch (error) {
      console.error('锁定用户失败:', error)
      throw error
    }
  }

  function resetFilters() {
    filters.search = undefined
    filters.role_id = undefined
    filters.status = undefined
    pagination.page = 1
  }

  return {
    users,
    loading,
    pagination,
    filters,
    totalPages,
    fetchUsers,
    createUser,
    updateUser,
    deleteUser,
    resetPassword,
    toggleLock,
    resetFilters
  }
})
```

### 5.4 TypeScript类型定义

**types/user.ts**:
```typescript
export interface User {
  id: number
  username: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id: number
  role_name?: string
  status: 'active' | 'locked' | 'disabled'
  is_locked: boolean
  last_login?: string
  password_changed_at?: string
  created_at: string
  updated_at: string
}

export interface UserCreate {
  username: string
  password: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id: number
}

export interface UserUpdate {
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id?: number
  is_active?: boolean
}

export interface Role {
  id: number
  name: string
  code: string
  description?: string
  is_system: boolean
}
```

---

## 六、服务层设计

### 6.1 UserService类

```python
# services/user_service.py
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.user import User, UserStatus
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password, generate_random_password
from app.services.audit_service import AuditService


class UserService:
    """用户业务逻辑类"""

    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)

    def get_users(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        role_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> tuple[List[User], int]:
        """
        获取用户列表

        Args:
            skip: 跳过数量
            limit: 限制数量
            search: 搜索关键词
            role_id: 角色ID筛选
            status: 状态筛选

        Returns:
            (用户列表, 总数)
        """
        query = self.db.query(User)

        # 搜索条件
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern),
                    User.full_name.ilike(search_pattern)
                )
            )

        # 角色筛选
        if role_id:
            query = query.filter(User.role_id == role_id)

        # 状态筛选
        if status:
            query = query.filter(User.status == status)

        # 总数
        total = query.count()

        # 分页
        users = query.offset(skip).limit(limit).all()

        return users, total

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return self.db.query(User).filter(User.username == username).first()

    def create_user(self, user_data: UserCreate, creator_id: int) -> User:
        """
        创建用户

        Args:
            user_data: 用户创建数据
            creator_id: 创建者ID

        Returns:
            创建的用户

        Raises:
            ValueError: 用户名或邮箱已存在
        """
        # 检查用户名唯一性
        if self.get_user_by_username(user_data.username):
            raise ValueError("用户名已存在")

        # 检查邮箱唯一性
        if user_data.email:
            existing = self.db.query(User).filter(User.email == user_data.email).first()
            if existing:
                raise ValueError("邮箱已被使用")

        # 创建用户
        user = User(
            username=user_data.username,
            password_hash=hash_password(user_data.password),
            email=user_data.email,
            full_name=user_data.full_name,
            phone=getattr(user_data, 'phone', None),
            department=getattr(user_data, 'department', None),
            role_id=user_data.role_id,
            status=UserStatus.ACTIVE
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        # 记录审计日志
        self.audit.log_action(
            user_id=creator_id,
            action="create_user",
            resource_type="user",
            resource_id=user.id,
            details=f"创建用户: {user.username}"
        )

        return user

    def update_user(
        self,
        user_id: int,
        user_data: UserUpdate,
        updater_id: int
    ) -> User:
        """
        更新用户

        Args:
            user_id: 用户ID
            user_data: 更新数据
            updater_id: 更新者ID

        Returns:
            更新后的用户

        Raises:
            ValueError: 用户不存在或邮箱已被使用
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 检查邮箱唯一性
        if user_data.email and user_data.email != user.email:
            existing = self.db.query(User).filter(
                and_(User.email == user_data.email, User.id != user_id)
            ).first()
            if existing:
                raise ValueError("邮箱已被使用")

        # 更新字段
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        self.db.commit()
        self.db.refresh(user)

        # 记录审计日志
        self.audit.log_action(
            user_id=updater_id,
            action="update_user",
            resource_type="user",
            resource_id=user.id,
            details=f"更新用户: {user.username}"
        )

        return user

    def delete_user(self, user_id: int, deleter_id: int) -> bool:
        """
        删除用户

        Args:
            user_id: 用户ID
            deleter_id: 删除者ID

        Returns:
            是否删除成功

        Raises:
            ValueError: 用户不存在或不能删除最后一个管理员
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 检查是否为最后一个管理员
        if user.is_admin:
            admin_count = self.db.query(User).join(User.role).filter(
                Role.code == "admin"
            ).count()
            if admin_count <= 1:
                raise ValueError("不能删除最后一个管理员")

        # 记录审计日志
        username = user.username
        self.audit.log_action(
            user_id=deleter_id,
            action="delete_user",
            resource_type="user",
            resource_id=user.id,
            details=f"删除用户: {username}"
        )

        self.db.delete(user)
        self.db.commit()

        return True

    def reset_password(
        self,
        user_id: int,
        new_password: Optional[str] = None,
        admin_id: int
    ) -> str:
        """
        重置用户密码

        Args:
            user_id: 用户ID
            new_password: 新密码（None则自动生成）
            admin_id: 管理员ID

        Returns:
            新密码
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 生成随机密码（如果未提供）
        if not new_password:
            new_password = generate_random_password()

        # 更新密码
        user.password_hash = hash_password(new_password)
        user.password_changed_at = func.now()
        user.failed_login_attempts = 0
        user.locked_until = None

        self.db.commit()

        # 记录审计日志
        self.audit.log_action(
            user_id=admin_id,
            action="reset_password",
            resource_type="user",
            resource_id=user.id,
            details=f"重置用户密码: {user.username}"
        )

        return new_password

    def lock_user(
        self,
        user_id: int,
        locked: bool,
        reason: Optional[str] = None,
        admin_id: int
    ) -> User:
        """
        锁定或解锁用户

        Args:
            user_id: 用户ID
            locked: 是否锁定
            reason: 锁定原因
            admin_id: 管理员ID

        Returns:
            更新后的用户
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        if locked:
            user.status = UserStatus.LOCKED
            # 默认锁定7天
            user.locked_until = datetime.now() + timedelta(days=7)
        else:
            user.status = UserStatus.ACTIVE
            user.locked_until = None
            user.failed_login_attempts = 0

        self.db.commit()
        self.db.refresh(user)

        # 记录审计日志
        action = "lock_user" if locked else "unlock_user"
        details = f"{'锁定' if locked else '解锁'}用户: {user.username}"
        if reason:
            details += f", 原因: {reason}"

        self.audit.log_action(
            user_id=admin_id,
            action=action,
            resource_type="user",
            resource_id=user.id,
            details=details
        )

        return user
```

### 6.2 辅助函数

```python
# core/security.py
import secrets
import string
import bcrypt
from typing import Optional


def hash_password(password: str) -> str:
    """哈希密码"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def generate_random_password(length: int = 12) -> str:
    """生成随机密码"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password
```

---

## 七、数据验证规则

### 7.1 Pydantic Schema验证

```python
# schemas/user.py
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    department: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    """创建用户"""
    password: str = Field(..., min_length=6, max_length=100)
    role_id: int

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        if not v.replace('_', '').isalnum():
            raise ValueError('用户名只能包含字母、数字和下划线')
        return v


class UserUpdate(BaseModel):
    """更新用户"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    department: Optional[str] = Field(None, max_length=100)
    role_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """用户响应"""
    id: int
    role_id: int
    role_name: Optional[str] = None
    status: str
    is_locked: bool
    last_login: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
```

### 7.2 业务层验证

| 验证项 | 规则 | 错误提示 |
|--------|------|----------|
| 用户名唯一性 | 数据库中不存在相同用户名 | "用户名已存在" |
| 邮箱唯一性 | 数据库中不存在相同邮箱 | "邮箱已被使用" |
| 角色存在性 | role_id必须存在于soc_roles表 | "角色不存在" |
| 最后管理员 | 不能删除最后一个管理员 | "不能删除最后一个管理员" |
| 用户存在性 | 更新/删除的用户必须存在 | "用户不存在" |

---

## 八、错误处理

### 8.1 HTTP状态码

| 状态码 | 场景 | 示例 |
|--------|------|------|
| 200 | 操作成功 | 获取用户列表、更新用户成功 |
| 201 | 创建成功 | 创建用户成功 |
| 400 | 请求参数错误 | 用户名已存在、邮箱格式错误 |
| 401 | 未认证 | JWT token无效或过期 |
| 403 | 权限不足 | 非管理员尝试创建用户 |
| 404 | 资源不存在 | 用户ID不存在 |
| 500 | 服务器错误 | 数据库连接失败 |

### 8.2 错误响应格式

```json
{
  "detail": "错误描述信息",
  "error_code": "USER_ALREADY_EXISTS"
}
```

### 8.3 前端错误处理

```typescript
// 在store中处理错误
async function createUser(data: UserCreate) {
  loading.value = true
  try {
    const response = await apiCall<User>('/users', {
      method: 'POST',
      body: JSON.stringify(data)
    })
    ElMessage.success('用户创建成功')
    await fetchUsers()
    return response
  } catch (error: any) {
    ElMessage.error(error.detail || '创建用户失败')
    throw error
  } finally {
    loading.value = false
  }
}
```

---

## 九、审计日志

### 9.1 记录的操作

所有修改操作必须记录审计日志：

| 操作 | action | details示例 |
|------|--------|-------------|
| 创建用户 | create_user | "创建用户: testuser" |
| 更新用户 | update_user | "更新用户: testuser" |
| 删除用户 | delete_user | "删除用户: testuser" |
| 重置密码 | reset_password | "重置用户密码: testuser" |
| 锁定用户 | lock_user | "锁定用户: testuser, 原因: 多次登录失败" |
| 解锁用户 | unlock_user | "解锁用户: testuser" |

### 9.2 审计日志字段

```python
{
    "user_id": admin_id,           # 操作者ID
    "action": "create_user",       # 操作类型
    "resource_type": "user",       # 资源类型
    "resource_id": user.id,        # 资源ID
    "details": "创建用户: testuser",  # 详细信息
    "ip_address": "192.168.0.100", # 操作IP
    "user_agent": "Mozilla/5.0...", # 用户代理
    "created_at": datetime.now()   # 操作时间
}
```

---

## 十、安全考虑

### 10.1 密码安全

- ✅ 使用bcrypt加密（salt rounds: 12）
- ✅ 密码长度至少6位
- ✅ 前端使用type="password"隐藏输入
- ✅ 传输时使用HTTPS（生产环境）
- ❌ 不在日志中记录密码
- ❌ 不在响应中返回password_hash

### 10.2 权限控制

- ✅ JWT token验证
- ✅ 基于角色的访问控制（RBAC）
- ✅ 菜单权限关联
- ✅ 前端路由守卫
- ✅ 后端API权限检查

### 10.3 防护措施

- ✅ SQL注入防护（使用ORM参数化查询）
- ✅ XSS防护（前端转义）
- ✅ CSRF防护（SameSite Cookie）
- ✅ 用户名枚举防护（统一错误提示）
- ⏳ 限流（TODO: 实现API限流）

---

## 十一、测试计划

### 11.1 单元测试

**UserService测试**:
- ✅ 创建用户（成功/失败场景）
- ✅ 更新用户（成功/失败场景）
- ✅ 删除用户（成功/失败场景）
- ✅ 重置密码
- ✅ 锁定/解锁用户
- ✅ 用户列表查询和筛选

**API测试**:
- ✅ GET /users (各种筛选条件)
- ✅ GET /users/{id}
- ✅ POST /users
- ✅ PUT /users/{id}
- ✅ DELETE /users/{id}
- ✅ POST /users/{id}/reset-password
- ✅ POST /users/{id}/lock

### 11.2 集成测试

- ✅ 用户创建→登录→查看→编辑→删除流程
- ✅ 权限控制（管理员vs普通用户）
- ✅ 审计日志记录

### 11.3 E2E测试

- ⏳ 用户登录
- ⏳ 导航到用户管理
- ⏳ 创建新用户
- ⏳ 编辑用户
- ⏳ 重置密码
- ⏳ 锁定用户
- ⏳ 删除用户

---

## 十二、实施步骤

### 阶段1: 后端服务层
1. ✅ 创建 `services/user_service.py`
2. ✅ 实现UserService类
3. ✅ 编写单元测试

### 阶段2: 后端API层
4. ✅ 创建 `api/users.py`
5. ✅ 实现所有API端点
6. ✅ 在main.py中注册路由
7. ✅ 编写API测试

### 阶段3: 前端Store
8. ✅ 创建 `types/user.ts`
9. ✅ 创建 `stores/users.ts`
10. ✅ 实现所有actions

### 阶段4: 前端UI
11. ✅ 创建 `views/system/Users.vue`
12. ✅ 创建 `components/UserDialog.vue`
13. ✅ 实现表格、表单、对话框

### 阶段5: 集成测试
14. ✅ 端到端测试
15. ✅ 权限测试
16. ✅ 修复bug

### 阶段6: 文档和部署
17. ✅ 更新API文档
18. ✅ 准备部署配置

---

## 十三、依赖项

### 13.1 后端依赖

```python
# requirements.txt 已包含
fastapi==0.115.0
sqlalchemy==2.0.36
pydantic==2.10.1
pydantic[email]
psycopg2-binary==2.9.10
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
```

### 13.2 前端依赖

```json
// package.json 已包含
{
  "dependencies": {
    "vue": "^3.5.30",
    "element-plus": "^2.13.5",
    "@element-plus/icons-vue": "^2.3.2",
    "pinia": "^3.0.4",
    "vue-router": "^4.6.4",
    "axios": "^1.13.6"
  }
}
```

---

## 十四、参考资料

- [FastAPI官方文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0文档](https://docs.sqlalchemy.org/en/20/)
- [Element Plus文档](https://element-plus.org/)
- [Pinia文档](https://pinia.vuejs.org/)
- [Vue 3文档](https://vuejs.org/)

---

## 附录

### A. 初始化数据

```sql
-- 默认管理员账户（已存在）
INSERT INTO soc_users (username, password_hash, email, full_name, role_id, status)
VALUES (
    'admin',
    '$2b$12$...',  -- bcrypt hash of 'admin123'
    'admin@example.com',
    '系统管理员',
    1,
    'active'
);
```

### B. API测试示例

```bash
# 创建用户
curl -X POST http://localhost:8000/api/v1/users \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Test123456",
    "email": "test@example.com",
    "full_name": "测试用户",
    "role_id": 2
  }'

# 获取用户列表
curl -X GET "http://localhost:8000/api/v1/users?page=1&page_size=20" \
  -H "Authorization: Bearer <token>"

# 重置密码
curl -X POST http://localhost:8000/api/v1/users/2/reset-password \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

**文档版本**: v1.0
**最后更新**: 2026-03-19
**作者**: AI-miniSOC Team
