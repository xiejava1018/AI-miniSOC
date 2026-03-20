# 用户管理API文档

## 概述

用户管理API提供用户CRUD操作、状态管理和密码管理功能。

## 基础信息

- **Base URL**: `/api/v1`
- **认证方式**: JWT Bearer Token
- **内容类型**: `application/json`

## 认证

所有API请求需要在HTTP Header中携带JWT Token：

```http
Authorization: Bearer <access_token>
```

## 端点列表

### 1. 获取用户列表

获取系统中的用户列表，支持分页、搜索和筛选。

**请求**
```http
GET /api/v1/users?page=1&page_size=20&search=admin&role_id=1&status=active
```

**查询参数**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | integer | 否 | 1 | 页码 |
| page_size | integer | 否 | 20 | 每页数量（最大100） |
| search | string | 否 | - | 搜索关键词（用户名/邮箱/姓名） |
| role_id | integer | 否 | - | 角色ID |
| status | string | 否 | - | 状态（active/locked/disabled） |

**响应**
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
      "last_login": "2026-03-20T10:00:00Z",
      "created_at": "2026-03-19T10:00:00Z",
      "updated_at": "2026-03-20T10:00:00Z"
    }
  ]
}
```

### 2. 获取用户详情

获取指定用户的详细信息。

**请求**
```http
GET /api/v1/users/{id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| id | integer | 用户ID |

**响应**
```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "full_name": "系统管理员",
  "phone": "1234567890",
  "department": "IT部门",
  "role_id": 1,
  "role_name": "管理员",
  "status": "active",
  "is_locked": false,
  "last_login": "2026-03-20T10:00:00Z",
  "password_changed_at": "2026-03-19T10:00:00Z",
  "created_at": "2026-03-19T10:00:00Z",
  "updated_at": "2026-03-20T10:00:00Z"
}
```

**错误响应**
```json
{
  "detail": "用户不存在"
}
```

### 3. 创建用户

创建新用户账号。

**请求**
```http
POST /api/v1/users
Content-Type: application/json

{
  "username": "newuser",
  "password": "Test123456",
  "email": "new@example.com",
  "full_name": "新用户",
  "phone": "13800138000",
  "department": "技术部",
  "role_id": 2
}
```

**请求体字段**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名（3-50字符） |
| password | string | 是 | 密码（至少6位） |
| email | string | 否 | 邮箱地址 |
| full_name | string | 否 | 真实姓名 |
| phone | string | 否 | 手机号 |
| department | string | 否 | 部门 |
| role_id | integer | 是 | 角色ID |

**响应**
```json
{
  "id": 10,
  "username": "newuser",
  "email": "new@example.com",
  "full_name": "新用户",
  "role_id": 2,
  "status": "active",
  "is_locked": false,
  "created_at": "2026-03-20T10:00:00Z",
  "updated_at": "2026-03-20T10:00:00Z"
}
```

**错误响应**
```json
{
  "detail": "用户名已存在"
}
```

### 4. 更新用户

更新用户信息。

**请求**
```http
PUT /api/v1/users/{id}
Content-Type: application/json

{
  "email": "updated@example.com",
  "full_name": "更新后的姓名",
  "phone": "13900139000",
  "department": "产品部",
  "role_id": 3
}
```

**请求体字段**

所有字段都是可选的。

| 字段 | 类型 | 说明 |
|------|------|------|
| email | string | 邮箱地址 |
| full_name | string | 真实姓名 |
| phone | string | 手机号 |
| department | string | 部门 |
| role_id | integer | 角色ID |

**响应**
```json
{
  "id": 10,
  "username": "newuser",
  "email": "updated@example.com",
  "full_name": "更新后的姓名",
  "role_id": 3,
  "updated_at": "2026-03-20T11:00:00Z"
}
```

**错误响应**
```json
{
  "detail": "用户不存在"
}
```

### 5. 删除用户

删除指定用户。

**请求**
```http
DELETE /api/v1/users/{id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| id | integer | 用户ID |

**响应**
```json
{
  "success": true,
  "message": "用户已删除"
}
```

**错误响应**
```json
{
  "detail": "不能删除最后一个管理员"
}
```

### 6. 重置用户密码

重置指定用户的密码。

**请求**
```http
POST /api/v1/users/{id}/reset-password
Content-Type: application/json

{
  "new_password": "NewPass123"
}
```

**请求体字段**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| new_password | string | 否 | 新密码。如果为空，则自动生成随机密码 |

**响应**
```json
{
  "success": true,
  "message": "密码已重置",
  "new_password": "NewPass123"
}
```

**注意**: 如果未提供`new_password`，系统将自动生成随机密码并在响应中返回。

### 7. 锁定/解锁用户

锁定或解锁用户账号。

**请求**
```http
POST /api/v1/users/{id}/lock
Content-Type: application/json

{
  "is_locked": true,
  "lock_reason": "多次登录失败"
}
```

**请求体字段**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| is_locked | boolean | 是 | true=锁定，false=解锁 |
| lock_reason | string | 否 | 锁定原因 |

**响应**
```json
{
  "id": 10,
  "username": "newuser",
  "status": "locked",
  "is_locked": true,
  "locked_until": "2026-03-27T10:00:00Z"
}
```

## 权限说明

### 管理员权限

以下操作需要管理员权限：

- ✅ 创建用户
- ✅ 更新用户
- ✅ 删除用户
- ✅ 重置密码
- ✅ 锁定/解锁用户

### 普通用户权限

- ✅ 查看用户列表
- ✅ 查看用户详情

## 错误码

| HTTP状态码 | 说明 |
|-----------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

## 数据模型

### User

```typescript
interface User {
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
```

### UserCreate

```typescript
interface UserCreate {
  username: string
  password: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id: number
}
```

### UserUpdate

```typescript
interface UserUpdate {
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id?: number
  is_active?: boolean
}
```

## 使用示例

### cURL示例

```bash
# 获取用户列表
curl -X GET "http://localhost:8000/api/v1/users?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 创建用户
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "Test123456",
    "email": "test@example.com",
    "role_id": 2
  }'

# 重置密码
curl -X POST "http://localhost:8000/api/v1/users/10/reset-password" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_password": "NewPass123"}'
```

### Python示例

```python
import requests

API_BASE = "http://localhost:8000/api/v1"
TOKEN = "your_jwt_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# 获取用户列表
response = requests.get(
    f"{API_BASE}/users",
    headers=headers,
    params={"page": 1, "page_size": 20}
)
users = response.json()

# 创建用户
new_user = {
    "username": "testuser",
    "password": "Test123456",
    "email": "test@example.com",
    "role_id": 2
}
response = requests.post(
    f"{API_BASE}/users",
    headers=headers,
    json=new_user
)
user = response.json()
```

### JavaScript示例

```javascript
const API_BASE = 'http://localhost:8000/api/v1';
const TOKEN = 'your_jwt_token';

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Content-Type': 'application/json'
};

