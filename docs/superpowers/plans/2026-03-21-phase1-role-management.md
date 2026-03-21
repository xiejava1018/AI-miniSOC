# Phase 1: 角色管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现完整的角色管理功能，包括角色CRUD、菜单权限分配和系统角色保护

**Architecture:**
- 后端：FastAPI + SQLAlchemy，提供7个RESTful API端点
- 前端：Vue 3 + TypeScript + Element Plus，角色管理页面和Store
- 权限：基于菜单的RBAC，系统角色严格保护

**Tech Stack:**
- 后端：FastAPI, Pydantic, SQLAlchemy, PostgreSQL
- 前端：Vue 3, Pinia, Element Plus, TypeScript
- 测试：Pytest (后端), Vitest (前端), Playwright (E2E)

**Dependencies:**
- 数据库表已存在（soc_roles, soc_role_menus, soc_users）
- 认证系统已实现
- 前端路由和API客户端基础已存在

---

## 文件结构

### 后端文件
```
src/backend/app/
├── api/
│   ├── __init__.py (修改: 注册roles路由)
│   └── roles.py (新建: 角色API端点)
├── core/
│   └── permissions.py (新建: 权限检查装饰器)
├── schemas/
│   └── role.py (新建: 角色Pydantic schemas)
├── services/
│   └── role_service.py (新建: 角色业务逻辑)
└── models/
    └── role.py (已存在: 无需修改)
```

### 前端文件
```
src/frontend/src/
├── api/
│   └── role.ts (新建: 角色API客户端)
├── stores/
│   └── roles.ts (新建: 角色Pinia store)
├── views/system/
│   └── Roles.vue (新建: 角色管理页面)
├── router/
│   └── index.ts (修改: 添加角色路由)
└── types/
    └── role.ts (新建: 角色TypeScript类型)
```

### 测试文件
```
src/backend/tests/
├── test_role_service.py (新建: 角色服务测试)
└── test_roles_api.py (新建: 角色API测试)

src/frontend/tests/
├── unit/stores/roles.test.ts (新建: 角色store测试)
└── e2e/04-roles.spec.ts (新建: 角色E2E测试)
```

---

## Task 1: 更新角色Pydantic Schemas

**Files:**
- Modify: `src/backend/app/schemas/role.py`

**背景**: 现有schema包含`is_active`字段，需要添加`code`、`menu_ids`、`is_system`、`user_count`字段以支持角色管理功能

- [ ] **Step 1: 更新schemas/role.py，添加新字段和schema**

在现有文件基础上添加以下内容：

```python
# 在文件开头添加导入
from datetime import datetime
from typing import List

# 更新 RoleCreate，添加 code 和 menu_ids 字段
class RoleCreate(RoleBase):
    """创建角色"""
    code: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="角色代码")
    menu_ids: List[int] = Field(default_factory=list, description="关联的菜单ID列表")
    is_active: bool = Field(default=True, description="是否激活")  # 保留现有字段

# 更新 RoleUpdate，添加 menu_ids 字段
class RoleUpdate(BaseModel):
    """更新角色"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="角色名称")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    menu_ids: Optional[List[int]] = Field(None, description="菜单ID列表")
    is_active: Optional[bool] = Field(None, description="是否激活")  # 保留现有字段
    # 注意: 不包含 code 字段，因为系统角色不能修改代码

# 更新 RoleResponse，添加 is_system 和 user_count 字段
class RoleResponse(RoleBase):
    """角色响应"""
    id: int = Field(..., description="角色ID")
    code: str = Field(..., description="角色代码")  # 添加
    is_active: bool = Field(..., description="是否激活")  # 保留现有字段
    is_system: bool = Field(..., description="是否系统角色")  # 新增
    user_count: int = Field(default=0, description="用户数量")  # 新增
    created_at: datetime = Field(..., description="创建时间")  # 修改为datetime类型
    updated_at: datetime = Field(..., description="更新时间")  # 修改为datetime类型

    class Config:
        from_attributes = True

# 新增 RoleListResponse
class RoleListResponse(BaseModel):
    """角色列表响应"""
    total: int = Field(..., description="总数")
    items: List[RoleResponse] = Field(..., description="角色列表")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页数量")

# 更新 RoleMenusRequest 为更通用的名称
class RoleMenusRequest(BaseModel):
    """菜单权限分配请求"""
    menu_ids: List[int] = Field(..., description="菜单ID列表")
```

- [ ] **Step 2: 运行Python语法检查**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && python -m py_compile app/schemas/role.py`
Expected: 无错误

- [ ] **Step 3: 提交schema文件**

```bash
git add src/backend/app/schemas/role.py
git commit -m "feat: add role Pydantic schemas

