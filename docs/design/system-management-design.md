# 系统管理模块设计文档

**项目**: AI-miniSOC
**模块**: 系统管理（System Management）
**版本**: v1.0
**日期**: 2026-03-19
**状态**: 设计中

---

## 1. 概述

### 1.1 目标

构建完整的系统管理模块，支持：
- 用户管理（创建、编辑、删除、角色分配）
- 角色管理（角色定义、权限分配）
- 菜单管理（动态菜单配置）
- 系统配置（基础、安全、通知、API配置）
- 审计日志（完整操作审计追踪）

### 1.2 适用场景

- **用户规模**: 小型团队（< 20人）
- **部署方式**: 内网部署
- **产品定位**: 安全产品，需要完整的审计追踪

---

## 2. 权限模型

### 2.1 角色定义

| 角色 | 代码 | 权限范围 |
|------|------|----------|
| 管理员 | `admin` | 所有权限，包括系统管理 |
| 普通用户 | `user` | 业务功能权限，无系统管理权限 |
| 只读用户 | `readonly` | 仅查看数据权限 |

### 2.2 权限粒度

**菜单级别权限控制** - 用户只能访问被授权的菜单页面

---

## 3. 数据库设计

### 3.1 核心表结构

#### 用户表 (soc_users)

```sql
CREATE TABLE soc_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'active', -- active, locked, disabled
    role_id BIGINT NOT NULL REFERENCES soc_roles(id),
    last_login_at TIMESTAMP,
    password_changed_at TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_status CHECK (status IN ('active', 'locked', 'disabled'))
);

CREATE INDEX idx_users_username ON soc_users(username);
CREATE INDEX idx_users_role ON soc_users(role_id);
CREATE INDEX idx_users_email ON soc_users(email);
```

#### 角色表 (soc_roles)

```sql
CREATE TABLE soc_roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    is_system BOOLEAN DEFAULT false, -- 系统内置角色不可删除
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_role_code CHECK (code IN ('admin', 'user', 'readonly'))
);
```

#### 菜单表 (soc_menus)

```sql
CREATE TABLE soc_menus (
    id BIGSERIAL PRIMARY KEY,
    parent_id BIGINT REFERENCES soc_menus(id), -- 支持多级菜单
    name VARCHAR(50) NOT NULL,
    path VARCHAR(200) NOT NULL,
    icon VARCHAR(50),
    sort_order INTEGER DEFAULT 0,
    is_visible BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_menus_parent ON soc_menus(parent_id);
```

#### 角色菜单关联表 (soc_role_menus)

```sql
CREATE TABLE soc_role_menus (
    role_id BIGINT NOT NULL REFERENCES soc_roles(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES soc_menus(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, menu_id)
);
```

#### 系统配置表 (soc_system_config)

```sql
CREATE TABLE soc_system_config (
    id BIGSERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL, -- basic, security, notification, api
    key VARCHAR(100) NOT NULL,
    value TEXT,
    value_type VARCHAR(20) DEFAULT 'string', -- string, number, boolean, json
    is_encrypted BOOLEAN DEFAULT false,
    description TEXT,
    updated_by BIGINT REFERENCES soc_users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

CREATE INDEX idx_config_category ON soc_system_config(category);
```

#### 用户会话表 (soc_user_sessions)

```sql
CREATE TABLE soc_user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64),
    ip_address VARCHAR(45),
    user_agent TEXT,
    login_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_at TIMESTAMP,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_sessions_user ON soc_user_sessions(user_id);
CREATE INDEX idx_sessions_token ON soc_user_sessions(token_hash);
CREATE INDEX idx_sessions_active ON soc_user_sessions(is_active, last_activity_at);
```

#### 密码历史表 (soc_password_history)

```sql
CREATE TABLE soc_password_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_password_history_user ON soc_password_history(user_id, created_at DESC);
```

#### 密码重置令牌表 (soc_password_reset_tokens)

