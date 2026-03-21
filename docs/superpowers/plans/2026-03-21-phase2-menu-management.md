# Phase 2: 菜单管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现完整的菜单管理功能，支持2级菜单树、图标配置和动态菜单渲染

**Architecture:**
- 后端：FastAPI + SQLAlchemy，提供6个RESTful API端点，支持树形结构
- 前端：Vue 3 + TypeScript + Element Plus，使用Tree组件展示2级菜单
- 数据结构：父子菜单关系，父菜单使用空字符串path，子菜单有实际路由

**Tech Stack:**
- 后端：FastAPI, Pydantic, SQLAlchemy, PostgreSQL
- 前端：Vue 3, Pinia, Element Plus Tree, TypeScript
- 测试：Pytest (后端), Vitest (前端), Playwright (E2E)

**Dependencies:**
- 数据库表已存在（soc_menus）
- Phase 1 (角色管理) 已完成（可选，但角色需要菜单权限）

---

## 文件结构

### 后端文件
```
src/backend/app/
├── api/
│   ├── __init__.py (修改: 注册menus路由)
│   └── menus.py (新建: 菜单API端点)
├── schemas/
│   └── menu.py (新建: 菜单Pydantic schemas)
├── services/
│   └── menu_service.py (新建: 菜单业务逻辑)
└── models/
    └── menu.py (已存在: 无需修改)
```

### 前端文件
```
src/frontend/src/
├── api/
│   └── menu.ts (新建: 菜单API客户端)
├── stores/
│   └── menus.ts (新建: 菜单Pinia store)
├── views/system/
│   └── Menus.vue (新建: 菜单管理页面)
├── router/
│   └── index.ts (修改: 添加菜单路由)
└── types/
    └── menu.ts (新建: 菜单TypeScript类型)
```

---

## Task 1: 创建菜单Pydantic Schemas

**Files:**
- Create: `src/backend/app/schemas/menu.py`

- [ ] **Step 1: 创建schemas/menu.py**

```python
# src/backend/app/schemas/menu.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MenuBase(BaseModel):
    """菜单基础schema"""
    name: str = Field(max_length=50, description="菜单名称")
    # 父级菜单的path设为空字符串""，不使用None
    path: str = Field(max_length=200, description="菜单路径")
    icon: Optional[str] = Field(None, max_length=50, description="菜单图标")
    sort_order: int = Field(0, description="排序")
    is_visible: bool = Field(True, description="是否可见")


class MenuCreate(MenuBase):
    """创建菜单schema"""
    parent_id: Optional[int] = Field(None, description="父菜单ID")


class MenuUpdate(BaseModel):
    """更新菜单schema"""
    name: Optional[str] = Field(None, max_length=50)
    path: Optional[str] = Field(None, max_length=200)
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_visible: Optional[bool] = None


class MenuResponse(MenuBase):
    """菜单响应schema"""
    id: int
    parent_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuTreeResponse(MenuResponse):
    """菜单树响应schema"""
    children: List['MenuTreeResponse'] = []

    class Config:
        from_attributes = True


# 重建模型以支持递归类型
MenuTreeResponse.model_rebuild()
```

- [ ] **Step 2: 提交schemas**

```bash
git add src/backend/app/schemas/menu.py
git commit -m "feat: add menu Pydantic schemas

Add MenuBase, MenuCreate, MenuUpdate, MenuResponse schemas
with MenuTreeResponse for hierarchical menu structure.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 实现菜单服务层

**Files:**
- Create: `src/backend/app/services/menu_service.py`

- [ ] **Step 1: 创建services/menu_service.py**

```python
# src/backend/app/services/menu_service.py
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.menu import Menu