// 获取用户列表
fetch(`${API_BASE}/users?page=1&page_size=20`, { headers })
  .then(res => res.json())
  .then(data => console.log(data));

// 创建用户
const newUser = {
  username: 'testuser',
  password: 'Test123456',
  email: 'test@example.com',
  role_id: 2
};

fetch(`${API_BASE}/users`, {
  method: 'POST',
  headers,
  body: JSON.stringify(newUser)
})
  .then(res => res.json())
  .then(data => console.log(data));
```

## 注意事项

1. **密码安全**
   - 密码最小长度为6位
   - 建议使用强密码（包含大小写字母、数字和特殊字符）
   - 重置密码后，新密码仅在响应中返回一次

2. **用户删除**
   - 不能删除最后一个管理员
   - 删除操作不可恢复，请谨慎操作

3. **用户锁定**
   - 默认锁定时间为7天
   - 锁定后用户无法登录
   - 解锁后需要重置登录失败次数

4. **分页查询**
   - 最大每页数量为100
   - 建议使用合理的分页大小以提高性能

5. **搜索功能**
   - 搜索支持用户名、邮箱和姓名
   - 搜索为模糊匹配
   - 可与其他筛选条件组合使用

## 相关文档

- [认证API](./auth-api.md)
- [角色管理API](./roles-api.md)
- [系统管理模块设计](../design/system-management-design.md)