```sql
CREATE TABLE soc_password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES soc_users(id),
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reset_tokens_user ON soc_password_reset_tokens(user_id);
CREATE INDEX idx_reset_tokens_hash ON soc_password_reset_tokens(token_hash);
CREATE INDEX idx_reset_tokens_expires ON soc_password_reset_tokens(expires_at);
```

#### API限流表 (soc_rate_limits)

```sql
CREATE TABLE soc_rate_limits (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id), -- NULL表示未认证用户
    ip_address VARCHAR(45) NOT NULL,
    endpoint VARCHAR(200) NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    blocked_until TIMESTAMP
);

CREATE INDEX idx_rate_limits_user ON soc_rate_limits(user_id, window_start);
CREATE INDEX idx_rate_limits_ip ON soc_rate_limits(ip_address, window_start);
```

#### 审计日志表 (soc_audit_logs)

```sql
CREATE TABLE soc_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES soc_users(id),
    username VARCHAR(50) NOT NULL, -- 冗余，防止用户删除后无法追溯
    action VARCHAR(50) NOT NULL, -- LOGIN, LOGOUT, CREATE, UPDATE, DELETE, EXPORT, IMPORT
    resource_type VARCHAR(50), -- User, Role, Menu, Config, Asset, Incident, Alert
    resource_id BIGINT,
    resource_name VARCHAR(200), -- 冗余资源名称
    old_values JSONB, -- 变更前值
    new_values JSONB, -- 变更后值
    ip_address VARCHAR(45),
    user_agent TEXT,
    session_id BIGINT REFERENCES soc_user_sessions(id),
    request_id VARCHAR(36), -- UUID用于关联请求
    status VARCHAR(20) DEFAULT 'success', -- success, failure
    error_message TEXT,
    log_hash VARCHAR(64), -- SHA256哈希，用于防篡改
    prev_log_hash VARCHAR(64), -- 前一条日志的哈希，形成哈希链
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON soc_audit_logs(user_id);
CREATE INDEX idx_audit_action ON soc_audit_logs(action);
CREATE INDEX idx_audit_resource ON soc_audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_created ON soc_audit_logs(created_at);
CREATE INDEX idx_audit_request ON soc_audit_logs(request_id);

-- 哈希链索引，用于验证日志完整性
CREATE INDEX idx_audit_hash_chain ON soc_audit_logs(prev_log_hash, log_hash);
```

#### 审计日志完整性触发器

```sql
CREATE OR REPLACE FUNCTION calculate_audit_log_hash()
RETURNS TRIGGER AS $$
DECLARE
  log_data TEXT;
  prev_hash VARCHAR(64);
BEGIN
  -- 获取前一条日志的哈希
  SELECT log_hash INTO prev_hash
  FROM soc_audit_logs
  WHERE id < NEW.id
  ORDER BY id DESC
  LIMIT 1;

  -- 计算当前日志哈希
  log_data := NEW.user_id::TEXT || NEW.username || NEW.action ||
              COALESCE(NEW.resource_type, '') || COALESCE(NEW.resource_id::TEXT, '') ||
              COALESCE(NEW.old_values::TEXT, '') || COALESCE(NEW.new_values::TEXT, '') ||
              NEW.created_at::TEXT || COALESCE(prev_hash, '');

  NEW.log_hash := encode(digest(log_data, 'sha256'), 'hex');
  NEW.prev_log_hash := prev_hash;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_hash_trigger
  BEFORE INSERT ON soc_audit_logs
  FOR EACH ROW
  EXECUTE FUNCTION calculate_audit_log_hash();
```

---

## 4. API设计

### 4.1 认证相关

```
POST   /api/v1/auth/login              # 用户登录
POST   /api/v1/auth/logout             # 用户登出
GET    /api/v1/auth/me                 # 获取当前用户信息
POST   /api/v1/auth/change-password    # 修改密码
```

### 4.2 用户管理