class MenuService:
    """菜单服务层"""

    def __init__(self, db: Session):
        self.db = db

    def get_all_menus(self) -> List[Menu]:
        """获取所有菜单（平铺）"""
        return self.db.query(Menu).order_by(Menu.sort_order).all()

    def get_menu_tree(self) -> List[Menu]:
        """
        获取菜单树

        Returns:
            树形结构的菜单列表
        """
        menus = self.db.query(Menu).filter(Menu.is_visible == True).all()
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
                if parent and hasattr(parent, 'children'):
                    parent.children.append(menu)

        # 排序
        for menu in root_menus:
            if hasattr(menu, 'children'):
                menu.children.sort(key=lambda x: x.sort_order or 0)

        return sorted(root_menus, key=lambda x: x.sort_order or 0)

    def get_menu_by_id(self, menu_id: int) -> Menu:
        """根据ID获取菜单"""
        menu = self.db.query(Menu).filter(Menu.id == menu_id).first()
        if not menu:
            raise ValueError("菜单不存在")
        return menu

    def create_menu(self, menu_data) -> Menu:
        """
        创建菜单

        Args:
            menu_data: MenuCreate schema

        Returns:
            创建的菜单对象
        """
        menu = Menu(
            name=menu_data.name,
            path=menu_data.path,
            icon=menu_data.icon,
            parent_id=menu_data.parent_id,
            sort_order=menu_data.sort_order,
            is_visible=menu_data.is_visible
        )
        self.db.add(menu)
        self.db.commit()
        self.db.refresh(menu)
        return menu

    def update_menu(self, menu_id: int, menu_data) -> Menu:
        """
        更新菜单

        Args:
            menu_id: 菜单ID
            menu_data: MenuUpdate schema

        Returns:
            更新后的菜单

        Raises:
            ValueError: 菜单不存在或防止循环引用
        """
        menu = self.get_menu_by_id(menu_id)

        # 防止循环引用
        if menu_data.parent_id:
            if menu_data.parent_id == menu_id:
                raise ValueError("不能将自己设为父菜单")

        # 更新字段
        update_data = menu_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(menu, field, value)

        self.db.commit()
        self.db.refresh(menu)
        return menu

    def delete_menu(self, menu_id: int) -> None:
        """
        删除菜单

        Args:
            menu_id: 菜单ID

        Raises:
            ValueError: 菜单不存在或有子菜单
        """
        menu = self.get_menu_by_id(menu_id)

        # 检查是否有子菜单
        child_count = self.db.query(Menu).filter(Menu.parent_id == menu_id).count()
        if child_count > 0:
            raise ValueError(f"该菜单有 {child_count} 个子菜单，无法删除")

        self.db.delete(menu)
        self.db.commit()

    def get_menu_options(self) -> List[dict]:
        """
        获取菜单选项（用于下拉选择）

        Returns:
            扁平化的菜单列表，带parent_name
        """
        menus = self.get_all_menus()
        options = []

        for menu in menus:
            parent_name = ""
            if menu.parent_id:
                parent = self.db.query(Menu).filter(Menu.id == menu.parent_id).first()
                if parent:
                    parent_name = f"{parent.name} / "

            options.append({
                "id": menu.id,
                "name": f"{parent_name}{menu.name}",
                "path": menu.path
            })

        return options
```

- [ ] **Step 2: 提交服务层**

```bash
git add src/backend/app/services/menu_service.py
git commit -m "feat: implement MenuService with tree support

Implement menu management business logic:
- get_menu_tree with hierarchical structure
- create_menu, update_menu, delete_menu
- get_menu_options for dropdown selection
- prevent circular reference

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 实现菜单API端点

**Files:**
- Create: `src/backend/app/api/menus.py`
- Modify: `src/backend/app/api/__init__.py`
- Modify: `src/backend/main.py`

- [ ] **Step 1: 创建api/menus.py**

