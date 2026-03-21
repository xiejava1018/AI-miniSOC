# 角色管理API文档

## 概述

角色管理API提供完整的角色CRUD操作和菜单权限分配功能。

## 基础信息

- **基础路径**: `/api/v1/roles`
- **认证方式**: Bearer Token (JWT)
- **权限要求**: 所有端点需要管理员权限

## API端点

### 1. 获取角色列表

**请求**
```
GET /api/v1/roles?page=1&page_size=20&search=admin
```

**响应**
```json
{
  "total": 10,
  "items": [
    {
      "id": 1,
      "name": "管理员",
      "code": "admin",
      "description": "系统管理员",
      "is_system": true,
      "user_count": 5,
      "created_at": "2026-03-21T00:00:00Z",
      "updated_at": "2026-03-21T00:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20
}
```

### 2. 创建角色

**请求**
```
POST /api/v1/roles
Content-Type: application/json

{
  "name": "安全分析师",
  "code": "security_analyst",
  "description": "负责安全事件分析",
  "menu_ids": [1, 2, 3]
}
```

**响应**
```json
{
  "id": 4,
  "name": "安全分析师",
  "code": "security_analyst",
  "description": "负责安全事件分析",
  "is_system": false,
  "user_count": 0,
  "created_at": "2026-03-21T00:00:00Z",
  "updated_at": "2026-03-21T00:00:00Z"
}
```

### 3. 更新角色

**请求**
```
PUT /api/v1/roles/{id}
Content-Type: application/json

{
  "name": "高级安全分析师",
  "description": "负责复杂安全事件分析"
}
```

### 4. 删除角色

**请求**
```
DELETE /api/v1/roles/{id}
```

**响应**
```json
{
  "success": true,
  "message": "角色已删除"
}
```

### 5. 分配菜单权限

**请求**
```
PUT /api/v1/roles/{id}/menus
Content-Type: application/json

{
  "menu_ids": [1, 2, 3, 4, 5]
}
```

## 错误码

| 错误码 | 描述 |
|--------|------|
| 403 | 需要管理员权限 |
| 404 | 角色不存在 |
| 400 | 角色代码已存在 / 角色正在被使用 / 系统角色不能修改或删除 |

## 使用示例

### cURL

```bash
# 获取角色列表
curl -X GET "http://localhost:8000/api/v1/roles" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 创建角色
curl -X POST "http://localhost:8000/api/v1/roles" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试角色",
    "code": "test_role",
    "description": "这是一个测试角色"
  }'
```

### Python

```python
import requests

headers = {"Authorization": f"Bearer {token}"}

# 获取角色列表
response = requests.get("http://localhost:8000/api/v1/roles", headers=headers)
roles = response.json()

# 创建角色
data = {
    "name": "测试角色",
    "code": "test_role",
    "description": "这是一个测试角色"
}
response = requests.post("http://localhost:8000/api/v1/roles", json=data, headers=headers)
```

### JavaScript

```javascript
// 获取角色列表
const response = await fetch('/api/v1/roles', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
const roles = await response.json()

// 创建角色
const response = await fetch('/api/v1/roles', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: '测试角色',
    code: 'test_role',
    description: '这是一个测试角色'
  })
})
```