```
GET    /api/v1/users/                  # 用户列表（分页、筛选）
POST   /api/v1/users/                  # 创建用户
GET    /api/v1/users/{id}              # 用户详情
PUT    /api/v1/users/{id}              # 更新用户
DELETE /api/v1/users/{id}              # 删除用户
POST   /api/v1/users/{id}/reset-password  # 重置密码
PUT    /api/v1/users/{id}/lock         # 锁定/解锁用户
```

### 4.3 角色管理

```
GET    /api/v1/roles/                  # 角色列表
POST   /api/v1/roles/                  # 创建角色
GET    /api/v1/roles/{id}              # 角色详情
PUT    /api/v1/roles/{id}              # 更新角色
DELETE /api/v1/roles/{id}              # 删除角色（系统角色不可删除）
PUT    /api/v1/roles/{id}/menus        # 分配菜单权限
GET    /api/v1/roles/{id}/menus        # 获取角色菜单
```

### 4.4 菜单管理

```
GET    /api/v1/menus/                  # 菜单树（所有用户可用）
POST   /api/v1/menus/                  # 创建菜单（仅管理员）
GET    /api/v1/menus/{id}              # 菜单详情
PUT    /api/v1/menus/{id}              # 更新菜单
DELETE /api/v1/menus/{id}              # 删除菜单
```

### 4.5 配置管理

```
GET    /api/v1/config                  # 获取所有配置（分类返回）
PUT    /api/v1/config                  # 批量更新配置
GET    /api/v1/config/{category}       # 获取分类配置
PUT    /api/v1/config/{category}       # 更新分类配置
POST   /api/v1/config/test-smtp        # 测试邮件连接
POST   /api/v1/config/test-webhook     # 测试Webhook连接
```

### 4.6 审计日志

```
GET    /api/v1/audit-logs              # 审计日志列表（支持多维度筛选）
GET    /api/v1/audit-logs/{id}         # 审计日志详情
GET    /api/v1/audit-logs/export       # 导出审计日志（CSV/Excel）
```

---

## 5. 后端架构

### 5.1 目录结构

```
src/backend/app/
├── api/
│   ├── __init__.py
│   ├── auth.py          # 认证相关API
│   ├── users.py         # 用户管理API
│   ├── roles.py         # 角色管理API
│   ├── menus.py         # 菜单管理API
│   ├── config.py        # 配置管理API
│   └── audit.py         # 审计日志API
├── core/
│   ├── __init__.py
│   ├── auth.py          # JWT认证、依赖注入
│   ├── permissions.py    # 权限检查装饰器
│   └── audit.py         # 审计日志服务
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── role.py
│   ├── menu.py
│   ├── system_config.py
│   └── audit_log.py
├── schemas/
│   ├── __init__.py
│   ├── user.py
│   ├── role.py
│   ├── menu.py
│   └── config.py
└── services/
    ├── auth_service.py
    ├── user_service.py
    ├── role_service.py
    ├── config_service.py
    └── audit_service.py
```

### 5.2 权限检查机制

```python
# core/permissions.py
from functools import wraps
from fastapi import HTTPException, Depends

def require_menu_permission(menu_path: str):
    """检查用户是否有访问菜单的权限"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if not current_user.has_menu_access(menu_path):
                raise HTTPException(status_code=403, detail="无权限访问")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

def require_admin():
    """要求管理员权限"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if not current_user.is_admin:
                raise HTTPException(status_code=403, detail="需要管理员权限")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator
```

### 5.3 审计日志服务

```python
# core/audit.py
from sqlalchemy.orm import Session
from app.models import AuditLog
from app.core.config import settings
import json

class AuditService:
    @staticmethod
    def log(
        db: Session,
        user_id: str,
        username: str,
        action: str,
        resource_type: str = None,
        resource_id: str = None,
        resource_name: str = None,
        old_values: dict = None,
        new_values: dict = None,
        ip_address: str = None,
        user_agent: str = None,
        status: str = "success",
        error_message: str = None
    ):
        """记录审计日志"""
        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message
        )
        db.add(log)
        db.commit()
```

---

## 6. 前端架构

### 6.1 目录结构