Add RoleBase, RoleCreate, RoleUpdate, RoleResponse schemas
for role management API.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 实现角色服务层

**Files:**
- Create: `src/backend/app/services/role_service.py`
- Modify: `src/backend/app/services/__init__.py`

- [ ] **Step 1: 创建services/role_service.py并实现RoleService类**

```python
# src/backend/app/services/role_service.py
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.role import Role
from app.models.user import User
from app.models.menu import Menu
from app.schemas.role import RoleCreate, RoleUpdate


class RoleService:
    """角色服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_roles(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> Tuple[List[Role], int]:
        """
        获取角色列表

        Args:
            skip: 跳过记录数
            limit: 返回记录数
            search: 搜索关键词（名称或代码）

        Returns:
            (角色列表, 总数)
        """
        query = self.db.query(Role)

        if search:
            query = query.filter(
                (Role.name.ilike(f"%{search}%")) |
                (Role.code.ilike(f"%{search}%"))
            )

        total = query.count()
        roles = query.offset(skip).limit(limit).all()

        return roles, total

    def get_role_by_id(self, role_id: int) -> Role:
        """根据ID获取角色"""
        role = self.db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError("角色不存在")
        return role

    def create_role(self, role_data: RoleCreate, creator_id: int) -> Role:
        """
        创建角色

        Args:
            role_data: 角色创建数据
            creator_id: 创建者ID

        Returns:
            创建的角色对象

        Raises:
            ValueError: 角色代码已存在
        """
        # 检查code唯一性
        existing = self.db.query(Role).filter(Role.code == role_data.code).first()
        if existing:
            raise ValueError("角色代码已存在")

        # 创建角色
        role = Role(
            name=role_data.name,
            code=role_data.code,
            description=role_data.description,
            is_system=False
        )
        self.db.add(role)
        self.db.flush()

        # 分配菜单权限
        if role_data.menu_ids:
            menus = self.db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def update_role(self, role_id: int, role_data: RoleUpdate, updater_id: int) -> Role:
        """
        更新角色

        Args:
            role_id: 角色ID
            role_data: 更新数据
            updater_id: 更新者ID

        Returns:
            更新后的角色

        Raises:
            ValueError: 角色不存在或系统角色不能修改代码
        """
        role = self.get_role_by_id(role_id)

        # 系统角色不能修改code
        if role.is_system and hasattr(role_data, 'code') and role_data.code != role.code:
            raise ValueError("系统角色不能修改代码")

        # 更新字段
        if role_data.name:
            role.name = role_data.name
        if role_data.description is not None:
            role.description = role_data.description

        # 更新菜单权限
        if role_data.menu_ids is not None:
            menus = self.db.query(Menu).filter(Menu.id.in_(role_data.menu_ids)).all()
            role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def delete_role(self, role_id: int, deleter_id: int) -> None:
        """
        删除角色

        Args:
            role_id: 角色ID
            deleter_id: 删除者ID

        Raises:
            ValueError: 角色不存在、系统角色或正在被使用
        """
        role = self.get_role_by_id(role_id)

        # 系统角色不能删除
        if role.is_system:
            raise ValueError("系统角色不能删除")

        # 检查是否有用户使用
        user_count = self.db.query(User).filter(User.role_id == role_id).count()
        if user_count > 0:
            raise ValueError(f"该角色正在被 {user_count} 个用户使用，无法删除")

        self.db.delete(role)
        self.db.commit()

    def get_role_menus(self, role_id: int) -> List[Menu]:
        """获取角色的菜单列表"""
        role = self.get_role_by_id(role_id)
        return role.menus

    def assign_menus(self, role_id: int, menu_ids: List[int]) -> Role:
        """
        分配菜单权限

        Args:
            role_id: 角色ID
            menu_ids: 菜单ID列表

        Returns:
            更新后的角色
        """
        role = self.get_role_by_id(role_id)

        menus = self.db.query(Menu).filter(Menu.id.in_(menu_ids)).all()
        role.menus = menus

        self.db.commit()
        self.db.refresh(role)
        return role

    def get_role_users(self, role_id: int) -> List[User]:
        """获取使用该角色的用户列表"""
        role = self.get_role_by_id(role_id)
        return self.db.query(User).filter(User.role_id == role_id).all()
```

- [ ] **Step 2: 运行Python语法检查**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && python -m py_compile app/services/role_service.py`
Expected: 无错误

- [ ] **Step 3: 提交服务层代码**

```bash
git add src/backend/app/services/role_service.py
git commit -m "feat: implement RoleService with CRUD operations

Implement role management business logic:
- get_roles with search and pagination
- create_role with menu assignment
- update_role with system role protection
- delete_role with user count check
- assign_menus for permission management
- get_role_users to list role users

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 创建权限检查装饰器