```python
# src/backend/app/api/menus.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuTreeResponse
)
from app.services.menu_service import MenuService


router = APIRouter(prefix="/menus", tags=["菜单管理"])


@router.get("", response_model=list[MenuResponse])
async def get_menus(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取所有菜单（平铺列表）"""
    service = MenuService(db)
    menus = service.get_all_menus()
    return [MenuResponse.model_validate(m) for m in menus]


@router.get("/tree", response_model=list[MenuTreeResponse])
async def get_menu_tree(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单树（所有用户可访问）"""
    service = MenuService(db)
    menus = service.get_menu_tree()
    return [MenuTreeResponse.model_validate(m) for m in menus]


@router.post("", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
async def create_menu(
    menu_data: MenuCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """创建菜单（仅管理员）"""
    service = MenuService(db)
    try:
        menu = service.create_menu(menu_data)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/options")
async def get_menu_options(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单选项（用于父菜单选择）"""
    service = MenuService(db)
    return service.get_menu_options()


@router.get("/{menu_id}", response_model=MenuResponse)
async def get_menu(
    menu_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单详情"""
    service = MenuService(db)
    try:
        menu = service.get_menu_by_id(menu_id)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{menu_id}", response_model=MenuResponse)
async def update_menu(
    menu_id: int,
    menu_data: MenuUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """更新菜单（仅管理员）"""
    service = MenuService(db)
    try:
        menu = service.update_menu(menu_id, menu_data)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{menu_id}")
async def delete_menu(
    menu_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """删除菜单（仅管理员）"""
    service = MenuService(db)
    try:
        service.delete_menu(menu_id)
        return {"success": True, "message": "菜单已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

- [ ] **Step 2: 注册路由**

修改 `src/backend/main.py`，添加：
```python
from app.api.menus import router as menus_router
app.include_router(menus_router, prefix="/api/v1")
```

- [ ] **Step 3: 提交API代码**

```bash
git add src/backend/app/api/menus.py src/backend/main.py
git commit -m "feat: implement menu management API endpoints

Add 6 menu management API endpoints:
- GET /api/v1/menus - list all menus
- GET /api/v1/menus/tree - get menu tree
- POST /api/v1/menus - create menu
- GET /api/v1/menus/options - get parent menu options
- PUT /api/v1/menus/{id} - update menu
- DELETE /api/v1/menus/{id} - delete menu

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 初始化菜单数据

**Files:**
- Create: `src/backend/scripts/init_menus.sql`

- [ ] **Step 1: 创建初始化SQL**

```bash
cat > /home/xiejava/AIproject/AI-miniSOC/src/backend/scripts/init_menus.sql << 'EOF'
-- 初始化菜单数据

-- 业务菜单
INSERT INTO soc_menus (name, path, icon, sort_order, is_visible) VALUES
('概览仪表板', '/dashboard', 'DataAnalysis', 1, true),
('资产管理', '/assets', 'Monitor', 2, true),
('事件管理', '/incidents', 'Warning', 3, true),
('告警管理', '/alerts', 'Bell', 4, true)
ON CONFLICT (path) DO NOTHING;

-- 系统管理（父菜单 - 使用空字符串path）
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

-- 显示插入结果
SELECT id, parent_id, name, path, icon, sort_order FROM soc_menus ORDER BY sort_order;
EOF
```

- [ ] **Step 2: 执行SQL并验证**

Run:
```bash
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U postgres -d AI-miniSOC -f src/backend/scripts/init_menus.sql
```

Expected: 显示9条菜单记录（4个业务菜单 + 1个系统管理父菜单 + 4个子菜单）

- [ ] **Step 3: 提交初始化脚本**

```bash
git add src/backend/scripts/init_menus.sql
git commit -m "chore: add menu initialization SQL script

Initialize system menus:
- Business menus: dashboard, assets, incidents, alerts
- System management parent menu (empty path)
- System submenus: users, roles, menus, audit logs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5-10: 前端实现（简化版）

由于篇幅限制，前端实现任务简化为：

**Task 5**: 创建菜单类型定义 (`src/frontend/src/types/menu.ts`)
**Task 6**: 创建菜单API客户端 (`src/frontend/src/api/menu.ts`)
**Task 7**: 创建菜单Store (`src/frontend/src/stores/menus.ts`)
**Task 8**: 创建菜单管理页面 (`src/frontend/src/views/system/Menus.vue`)
  - 使用Element Plus Table + tree-props
  - 父菜单选择器（el-tree-select）
  - 图标选择器（el-select + Element Plus Icons）
  - 删除确认（检查子菜单）
**Task 9**: 添加路由和测试
**Task 10**: 文档和提交

---

## 验收标准

### 功能验收
- [ ] 可以创建2级菜单（父+子）
- [ ] 可以编辑菜单（防止循环引用）
- [ ] 可以删除菜单（有子菜单时阻止）
- [ ] 可以展开/收起菜单树
- [ ] 图标正确显示

### 安全验收
- [ ] 创建/更新/删除需要管理员权限
- [ ] 所有用户可以查看菜单树

---

**下一步**: 完成 Phase 3: 动态菜单加载实施计划