```
src/frontend/src/
├── views/
│   ├── auth/
│   │   └── Login.vue              # 登录页
│   ├── system/
│   │   ├── Users.vue              # 用户管理
│   │   ├── Roles.vue              # 角色管理
│   │   ├── Menus.vue              # 菜单管理
│   │   ├── SystemConfig.vue       # 系统配置
│   │   └── AuditLogs.vue          # 审计日志
│   └── profile/
│       └── Profile.vue            # 个人中心
├── stores/
│   ├── auth.ts                    # 认证状态（token, 用户信息）
│   ├── user.ts                    # 用户管理
│   ├── role.ts                    # 角色管理
│   ├── menu.ts                    # 菜单管理
│   └── config.ts                  # 系统配置
├── router/
│   └── index.ts                   # 路由配置 + 权限守卫
└── api/
    └── client.ts                  # API客户端（添加拦截器）
```

### 6.2 路由配置

```typescript
// router/index.ts
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/auth/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/system',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'users',
        name: 'SystemUsers',
        component: () => import('@/views/system/Users.vue'),
        meta: { menuId: 'menu-system-users', requiresAdmin: true }
      },
      {
        path: 'roles',
        name: 'SystemRoles',
        component: () => import('@/views/system/Roles.vue'),
        meta: { menuId: 'menu-system-roles', requiresAdmin: true }
      },
      {
        path: 'menus',
        name: 'SystemMenus',
        component: () => import('@/views/system/Menus.vue'),
        meta: { menuId: 'menu-system-menus', requiresAdmin: true }
      },
      {
        path: 'config',
        name: 'SystemConfig',
        component: () => import('@/views/system/SystemConfig.vue'),
        meta: { menuId: 'menu-system-config', requiresAdmin: true }
      },
      {
        path: 'audit',
        name: 'AuditLogs',
        component: () => import('@/views/system/AuditLogs.vue'),
        meta: { menuId: 'menu-system-audit', requiresAdmin: true }
      }
    ]
  }
]
```

### 6.3 路由守卫

```typescript
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 1. 检查是否需要登录
  if (to.meta.requiresAuth !== false && !authStore.isLoggedIn) {
    return next('/login')
  }

  // 2. 已登录用户访问登录页，跳转到首页
  if (to.path === '/login' && authStore.isLoggedIn) {
    return next('/dashboard')
  }

  // 3. 检查管理员权限
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return next('/403')
  }

  // 4. 检查菜单权限
  if (to.meta.menuId && !authStore.hasMenuPermission(to.meta.menuId)) {
    return next('/403')
  }

  next()
})
```

### 6.4 认证Store

```typescript
// stores/auth.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<any>(null)
  const menus = ref<any[]>([])

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role_code === 'admin')

  const hasMenuPermission = (menuId: string) => {
    return menus.value.some(m => m.id === menuId)
  }

  const login = async (credentials: any) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials)
    })
    const data = await response.json()

    token.value = data.token
    user.value = data.user
    menus.value = data.menus

    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  const logout = () => {
    token.value = null
    user.value = null
    menus.value = []
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return {
    token,
    user,
    menus,
    isLoggedIn,
    isAdmin,
    hasMenuPermission,
    login,
    logout
  }
})
```

---

## 7. 配置分类详细设计

### 7.1 基础配置 (basic)

| 键 | 类型 | 默认值 | 描述 |
|---|------|--------|------|
| system_name | string | AI-miniSOC | 系统名称 |
| system_logo | string | /logo.png | Logo URL |
| theme | string | dark | 默认主题 |
| timezone | string | Asia/Shanghai | 时区 |
| language | string | zh-CN | 语言 |

### 7.2 安全策略 (security)

| 键 | 类型 | 默认值 | 描述 |
|---|------|--------|------|
| password_min_length | number | 8 | 密码最小长度 |
| password_require_special | boolean | true | 是否需要特殊字符 |
| password_expire_days | number | 90 | 密码过期天数（0=永不过期） |
| login_max_attempts | number | 5 | 最大登录尝试次数 |
| login_lockout_minutes | number | 30 | 锁定时长（分钟） |
| session_timeout_minutes | number | 120 | 会话超时（分钟） |