**Files:**
- Create: `src/backend/app/core/permissions.py`

- [ ] **Step 1: 创建core/permissions.py并实现装饰器**

```python
# src/backend/app/core/permissions.py
from functools import wraps
from fastapi import HTTPException, status, Depends
from typing import Callable

from app.core.auth import get_current_user
from app.schemas.user import UserResponse


def require_admin() -> Callable:
    """
    要求管理员权限装饰器

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            current_user: UserResponse = Depends(require_admin())
        ):
            ...
    """
    async def _check_admin(current_user: UserResponse = Depends(get_current_user)):
        # 修复: 使用 role_name 而不是 is_admin
        if current_user.role_name != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user

    return _check_admin


def require_menu_permission(menu_path: str) -> Callable:
    """
    要求菜单权限装饰器

    Args:
        menu_path: 菜单路径

    Usage:
        @router.get("/system/users")
        async def get_users(
            current_user: UserResponse = Depends(require_menu_permission("system-users"))
        ):
            ...
    """
    async def _check_permission(current_user: UserResponse = Depends(get_current_user)):
        if not current_user.has_menu_access(menu_path):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问"
            )
        return current_user

    return _check_permission
```

- [ ] **Step 2: 运行Python语法检查**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && python -m py_compile app/core/permissions.py`
Expected: 无错误

- [ ] **Step 3: 提交权限装饰器**

```bash
git add src/backend/app/core/permissions.py
git commit -m "feat: add permission check decorators

Add require_admin and require_menu_permission decorators
for protecting API endpoints based on user roles and menu access.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 实现角色API端点

**Files:**
- Create: `src/backend/app/api/roles.py`
- Modify: `src/backend/app/api/__init__.py`

- [ ] **Step 1: 创建api/roles.py并实现API端点**

```python
# src/backend/app/api/roles.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    RoleMenusRequest
)
from app.services.role_service import RoleService


router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("", response_model=RoleListResponse)
async def get_roles(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    获取角色列表

    需要权限: admin
    """
    service = RoleService(db)
    skip = (page - 1) * page_size

    roles, total = service.get_roles(
        skip=skip,
        limit=page_size,
        search=search
    )

    # 为每个角色添加用户数
    items = []
    for role in roles:
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role.id))
        items.append(RoleResponse(**role_dict))

    return RoleListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取角色详情"""
    service = RoleService(db)
    try:
        role = service.get_role_by_id(role_id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role_id))
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    创建角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        role = service.create_role(role_data, creator_id=current_user.id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = 0
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    更新角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        role = service.update_role(role_id, role_data, updater_id=current_user.id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role_id))
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    删除角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        service.delete_role(role_id, deleter_id=current_user.id)
        return {"success": True, "message": "角色已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{role_id}/menus")
async def get_role_menus(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取角色的菜单列表"""
    service = RoleService(db)
    try:
        menus = service.get_role_menus(role_id)
        return {
            "role_id": role_id,
            "menu_ids": [menu.id for menu in menus],
            "menus": [menu.to_dict() for menu in menus]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{role_id}/menus")
async def assign_role_menus(
    role_id: int,
    menus_data: RoleMenusRequest,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """分配菜单权限"""
    service = RoleService(db)
    try:
        role = service.assign_menus(role_id, menus_data.menu_ids)
        return {
            "success": True,
            "message": "菜单权限已分配",
            "role": RoleResponse.model_validate(role).model_dump()
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{role_id}/users")
async def get_role_users(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取使用该角色的用户列表"""
    service = RoleService(db)
    try:
        users = service.get_role_users(role_id)
        return {
            "role_id": role_id,
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "email": user.email,
                    "status": user.status
                }
                for user in users
            ]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
```

- [ ] **Step 2: 修改api/__init__.py注册角色路由**

在 `src/backend/app/api/__init__.py` 中添加：

```python
# 在文件开头的import部分添加
from app.api import roles

# 在 api_router.include_router 调用列表中添加
api_router.include_router(roles.router, prefix="/roles", tags=["角色管理"])
```

完整的文件应该是：
```python
"""
API 路由汇总
"""

from fastapi import APIRouter
from app.api import auth, users, assets, incidents, alerts, ai, roles

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])
api_router.include_router(assets.router, prefix="/assets", tags=["资产管理"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["事件管理"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["告警管理"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI分析"])
api_router.include_router(roles.router, prefix="/roles", tags=["角色管理"])  # 新增
```