### 7.3 通知配置 (notification)

**邮件通知**
| 键 | 类型 | 描述 |
|---|------|------|
| email_enabled | boolean | 启用邮件 |
| email_smtp_host | string | SMTP服务器 |
| email_smtp_port | number | SMTP端口 |
| email_username | string | 邮箱用户名 |
| email_password | string (加密) | 邮箱密码 |
| email_from | string | 发件人地址 |

**钉钉通知**
| 键 | 类型 | 描述 |
|---|------|------|
| dingtalk_enabled | boolean | 启用钉钉 |
| dingtalk_webhook | string | Webhook URL |
| dingtalk_secret | string (加密) | 加密密钥 |

**微信通知**
| 键 | 类型 | 描述 |
|---|------|------|
| wechat_enabled | boolean | 启用微信 |
| wechat_webhook | string | Webhook URL |

### 7.4 API配置 (api)

**Wazuh配置**
| 键 | 类型 | 描述 |
|---|------|------|
| wazuh_api_url | string | Wazuh API地址 |
| wazuh_username | string | 用户名 |
| wazuh_password | string (加密) | 密码 |

**智谱AI配置**
| 键 | 类型 | 描述 |
|---|------|------|
| glm_api_key | string (加密) | API Key |
| glm_model | string | 模型名称（glm-4-flash） |

---

## 8. 审计日志范围

### 8.1 必须审计的操作

**A. 认证审计**
- 用户登录（成功/失败）
- 用户登出
- 密码修改
- 密码重置

**B. 用户管理审计**
- 创建/删除用户
- 修改用户信息
- 修改用户角色
- 锁定/解锁用户

**C. 权限审计**
- 角色创建/删除
- 角色权限变更
- 菜单创建/删除/修改
- 菜单权限分配

**D. 配置审计**
- 系统配置修改
- 安全策略变更
- 通知配置变更
- API配置变更

**E. 数据操作审计**
- 资产创建/删除
- 事件状态变更
- 告警处置
- 批量操作

**F. 敏感操作审计**
- 数据导出
- 数据导入
- API密钥查看
- 配置备份/恢复

### 8.2 审计日志保留策略

- 在线保留：90天
- 归档保留：1年
- 超过保留期的日志自动归档到对象存储

---

## 9. 安全设计

### 9.1 密码安全

- 使用 bcrypt 加密存储（work factor 12）
- 密码强度校验：最小长度、大小写、数字、特殊字符
- 首次登录强制修改默认密码
- 密码修改后重新生成会话token
- 记录密码修改历史（防止重复使用旧密码）

### 9.2 Token安全

- Access Token 有效期：2小时
- Refresh Token 有效期：7天
- Token 存储位置：**推荐 httpOnly cookies**（安全选项，防止XSS攻击）
- 支持 Token 黑名单（Redis实现，需要添加Redis到基础设施）
- 登出时将 token 加入黑名单

### 9.3 敏感配置加密

- 使用 AES-256-GCM 加密
- 加密密钥从环境变量读取
- 配置返回时自动脱敏（显示 `****`）
- 仅在测试连接时解敏验证

### 9.4 防护措施

- 登录失败5次锁定账户30分钟
- 支持IP白名单（可选）
- API限流（防止暴力破解）
- SQL注入防护（使用ORM参数化查询）
- XSS防护（前端输出转义）

---

## 10. 错误处理

### 10.1 统一错误响应格式

```json
{
  "success": false,
  "error_code": "PERMISSION_DENIED",
  "message": "无权限访问",
  "detail": {}
}
```

### 10.2 错误码定义

| 错误码 | HTTP状态 | 描述 |
|--------|---------|------|
| AUTH_REQUIRED | 401 | 需要登录 |
| INVALID_TOKEN | 401 | Token无效或过期 |
| PERMISSION_DENIED | 403 | 权限不足 |
| INVALID_CREDENTIALS | 401 | 用户名或密码错误 |
| USER_LOCKED | 403 | 用户已锁定 |
| PASSWORD_EXPIRED | 403 | 密码已过期 |
| USER_NOT_FOUND | 404 | 用户不存在 |
| ROLE_NOT_FOUND | 404 | 角色不存在 |
| DUPLICATE_USERNAME | 400 | 用户名已存在 |
| WEAK_PASSWORD | 400 | 密码强度不足 |
| CONFIG_ENCRYPTED | 403 | 配置已加密，无法查看明文 |

---

## 11. 初始化数据

### 11.1 默认角色

```sql
-- 管理员
INSERT INTO soc_roles (id, name, code, description, is_system)
VALUES ('00000000-0000-0000-0000-000000000001', '管理员', 'admin', '系统管理员，拥有所有权限', true);

-- 普通用户
INSERT INTO soc_roles (id, name, code, description, is_system)
VALUES ('00000000-0000-0000-0000-000000000002', '普通用户', 'user', '普通用户，可使用业务功能', true);

-- 只读用户
INSERT INTO soc_roles (id, name, code, description, is_system)
VALUES ('00000000-0000-0000-0000-000000000003', '只读用户', 'readonly', '只读用户，仅可查看数据', true);
```

### 11.2 默认管理员账户

```
用户名: admin
密码: 系统首次启动时自动生成随机强密码（显示在控制台/日志中）
      首次登录后强制修改密码
角色: 管理员
```

### 11.3 默认菜单

```sql
-- 业务菜单
INSERT INTO soc_menus (id, parent_id, name, path, icon, sort_order) VALUES
  ('menu-dashboard', NULL, '概览仪表板', '/dashboard', 'DataAnalysis', 1),
  ('menu-assets', NULL, '资产管理', '/assets', 'Monitor', 2),
  ('menu-incidents', NULL, '事件管理', '/incidents', 'Warning', 3),
  ('menu-alerts', NULL, '告警管理', '/alerts', 'Bell', 4);

-- 系统管理（父菜单）
INSERT INTO soc_menus (id, parent_id, name, path, icon, sort_order)
VALUES ('menu-system', NULL, '系统管理', '/system', 'Setting', 5);

-- 系统管理子菜单
INSERT INTO soc_menus (id, parent_id, name, path, icon, sort_order) VALUES
  ('menu-system-users', 'menu-system', '用户管理', '/system/users', 'User', 1),
  ('menu-system-roles', 'menu-system', '角色管理', '/system/roles', 'Lock', 2),
  ('menu-system-menus', 'menu-system', '菜单管理', '/system/menus', 'Menu', 3),
  ('menu-system-config', 'menu-system', '系统配置', '/system/config', 'Setting', 4),
  ('menu-system-audit', 'menu-system', '审计日志', '/system/audit', 'Document', 5);

-- 管理员拥有所有菜单权限
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT '00000000-0000-0000-0000-000000000001', id FROM soc_menus;

-- 普通用户拥有业务菜单权限（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT '00000000-0000-0000-0000-000000000002', id FROM soc_menus WHERE id NOT LIKE 'menu-system%';

-- 只读用户拥有查看权限（不含系统管理）
INSERT INTO soc_role_menus (role_id, menu_id)
SELECT '00000000-0000-0000-0000-000000000003', id FROM soc_menus WHERE id NOT LIKE 'menu-system%';
```

### 11.4 默认配置

```sql
-- 基础配置
INSERT INTO soc_system_config (category, key, value, description) VALUES
  ('basic', 'system_name', 'AI-miniSOC', '系统名称'),
  ('basic', 'theme', 'dark', '默认主题'),
  ('basic', 'timezone', 'Asia/Shanghai', '时区');

-- 安全策略
INSERT INTO soc_system_config (category, key, value, value_type, description) VALUES
  ('security', 'password_min_length', '8', 'number', '密码最小长度'),
  ('security', 'password_require_special', 'true', 'boolean', '需要特殊字符'),
  ('security', 'login_max_attempts', '5', 'number', '最大登录尝试次数'),
  ('security', 'session_timeout_minutes', '120', 'number', '会话超时（分钟）');
```