- [ ] **Step 3: 验证路由注册**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend && python -c "from app.api import api_router; routes = [r.path for r in api_router.routes if hasattr(r, 'path')]; print('Registered routes:', routes)"
```

Expected: 输出包含 `/api/v1/roles`

- [ ] **Step 4: 提交路由注册**

```bash
git add src/backend/app/api/__init__.py
git commit -m "feat: register roles router in api_router

Add roles router to centralized API router registration.
All role endpoints now accessible at /api/v1/roles/*

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 5: 运行Python语法检查**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && python -m py_compile app/api/roles.py`
Expected: 无错误

- [ ] **Step 6: 提交API代码**

```bash
git add src/backend/app/api/roles.py src/backend/app/api/__init__.py
git commit -m "feat: implement role management API endpoints

Add 7 role management API endpoints:
- GET /api/v1/roles - list roles with pagination
- GET /api/v1/roles/{id} - get role details
- POST /api/v1/roles - create role
- PUT /api/v1/roles/{id} - update role
- DELETE /api/v1/roles/{id} - delete role
- GET /api/v1/roles/{id}/menus - get role menus
- PUT /api/v1/roles/{id}/menus - assign menus

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 初始化数据库角色数据

**Files:**
- Create: `src/backend/scripts/init_roles.sql`

- [ ] **Step 1: 创建初始化SQL脚本**

```bash
cat > /home/xiejava/AIproject/AI-miniSOC/src/backend/scripts/init_roles.sql << 'EOF'
-- 初始化系统内置角色

-- 系统内置角色
INSERT INTO soc_roles (name, code, description, is_system) VALUES
('管理员', 'admin', '系统管理员，拥有所有权限', true),
('普通用户', 'user', '普通用户，可使用业务功能', true),
('只读用户', 'readonly', '只读用户，仅可查看数据', true)
ON CONFLICT (code) DO NOTHING;

-- 显示插入结果
SELECT id, name, code, is_system FROM soc_roles WHERE code IN ('admin', 'user', 'readonly');
EOF
```

- [ ] **Step 2: 执行SQL脚本**

Run:
```bash
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U postgres -d AI-miniSOC -f src/backend/scripts/init_roles.sql
```

Expected: 显示3个角色被插入

- [ ] **Step 3: 验证数据**

Run:
```bash
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U postgres -d AI-miniSOC -c "SELECT id, name, code, is_system FROM soc_roles WHERE code IN ('admin', 'user', 'readonly');"
```

Expected: 返回3条角色记录

- [ ] **Step 4: 提交初始化脚本**

```bash
git add src/backend/scripts/init_roles.sql
git commit -m "chore: add role initialization SQL script

Add system built-in roles:
- admin (system administrator)
- user (regular user)
- readonly (read-only user)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 后端单元测试

**Files:**
- Create: `src/backend/tests/test_role_service.py`
- Create: `src/backend/tests/test_roles_api.py`

- [ ] **Step 1: 创建服务层测试**

```python
# src/backend/tests/test_role_service.py
import pytest
from sqlalchemy.orm import Session

from app.services.role_service import RoleService
from app.schemas.role import RoleCreate, RoleUpdate
from app.models.role import Role
from app.models.user import User


class TestRoleService:
    """角色服务测试"""

    def test_get_roles_empty(self, db: Session):
        """测试获取空角色列表"""
        service = RoleService(db)
        roles, total = service.get_roles(skip=0, limit=20)

        assert total == 0
        assert roles == []

    def test_create_role(self, db: Session):
        """测试创建角色"""
        service = RoleService(db)
        role_data = RoleCreate(
            name="测试角色",
            code="test_role",
            description="这是一个测试角色"
        )

        role = service.create_role(role_data, creator_id=1)

        assert role.id is not None
        assert role.name == "测试角色"
        assert role.code == "test_role"
        assert role.is_system is False

    def test_create_role_duplicate_code(self, db: Session):
        """测试创建角色时代码重复"""
        service = RoleService(db)
        role_data = RoleCreate(
            name="测试角色",
            code="test_role"
        )

        # 第一次创建成功
        service.create_role(role_data, creator_id=1)

        # 第二次创建应该失败
        with pytest.raises(ValueError, match="角色代码已存在"):
            service.create_role(role_data, creator_id=1)

    def test_update_role(self, db: Session):
        """测试更新角色"""
        service = RoleService(db)

        # 先创建角色
        role_data = RoleCreate(name="原始名称", code="test_role")
        role = service.create_role(role_data, creator_id=1)

        # 更新角色
        update_data = RoleUpdate(name="更新后的名称")
        updated_role = service.update_role(role.id, update_data, updater_id=1)

        assert updated_role.name == "更新后的名称"

    def test_update_system_role_code(self, db: Session):
        """测试系统角色不能修改代码"""
        service = RoleService(db)

        # 创建系统角色
        role = Role(
            name="系统角色",
            code="system_role",
            is_system=True
        )
        db.add(role)
        db.commit()

        # 尝试修改代码
        update_data = RoleUpdate(code="new_code")
        with pytest.raises(ValueError, match="系统角色不能修改代码"):
            service.update_role(role.id, update_data, updater_id=1)

    def test_delete_role(self, db: Session):
        """测试删除角色"""
        service = RoleService(db)

        # 创建角色
        role_data = RoleCreate(name="待删除角色", code="delete_me")
        role = service.create_role(role_data, creator_id=1)

        # 删除角色
        service.delete_role(role.id, deleter_id=1)

        # 验证已删除
        with pytest.raises(ValueError, match="角色不存在"):
            service.get_role_by_id(role.id)

    def test_delete_system_role(self, db: Session):
        """测试系统角色不能删除"""
        service = RoleService(db)

        # 创建系统角色
        role = Role(
            name="系统角色",
            code="system_role",
            is_system=True
        )
        db.add(role)
        db.commit()

        # 尝试删除
        with pytest.raises(ValueError, match="系统角色不能删除"):
            service.delete_role(role.id, deleter_id=1)

    def test_delete_role_with_users(self, db: Session):
        """测试有用户的角色不能删除"""
        service = RoleService(db)

        # 创建用户和角色
        role = Role(name="测试角色", code="test_role", is_system=False)
        db.add(role)
        db.flush()

        user = User(
            username="test_user",
            password_hash="hash",
            role_id=role.id
        )
        db.add(user)
        db.commit()

        # 尝试删除
        with pytest.raises(ValueError, match="正在被.*个用户使用"):
            service.delete_role(role.id, deleter_id=1)
```

- [ ] **Step 2: 运行服务层测试**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend && source venv/bin/activate && pytest tests/test_role_service.py -v
```

Expected: 所有测试通过

- [ ] **Step 3: 提交测试代码**

```bash
git add src/backend/tests/test_role_service.py
git commit -m "test: add role service unit tests

Add comprehensive unit tests for RoleService:
- create_role with validation
- update_role with system role protection
- delete_role with user count check
- duplicate code prevention
- system role protection

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 前端 - 创建角色类型定义

**Files:**
- Create: `src/frontend/src/types/role.ts`

- [ ] **Step 1: 创建types/role.ts**

```typescript
// src/frontend/src/types/role.ts
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

export interface RoleCreate {
  name: string
  code: string
  description?: string
  menu_ids?: number[]
}

export interface RoleUpdate {
  name?: string
  description?: string
  menu_ids?: number[]
}

export interface RoleListResponse {
  total: number
  items: Role[]
  page: number
  page_size: number
}

export interface RoleMenusRequest {
  menu_ids: number[]
}
```

- [ ] **Step 2: 提交类型定义**

```bash
git add src/frontend/src/types/role.ts
git commit -m "feat: add role TypeScript type definitions

Add Role, RoleCreate, RoleUpdate, and RoleListResponse types.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 前端 - 创建角色API客户端

**Files:**
- Create: `src/frontend/src/api/role.ts`

- [ ] **Step 1: 创建api/role.ts**

```typescript
// src/frontend/src/api/role.ts
import axios from 'axios'
import type { Role, RoleCreate, RoleUpdate, RoleListResponse, RoleMenusRequest } from '@/types/role'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const roleApi = {
  async getRoles(params?: { page?: number; page_size?: number; search?: string }): Promise<RoleListResponse> {
    const response = await axios.get<RoleListResponse>(`${API_BASE}/roles`, { params })
    return response.data
  },

  async getRole(id: number): Promise<Role> {
    const response = await axios.get<Role>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async createRole(data: RoleCreate): Promise<Role> {
    const response = await axios.post<Role>(`${API_BASE}/roles`, data)
    return response.data
  },

  async updateRole(id: number, data: RoleUpdate): Promise<Role> {
    const response = await axios.put<Role>(`${API_BASE}/roles/${id}`, data)
    return response.data
  },

  async deleteRole(id: number): Promise<{ success: boolean; message: string }> {
    const response = await axios.delete<{ success: boolean; message: string }>(`${API_BASE}/roles/${id}`)
    return response.data
  },

  async getRoleMenus(id: number): Promise<{ role_id: number; menu_ids: number[]; menus: any[] }> {
    const response = await axios.get(`${API_BASE}/roles/${id}/menus`)
    return response.data
  },

  async assignMenus(id: number, data: RoleMenusRequest): Promise<{ success: boolean; message: string; role: Role }> {
    const response = await axios.put(`${API_BASE}/roles/${id}/menus`, data)
    return response.data
  },

  async getRoleUsers(id: number): Promise<{ role_id: number; users: any[] }> {
    const response = await axios.get(`${API_BASE}/roles/${id}/users`)
    return response.data
  }
}
```

- [ ] **Step 2: 提交API客户端**

```bash
git add src/frontend/src/api/role.ts
git commit -m "feat: add role API client

Add axios-based API client for role management:
- getRoles with pagination
- createRole, updateRole, deleteRole
- getRoleMenus, assignMenus
- getRoleUsers

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8b: 前端 - 创建菜单API客户端

**Files:**
- Create: `src/frontend/src/api/menu.ts`

**背景**: Roles.vue的菜单权限对话框需要获取菜单树数据

- [ ] **Step 1: 创建api/menu.ts**

```typescript
// src/frontend/src/api/menu.ts
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface Menu {
  id: number
  parent_id?: number
  name: string
  path: string
  icon: string
  sort_order: number
  is_visible: boolean
}

export const menuApi = {
  async getMenus(): Promise<Menu[]> {
    const response = await axios.get<Menu[]>(`${API_BASE}/menus`)
    return response.data
  },

  async getMenuTree(): Promise<Menu[]> {
    const response = await axios.get<Menu[]>(`${API_BASE}/menus/tree`)
    return response.data
  },

  async getMenuOptions(): Promise<any[]> {
    const response = await axios.get(`${API_BASE}/menus/options`)
    return response.data
  }
}
```

- [ ] **Step 2: 提交Menu API客户端**

```bash
git add src/frontend/src/api/menu.ts
git commit -m "feat: add menu API client

Add axios-based API client for menu operations:
- getMenus - get flat menu list
- getMenuTree - get hierarchical menu tree
- getMenuOptions - get parent menu options for dropdown

Required by Roles.vue menu permission dialog.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 前端 - 创建角色Store

**Files:**
- Create: `src/frontend/src/stores/roles.ts`

- [ ] **Step 1: 创建stores/roles.ts**

```typescript
// src/frontend/src/stores/roles.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Role, RoleCreate, RoleUpdate } from '@/types/role'
import { roleApi } from '@/api/role'
import { ElMessage } from 'element-plus'

export const useRolesStore = defineStore('roles', () => {
  const roles = ref<Role[]>([])
  const loading = ref(false)
  const pagination = ref({
    page: 1,
    page_size: 20,
    total: 0
  })

  async function fetchRoles(params?: { page?: number; search?: string }) {
    loading.value = true
    try {
      const response = await roleApi.getRoles({
        page: params?.page || pagination.value.page,
        page_size: pagination.value.page_size,
        search: params?.search
      })
      roles.value = response.items
      pagination.value.total = response.total
      pagination.value.page = response.page
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '获取角色列表失败')
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createRole(data: RoleCreate) {
    try {
      await roleApi.createRole(data)
      ElMessage.success('角色创建成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '创建角色失败')
      throw error
    }
  }

  async function updateRole(id: number, data: RoleUpdate) {
    try {
      await roleApi.updateRole(id, data)
      ElMessage.success('角色更新成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '更新角色失败')
      throw error
    }
  }

  async function deleteRole(id: number) {
    try {
      await roleApi.deleteRole(id)
      ElMessage.success('角色删除成功')
      await fetchRoles()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '删除角色失败')
      throw error
    }
  }

  async function assignMenus(roleId: number, menuIds: number[]) {
    try {
      await roleApi.assignMenus(roleId, { menu_ids: menuIds })
      ElMessage.success('菜单权限分配成功')
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '分配菜单权限失败')
      throw error
    }
  }

  function resetFilters() {
    pagination.value.page = 1
  }

  return {
    roles,
    loading,
    pagination,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
    assignMenus,
    resetFilters
  }
})
```

- [ ] **Step 2: 提交Store**

```bash
git add src/frontend/src/stores/roles.ts
git commit -m "feat: add roles Pinia store

Implement roles state management with actions:
- fetchRoles with pagination
- createRole, updateRole, deleteRole
- assignMenus for permission management
- error handling with ElMessage

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 前端 - 创建角色管理页面

**Files:**
- Create: `src/frontend/src/views/system/Roles.vue`
- Modify: `src/frontend/src/router/index.ts`

- [ ] **Step 1: 创建views/system/Roles.vue**

由于文件较长，分为多个步骤完成。

首先创建文件头部和模板：

```vue
<!-- src/frontend/src/views/system/Roles.vue -->
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRolesStore } from '@/stores/roles'
import { useAuthStore } from '@/stores/auth'
import { roleApi } from '@/api/role'
import { menuApi } from '@/api/menu'  // 添加菜单API导入
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
```

- [ ] **Step 2: 添加角色路由**

修改 `src/frontend/src/router/index.ts`，在系统管理路由中添加：

```typescript
{
  path: 'roles',
  name: 'SystemRoles',
  component: () => import('@/views/system/Roles.vue'),
  meta: { title: '角色管理', requiresAuth: true }
}
```

- [ ] **Step 3: 运行TypeScript类型检查**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/frontend && npm run type-check
```

Expected: 无类型错误

- [ ] **Step 4: 提交角色页面**

```bash
git add src/frontend/src/views/system/Roles.vue src/frontend/src/router/index.ts
git commit -m "feat: add role management page

Implement Roles.vue with:
- Role list with search and pagination
- Create/Edit role dialog
- Delete role with confirmation
- System role protection (disabled delete button)
- Menu permission assignment dialog

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: 前端单元测试

**Files:**
- Create: `src/frontend/tests/unit/stores/roles.test.ts`

- [ ] **Step 1: 创建roles store测试**

```typescript
// src/frontend/tests/unit/stores/roles.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRolesStore } from '@/stores/roles'
import { roleApi } from '@/api/role'
import { ElMessage } from 'element-plus'

vi.mock('@/api/role')
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn()
  }
}))

describe('Roles Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('fetchRoles should update roles and pagination', async () => {
    const mockResponse = {
      total: 2,
      items: [
        { id: 1, name: '管理员', code: 'admin', is_system: true, user_count: 1 },
        { id: 2, name: '普通用户', code: 'user', is_system: true, user_count: 5 }
      ],
      page: 1,
      page_size: 20
    }

    vi.mocked(roleApi.getRoles).mockResolvedValue(mockResponse)

    const store = useRolesStore()
    await store.fetchRoles()

    expect(store.roles).toEqual(mockResponse.items)
    expect(store.pagination.total).toBe(2)
  })

  it('createRole should call API and refresh list', async () => {
    const newRole = {
      id: 3,
      name: '测试角色',
      code: 'test',
      is_system: false,
      user_count: 0
    }

    vi.mocked(roleApi.createRole).mockResolvedValue(newRole)
    vi.mocked(roleApi.getRoles).mockResolvedValue({
      total: 3,
      items: [newRole],
      page: 1,
      page_size: 20
    })

    const store = useRolesStore()
    await store.createRole({
      name: '测试角色',
      code: 'test'
    })

    expect(roleApi.createRole).toHaveBeenCalledWith({
      name: '测试角色',
      code: 'test'
    })
    expect(ElMessage.success).toHaveBeenCalledWith('角色创建成功')
  })

  it('deleteRole should handle system role protection', async () => {
    const systemRole = {
      id: 1,
      name: '管理员',
      code: 'admin',
      is_system: true,
      user_count: 1
    }

    vi.mocked(roleApi.deleteRole).mockRejectedValue({
      response: { data: { detail: '系统角色不能删除' } }
    })

    const store = useRolesStore()
    await expect(store.deleteRole(systemRole.id)).rejects.toThrow()

    expect(ElMessage.error).toHaveBeenCalledWith('系统角色不能删除')
  })
})
```

- [ ] **Step 2: 运行前端单元测试**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/frontend && npm test tests/unit/stores/roles.test.ts
```

Expected: 测试通过

- [ ] **Step 3: 提交测试**

```bash
git add src/frontend/tests/unit/stores/roles.test.ts
git commit -m "test: add roles store unit tests

Add comprehensive unit tests for roles store:
- fetchRoles pagination
- createRole success flow
- deleteRole error handling
- system role protection

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: E2E测试

**Files:**
- Create: `src/frontend/tests/e2e/04-roles.spec.ts`

- [ ] **Step 1: 创建E2E测试**

```typescript
// src/frontend/tests/e2e/04-roles.spec.ts
import { test, expect } from '@playwright/test'

test.describe('角色管理', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('http://localhost:5173/login')
    await page.fill('[data-testid="username-input"]', 'admin')
    await page.fill('[data-testid="password-input"]', 'admin123')
    await page.click('[data-testid="login-button"]')
    await page.waitForURL('**/dashboard')
  })

  test('should display role list page', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 验证页面标题
    await expect(page.locator('text=角色管理')).toBeVisible()

    // 验证创建按钮
    await expect(page.locator('button:has-text("创建角色")')).toBeVisible()
  })

  test('should display list of roles', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 验证角色列表表格
    const table = page.locator('.el-table')
    await expect(table).toBeVisible()

    // 验证系统角色标签
    const systemTags = page.locator('.el-tag--warning:has-text("系统")')
    await expect(systemTags).toHaveCount(3) // admin, user, readonly
  })

  test('should create new role', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 点击创建按钮
    await page.click('button:has-text("创建角色")')

    // 填写表单
    await page.fill('input[placeholder="请输入角色名称"]', '测试角色')
    await page.fill('input[placeholder="请输入角色代码"]', 'test_role')
    await page.fill('textarea[placeholder="请输入角色描述"]', '这是一个测试角色')

    // 提交
    await page.click('.el-dialog button:has-text("确定")')

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible()

    // 验证新角色出现在列表中
    await expect(page.locator('text=测试角色')).toBeVisible()
  })

  test('should not delete system role', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 找到管理员角色的删除按钮
    const adminRow = page.locator('tr').filter({ hasText: '管理员' })
    const deleteButton = adminRow.locator('button:has-text("删除")')

    // 验证删除按钮被禁用
    await expect(deleteButton).toBeDisabled()
  })

  test('should edit custom role', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 点击编辑按钮（假设有一个自定义角色）
    const customRoleRow = page.locator('tr').filter({ hasText: '测试角色' })
    await customRoleRow.locator('button:has-text("编辑")').click()

    // 修改名称
    await page.fill('input[placeholder="请输入角色名称"]', '修改后的角色')

    // 提交
    await page.click('.el-dialog button:has-text("确定")')

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible()
  })

  test('should search roles', async ({ page }) => {
    await page.goto('http://localhost:5173/system/roles')

    // 搜索角色
    await page.fill('input[placeholder="搜索角色名称或代码"]', 'admin')

    // 验证搜索结果
    await expect(page.locator('text=管理员')).toBeVisible()
  })
})
```

- [ ] **Step 2: 提交E2E测试**

```bash
git add src/frontend/tests/e2e/04-roles.spec.ts
git commit -m "test: add role management E2E tests

Add Playwright E2E tests for role management:
- Display role list page
- Create new role
- System role protection (delete disabled)
- Edit custom role
- Search roles

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13: 集成测试和文档

**Files:**
- Create: `docs/api/roles-api.md`

- [ ] **Step 1: 创建API文档**

```markdown
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
```

- [ ] **Step 2: 运行完整测试套件**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend && source venv/bin/activate && pytest tests/test_role_service.py tests/test_roles_api.py -v
```

Expected: 所有测试通过

- [ ] **Step 3: 运行前端测试**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/frontend && npm test
```

Expected: 所有测试通过

- [ ] **Step 4: 提交文档**

```bash
git add docs/api/roles-api.md
git commit -m "docs: add role management API documentation

Add comprehensive API documentation for role management:
- Endpoint descriptions
- Request/response examples
- Error codes
- Usage examples in cURL, Python, JavaScript

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 14: 最终提交和推送

- [ ] **Step 1: 查看所有提交**

Run:
```bash
cd /home/xiejava/AIproject/AI-miniSOC && git log --oneline -15
```

- [ ] **Step 2: 推送到GitHub**

Run:
```bash
git push origin master
```

Expected: 所有提交成功推送

- [ ] **Step 3: 创建GitHub Release（可选）**

在GitHub上创建Release标记Phase 1完成：
- 标题: "Phase 1: 角色管理"
- 描述: 实现完整的角色管理功能，包括CRUD、菜单权限分配和系统角色保护

---

## 验收标准

### 功能验收
- [ ] 可以创建自定义角色
- [ ] 可以编辑角色（系统角色不能修改代码）
- [ ] 可以删除自定义角色（系统角色不能删除）
- [ ] 可以分配菜单权限给角色
- [ ] 可以查看角色的用户列表
- [ ] 搜索和分页功能正常

### 安全验收
- [ ] 系统角色（admin/user/readonly）不能删除
- [ ] 系统角色代码不能修改
- [ ] 有用户的角色不能删除
- [ ] 所有API需要管理员权限

### 测试验收
- [ ] 后端单元测试通过率100%
- [ ] 前端单元测试通过率100%
- [ ] E2E测试通过率100%

### 文档验收
- [ ] API文档完整
- [ ] 代码注释充分
- [ ] 使用示例清晰

---

## 预计工作量

- **后端开发**: 4-6小时
- **前端开发**: 4-6小时
- **测试**: 2-3小时
- **文档**: 1-2小时
- **总计**: 11-17小时（约2个工作日）

---

## 依赖和阻塞

### 前置依赖
- ✅ 数据库表已创建
- ✅ 认证系统已实现
- ✅ 用户管理已完成

### 后续Phase依赖
- Phase 2 (菜单管理) 无依赖
- Phase 3 (动态菜单) 依赖Phase 1 + Phase 2
- Phase 4 (审计日志) 无依赖

---

**下一步**: 完成 Phase 2: 菜单管理实施计划