---

## 12. 实施步骤

### 阶段1：数据库和认证（优先级：高）

1. 创建数据库表（用户、角色、菜单、审计日志）
2. 实现JWT认证逻辑
3. 创建登录页面
4. 实现权限检查中间件
5. 初始化默认数据

**交付物**：
- 可用的登录功能
- JWT Token认证
- 基本的权限检查

### 阶段2：用户和角色管理（优先级：高）

1. 用户管理CRUD
2. 角色管理CRUD
3. 菜单权限分配
4. 前端管理页面
5. **密码重置功能**（邮件重置链接）
6. **会话管理**（查看/撤销用户会话）
7. **双因素认证（2FA）**（TOTP - 基于时间的一次性密码）
8. 密码历史记录（防止重复使用旧密码）

**交付物**：
- 用户管理功能
- 角色管理功能
- 动态菜单加载
- 密码重置流程
- 会话管理界面
- 2FA启用和验证

### 阶段3：系统配置（优先级：中）

1. 配置管理API
2. 配置加密/解密
3. 配置验证
4. 前端配置页面

**交付物**：
- 系统配置管理
- 安全策略配置
- 通知配置

### 阶段4：审计日志（优先级：高）

1. 审计日志服务
2. 审计中间件
3. 审计日志查询
4. 前端审计页面

**交付物**：
- 完整的审计追踪
- 审计日志查询和导出

### 阶段5：测试和优化（优先级：中）

1. 单元测试
2. 集成测试
3. 安全测试
4. 性能优化

---

## 13. 技术栈确认

### 后端

- FastAPI 0.115.0+
- SQLAlchemy 2.0+
- Pydantic 2.0+
- PyJWT 2.8+
- bcrypt 4.1+ (密码加密)
- cryptography 41+ (配置加密)
- Redis 7+ (Token黑名单、会话缓存、API限流)
- pyotp 2.9+ (2FA TOTP生成)

### 前端

- Vue.js 3
- Pinia (状态管理)
- Vue Router 4
- TypeScript
- Element Plus

### 数据库

- PostgreSQL 16+
- Redis 7+ (缓存和会话管理)

---

## 14. 性能和可扩展性要求

### 14.1 性能指标

**API响应时间**：
- 认证接口（登录/登出）：< 500ms (95th percentile)
- 用户/角色管理接口：< 200ms (95th percentile)
- 配置管理接口：< 300ms (95th percentile)
- 审计日志查询：< 2秒 (100万条记录)

**并发能力**：
- 支持 100 并发用户
- 支持 1000 TPS (每秒事务数)
- 数据库连接池：20-50连接

**数据库性能**：
- 审计日志表分区（按月分区）
- 关键字段建立索引
- 定期清理过期数据

### 14.2 可扩展性设计

**水平扩展**：
- 无状态API服务（支持多实例部署）
- Redis集群（用于会话共享）
- 数据库读写分离（主从复制）

**数据归档策略**：
- 审计日志：90天在线，1年归档
- 会话记录：30天后自动清理
- 密码重置令牌：24小时过期清理

### 14.3 监控指标

**关键指标监控**：
- API响应时间和错误率
- 数据库连接池使用率
- Redis内存使用率
- 活跃会话数
- 登录失败率

**告警规则**：
- API错误率 > 5%
- 数据库连接池使用率 > 80%
- 某IP登录失败次数 > 10次/分钟
- 系统配置变更告警

---

## 15. 后续扩展方向

1. **OAuth2/LDAP集成** - 支持企业SSO
2. **多租户支持** - 数据隔离
3. **细粒度权限** - 按钮级别权限控制
4. **数据权限** - 行级数据权限控制
5. **审计日志增强** - 支持日志归档、检索、分析、AI异常检测
6. **用户行为分析** - UEBA（用户和实体行为分析）

---

**文档版本**: v1.1
**最后更新**: 2026-03-19
**状态**: 已修订，待最终审核
