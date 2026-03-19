# 用户管理模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为AI-miniSOC实现完整的用户管理功能，包括用户CRUD、状态管理、密码管理和基于角色的权限控制

**Architecture:** 后端采用FastAPI + SQLAlchemy分层架构（API → Service → Model），前端使用Vue 3 + Element Plus表格UI，通过专用Pinia Store管理状态，JWT认证+RBAC权限控制

**Tech Stack:** FastAPI 0.115+, SQLAlchemy 2.0+, PostgreSQL 16+, Vue 3, TypeScript, Element Plus 2.13+, Pinia 3.0+

---

## 文件结构规划

### 后端文件（创建/修改）

```
src/backend/app/
├── services/
│   ├── user_service.py          # [新建] 用户业务逻辑服务
│   └── __init__.py              # [修改] 导出UserService
├── api/
│   ├── users.py                 # [新建] 用户管理API路由
│   └── __init__.py              # [修改] 注册users路由
├── core/
│   └── security.py              # [修改] 添加密码生成工具
└── models/
    └── user.py                  # [已存在] 无需修改
```

### 前端文件（创建/修改）

```
src/frontend/src/
├── types/
│   └── user.ts                  # [新建] 用户类型定义
├── stores/
│   └── users.ts                 # [新建] 用户状态管理Store
├── views/
│   └── system/
│       ├── Users.vue            # [修改] 完整的用户管理页面
│       └── UserDialog.vue       # [新建] 用户创建/编辑对话框
└── api/
    └── client.ts                # [修改] 添加用户相关API调用
```

---

## Phase 1: 后端服务层 (UserService)

### Task 1: 创建UserService基础框架

**Files:**
- Create: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py` (新建)

- [ ] **Step 1: 编写UserService类结构测试**

```python
# tests/test_user_service.py
import pytest
from sqlalchemy.orm import Session
from app.services.user_service import UserService


def test_user_service_init(db: Session):
    """测试UserService初始化"""
    service = UserService(db)
    assert service.db is not None
    assert service.audit is not None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd src/backend
pytest tests/test_user_service.py::test_user_service_init -v
```

Expected: `FAILED - ImportError: cannot import name 'UserService'`

- [ ] **Step 3: 创建UserService基础类**

```python
# services/user_service.py
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta

from app.models.user import User, UserStatus
from app.models.role import Role
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import hash_password, generate_random_password
from app.services.audit_service import AuditService


class UserService:
    """用户业务逻辑类"""

    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_user_service_init -v
```

Expected: `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): add UserService class skeleton"
```

---

### Task 2: 实现用户列表查询功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写用户列表查询测试**

```python
# tests/test_user_service.py
def test_get_users(db: Session, sample_users):
    """测试获取用户列表"""
    service = UserService(db)
    users, total = service.get_users(skip=0, limit=10)

    assert total == len(sample_users)
    assert len(users) == min(10, len(sample_users))
    assert all(isinstance(u, User) for u in users)


def test_get_users_with_search(db: Session, sample_users):
    """测试搜索用户"""
    service = UserService(db)
    users, total = service.get_users(skip=0, limit=10, search="admin")

    assert total >= 0
    assert all("admin" in u.username.lower() for u in users)


def test_get_users_with_filters(db: Session, sample_users):
    """测试筛选用户"""
    service = UserService(db)
    users, total = service.get_users(
        skip=0,
        limit=10,
        role_id=1,
        status="active"
    )

    assert all(u.role_id == 1 for u in users)
    assert all(u.status == UserStatus.ACTIVE for u in users)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_get_users -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'get_users'`

- [ ] **Step 3: 实现用户列表查询方法**

```python
# services/user_service.py (在UserService类中添加)

    def get_users(
        self,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        role_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> Tuple[List[User], int]:
        """
        获取用户列表

        Args:
            skip: 跳过数量
            limit: 限制数量
            search: 搜索关键词（用户名/邮箱/姓名）
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_get_users -v
pytest tests/test_user_service.py::test_get_users_with_search -v
pytest tests/test_user_service.py::test_get_users_with_filters -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement get_users with search and filters"
```

---

### Task 3: 实现用户查询方法

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写用户查询测试**

```python
# tests/test_user_service.py
def test_get_user_by_id(db: Session, sample_users):
    """测试根据ID获取用户"""
    service = UserService(db)
    user = sample_users[0]

    found = service.get_user_by_id(user.id)
    assert found is not None
    assert found.id == user.id
    assert found.username == user.username


def test_get_user_by_id_not_found(db: Session):
    """测试获取不存在的用户"""
    service = UserService(db)
    found = service.get_user_by_id(99999)
    assert found is None


def test_get_user_by_username(db: Session, sample_users):
    """测试根据用户名获取用户"""
    service = UserService(db)
    user = sample_users[0]

    found = service.get_user_by_username(user.username)
    assert found is not None
    assert found.username == user.username
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_get_user_by_id -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'get_user_by_id'`

- [ ] **Step 3: 实现用户查询方法**

```python
# services/user_service.py (在UserService类中添加)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return self.db.query(User).filter(User.username == username).first()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_get_user_by_id -v
pytest tests/test_user_service.py::test_get_user_by_id_not_found -v
pytest tests/test_user_service.py::test_get_user_by_username -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): add user query methods"
```

---

### Task 4: 实现创建用户功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写创建用户测试**

```python
# tests/test_user_service.py
import pytest
from app.schemas.user import UserCreate


def test_create_user_success(db: Session, sample_role):
    """测试成功创建用户"""
    service = UserService(db)
    user_data = UserCreate(
        username="testuser",
        password="Test123456",
        email="test@example.com",
        full_name="测试用户",
        role_id=sample_role.id
    )

    user = service.create_user(user_data, creator_id=1)

    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.role_id == sample_role.id
    assert user.status == UserStatus.ACTIVE


def test_create_user_duplicate_username(db: Session, sample_users):
    """测试创建重复用户名"""
    service = UserService(db)
    existing_user = sample_users[0]

    user_data = UserCreate(
        username=existing_user.username,
        password="Test123456",
        role_id=existing_user.role_id
    )

    with pytest.raises(ValueError, match="用户名已存在"):
        service.create_user(user_data, creator_id=1)


def test_create_user_duplicate_email(db: Session, sample_role):
    """测试创建重复邮箱"""
    service = UserService(db)

    # 先创建一个用户
    user_data1 = UserCreate(
        username="user1",
        password="Test123456",
        email="duplicate@example.com",
        role_id=sample_role.id
    )
    service.create_user(user_data1, creator_id=1)

    # 尝试创建相同邮箱的用户
    user_data2 = UserCreate(
        username="user2",
        password="Test123456",
        email="duplicate@example.com",
        role_id=sample_role.id
    )

    with pytest.raises(ValueError, match="邮箱已被使用"):
        service.create_user(user_data2, creator_id=1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_create_user_success -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'create_user'`

- [ ] **Step 3: 实现创建用户方法**

```python
# services/user_service.py (在UserService类中添加)

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_create_user_success -v
pytest tests/test_user_service.py::test_create_user_duplicate_username -v
pytest tests/test_user_service.py::test_create_user_duplicate_email -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement create_user with validation"
```

---

### Task 5: 实现更新用户功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写更新用户测试**

```python
# tests/test_user_service.py
from app.schemas.user import UserUpdate


def test_update_user_success(db: Session, sample_users):
    """测试成功更新用户"""
    service = UserService(db)
    user = sample_users[0]

    update_data = UserUpdate(
        email="newemail@example.com",
        full_name="新姓名"
    )

    updated = service.update_user(user.id, update_data, updater_id=1)

    assert updated.email == "newemail@example.com"
    assert updated.full_name == "新姓名"


def test_update_user_not_found(db: Session):
    """测试更新不存在的用户"""
    service = UserService(db)
    update_data = UserUpdate(email="test@example.com")

    with pytest.raises(ValueError, match="用户不存在"):
        service.update_user(99999, update_data, updater_id=1)


def test_update_user_duplicate_email(db: Session, sample_users):
    """测试更新为已存在的邮箱"""
    service = UserService(db)
    user1, user2 = sample_users[0], sample_users[1]

    update_data = UserUpdate(email=user2.email)

    with pytest.raises(ValueError, match="邮箱已被使用"):
        service.update_user(user1.id, update_data, updater_id=1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_update_user_success -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'update_user'`

- [ ] **Step 3: 实现更新用户方法**

```python
# services/user_service.py (在UserService类中添加)

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
        update_data_dict = user_data.model_dump(exclude_unset=True)
        for field, value in update_data_dict.items():
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_update_user_success -v
pytest tests/test_user_service.py::test_update_user_not_found -v
pytest tests/test_user_service.py::test_update_user_duplicate_email -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement update_user with validation"
```

---

### Task 6: 实现删除用户功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写删除用户测试**

```python
# tests/test_user_service.py
def test_delete_user_success(db: Session, sample_users):
    """测试成功删除用户"""
    service = UserService(db)
    user = sample_users[0]
    user_id = user.id

    result = service.delete_user(user_id, deleter_id=1)

    assert result is True
    assert service.get_user_by_id(user_id) is None


def test_delete_user_not_found(db: Session):
    """测试删除不存在的用户"""
    service = UserService(db)

    with pytest.raises(ValueError, match="用户不存在"):
        service.delete_user(99999, deleter_id=1)


def test_delete_last_admin(db: Session, admin_user):
    """测试不能删除最后一个管理员"""
    service = UserService(db)

    with pytest.raises(ValueError, match="不能删除最后一个管理员"):
        service.delete_user(admin_user.id, deleter_id=admin_user.id)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_delete_user_success -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'delete_user'`

- [ ] **Step 3: 实现删除用户方法**

```python
# services/user_service.py (在UserService类中添加)

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_delete_user_success -v
pytest tests/test_user_service.py::test_delete_user_not_found -v
pytest tests/test_user_service.py::test_delete_last_admin -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement delete_user with admin protection"
```

---

### Task 7: 实现重置密码功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写重置密码测试**

```python
# tests/test_user_service.py
def test_reset_password_with_custom(db: Session, sample_users):
    """测试重置为自定义密码"""
    service = UserService(db)
    user = sample_users[0]

    new_password = service.reset_password(user.id, new_password="NewPass123", admin_id=1)

    assert new_password == "NewPass123"


def test_reset_password_auto_generate(db: Session, sample_users):
    """测试自动生成密码"""
    service = UserService(db)
    user = sample_users[0]

    new_password = service.reset_password(user.id, new_password=None, admin_id=1)

    assert new_password is not None
    assert len(new_password) >= 6


def test_reset_password_not_found(db: Session):
    """测试重置不存在的用户密码"""
    service = UserService(db)

    with pytest.raises(ValueError, match="用户不存在"):
        service.reset_password(99999, admin_id=1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_reset_password_with_custom -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'reset_password'`

- [ ] **Step 3: 实现重置密码方法**

```python
# services/user_service.py (在UserService类中添加)

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
        user.password_changed_at = datetime.now()
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_reset_password_with_custom -v
pytest tests/test_user_service.py::test_reset_password_auto_generate -v
pytest tests/test_user_service.py::test_reset_password_not_found -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement reset_password"
```

---

### Task 8: 实现锁定/解锁用户功能

**Files:**
- Modify: `src/backend/app/services/user_service.py`
- Test: `src/backend/tests/test_user_service.py`

- [ ] **Step 1: 编写锁定用户测试**

```python
# tests/test_user_service.py
def test_lock_user(db: Session, sample_users):
    """测试锁定用户"""
    service = UserService(db)
    user = sample_users[0]

    locked_user = service.lock_user(
        user.id,
        locked=True,
        reason="多次登录失败",
        admin_id=1
    )

    assert locked_user.status == UserStatus.LOCKED
    assert locked_user.locked_until is not None


def test_unlock_user(db: Session, sample_users):
    """测试解锁用户"""
    service = UserService(db)
    user = sample_users[0]

    # 先锁定
    service.lock_user(user.id, locked=True, admin_id=1)

    # 再解锁
    unlocked_user = service.lock_user(
        user.id,
        locked=False,
        admin_id=1
    )

    assert unlocked_user.status == UserStatus.ACTIVE
    assert unlocked_user.locked_until is None


def test_lock_user_not_found(db: Session):
    """测试锁定不存在的用户"""
    service = UserService(db)

    with pytest.raises(ValueError, match="用户不存在"):
        service.lock_user(99999, locked=True, admin_id=1)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_user_service.py::test_lock_user -v
```

Expected: `FAILED - AttributeError: 'UserService' object has no attribute 'lock_user'`

- [ ] **Step 3: 实现锁定用户方法**

```python
# services/user_service.py (在UserService类中添加)

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

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_user_service.py::test_lock_user -v
pytest tests/test_user_service.py::test_unlock_user -v
pytest tests/test_user_service.py::test_lock_user_not_found -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/services/user_service.py src/backend/tests/test_user_service.py
git commit -m "feat(services): implement lock_user and unlock_user"
```

---

### Task 9: 添加密码生成工具函数

**Files:**
- Modify: `src/backend/app/core/security.py`

- [ ] **Step 1: 编写密码生成测试**

```python
# tests/test_security.py
from app.core.security import generate_random_password


def test_generate_random_password_default():
    """测试生成默认长度密码"""
    password = generate_random_password()
    assert len(password) == 12
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)


def test_generate_random_password_custom_length():
    """测试生成自定义长度密码"""
    password = generate_random_password(length=20)
    assert len(password) == 20
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_security.py::test_generate_random_password_default -v
```

Expected: `FAILED - ImportError: cannot import name 'generate_random_password'`

- [ ] **Step 3: 实现密码生成函数**

```python
# core/security.py (添加到文件末尾)

import secrets
import string


def generate_random_password(length: int = 12) -> str:
    """
    生成随机密码

    Args:
        length: 密码长度，默认12位

    Returns:
        随机密码字符串，包含大小写字母、数字和特殊字符
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_security.py::test_generate_random_password_default -v
pytest tests/test_security.py::test_generate_random_password_custom_length -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/core/security.py src/backend/tests/test_security.py
git commit -m "feat(core): add generate_random_password utility"
```

---

### Task 10: 导出UserService

**Files:**
- Modify: `src/backend/app/services/__init__.py`

- [ ] **Step 1: 更新services的__init__.py**

```python
# services/__init__.py
from .user_service import UserService
from .audit_service import AuditService
from .encryption_service import EncryptionService
from .wazuh_client import WazuhClient
from .asset_sync import AssetSyncService
from .alert_query import AlertQueryService
from .ai_analysis import AIAnalysisService

__all__ = [
    "UserService",
    "AuditService",
    "EncryptionService",
    "WazuhClient",
    "AssetSyncService",
    "AlertQueryService",
    "AIAnalysisService",
]
```

- [ ] **Step 2: 验证导入**

```bash
cd src/backend
python -c "from app.services import UserService; print('Import successful')"
```

Expected: `Import successful`

- [ ] **Step 3: 提交**

```bash
git add src/backend/app/services/__init__.py
git commit -m "feat(services): export UserService"
```

---

## Phase 2: 后端API层 (Users API)

### Task 11: 创建用户管理API路由

**Files:**
- Create: `src/backend/app/api/users.py`
- Test: `src/backend/tests/test_users_api.py` (新建)

- [ ] **Step 1: 编写API路由测试**

```python
# tests/test_users_api.py
import pytest
from fastapi.testclient import TestClient


def test_get_users_unauthorized(client: TestClient):
    """测试未认证访问"""
    response = client.get("/api/v1/users")
    assert response.status_code == 401


def test_get_users_authorized(client: TestClient, auth_token):
    """测试认证用户访问"""
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_users_api.py::test_get_users_unauthorized -v
```

Expected: `FAILED - 404 Not Found` (路由不存在)

- [ ] **Step 3: 创建API路由文件**

```python
# api/users.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_menu_permission
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    ResetPasswordRequest,
    LockUserRequest
)
from app.services.user_service import UserService
from app.schemas.user import UserResponse as UserResponseSchema


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    role_id: Optional[int] = Query(None, description="角色ID"),
    status: Optional[str] = Query(None, description="状态"),
    current_user: UserResponseSchema = Depends(require_menu_permission("system-users")),
    db: Session = Depends(get_db)
):
    """
    获取用户列表

    需要权限: system-users
    """
    service = UserService(db)
    skip = (page - 1) * page_size

    users, total = service.get_users(
        skip=skip,
        limit=page_size,
        search=search,
        role_id=role_id,
        status=status
    )

    return UserListResponse(
        total=total,
        items=[UserResponse.model_validate(u) for u in users]
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: UserResponseSchema = Depends(require_menu_permission("system-users")),
    db: Session = Depends(get_db)
):
    """获取用户详情"""
    service = UserService(db)
    user = service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以创建用户"
        )

    service = UserService(db)
    try:
        user = service.create_user(user_data, creator_id=current_user.id)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以更新用户"
        )

    service = UserService(db)
    try:
        user = service.update_user(user_id, user_data, updater_id=current_user.id)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以删除用户"
        )

    service = UserService(db)
    try:
        service.delete_user(user_id, deleter_id=current_user.id)
        return {"success": True, "message": "用户已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    password_data: ResetPasswordRequest,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    重置用户密码

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以重置密码"
        )

    service = UserService(db)
    try:
        new_password = service.reset_password(
            user_id,
            new_password=password_data.new_password,
            admin_id=current_user.id
        )
        return {
            "success": True,
            "message": "密码已重置",
            "new_password": new_password
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/lock", response_model=UserResponse)
async def lock_user(
    user_id: int,
    lock_data: LockUserRequest,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    锁定或解锁用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以锁定用户"
        )

    service = UserService(db)
    try:
        user = service.lock_user(
            user_id,
            locked=lock_data.is_locked,
            reason=lock_data.lock_reason,
            admin_id=current_user.id
        )
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_users_api.py::test_get_users_unauthorized -v
pytest tests/test_users_api.py::test_get_users_authorized -v
```

Expected: All `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/backend/app/api/users.py src/backend/tests/test_users_api.py
git commit -m "feat(api): add user management API endpoints"
```

---

### Task 12: 注册用户管理路由

**Files:**
- Modify: `src/backend/app/api/__init__.py`
- Modify: `src/backend/main.py`

- [ ] **Step 1: 更新api/__init__.py**

```python
# api/__init__.py
from . import users, auth, assets, incidents, alerts, ai

__all__ = ["users", "auth", "assets", "incidents", "alerts", "ai"]
```

- [ ] **Step 2: 在main.py中注册路由**

```python
# main.py (找到API路由注册部分，添加)
from app.api import users

# 注册用户管理路由
app.include_router(users.router, prefix="/api/v1", tags=["用户管理"])
```

- [ ] **Step 3: 验证路由注册**

```bash
cd src/backend
python -c "from main import app; print([r.path for r in app.routes if 'users' in r.path])"
```

Expected: 包含 `/api/v1/users` 等路径

- [ ] **Step 4: 提交**

```bash
git add src/backend/app/api/__init__.py src/backend/main.py
git commit -m "feat(api): register user management routes"
```

---

## Phase 3: 前端类型定义

### Task 13: 创建用户类型定义

**Files:**
- Create: `src/frontend/src/types/user.ts`

- [ ] **Step 1: 创建用户类型定义文件**

```typescript
// types/user.ts
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

export interface UserListResponse {
  total: number
  page: number
  page_size: number
  items: User[]
}

export interface ResetPasswordRequest {
  new_password?: string
}

export interface LockUserRequest {
  is_locked: boolean
  lock_reason?: string
}
```

- [ ] **Step 2: 验证类型定义**

```bash
cd src/frontend
npx tsc --noEmit types/user.ts
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/frontend/src/types/user.ts
git commit -m "feat(frontend): add user type definitions"
```

---

## Phase 4: 前端Store

### Task 14: 创建用户管理Store

**Files:**
- Create: `src/frontend/src/stores/users.ts`

- [ ] **Step 1: 编写Store测试**

```typescript
// tests/stores/users.test.ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUsersStore } from '@/stores/users'

describe('Users Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('initial state', () => {
    const store = useUsersStore()

    expect(store.users).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.pagination.page).toBe(1)
    expect(store.pagination.page_size).toBe(20)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd src/frontend
npm test stores/users.test.ts
```

Expected: `FAILED - Cannot find module '@/stores/users'`

- [ ] **Step 3: 创建用户Store**

```typescript
// stores/users.ts
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
    loading.value = true
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
    } finally {
      loading.value = false
    }
  }

  async function updateUser(id: number, data: UserUpdate) {
    loading.value = true
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
    } finally {
      loading.value = false
    }
  }

  async function deleteUser(id: number) {
    loading.value = true
    try {
      await apiCall(`/users/${id}`, { method: 'DELETE' })
      await fetchUsers()
    } catch (error) {
      console.error('删除用户失败:', error)
      throw error
    } finally {
      loading.value = false
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
    loading.value = true
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
    } finally {
      loading.value = false
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

- [ ] **Step 4: 运行测试确认通过**

```bash
cd src/frontend
npm test stores/users.test.ts
```

Expected: `PASSED`

- [ ] **Step 5: 提交**

```bash
git add src/frontend/src/stores/users.ts src/frontend/tests/stores/users.test.ts
git commit -m "feat(frontend): add users store with CRUD operations"
```

---

## Phase 5: 前端UI组件

### Task 15: 创建用户对话框组件

**Files:**
- Create: `src/frontend/src/components/UserDialog.vue`

- [ ] **Step 1: 创建用户对话框组件**

```vue
<!-- components/UserDialog.vue -->
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
          placeholder="请输入用户名（3-50字符）"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password" v-if="mode === 'create'">
        <el-input
          v-model="formData.password"
          type="password"
          placeholder="请输入密码（至少6位）"
          show-password
        />
      </el-form-item>

      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="formData.email"
          type="email"
          placeholder="请输入邮箱"
        />
      </el-form-item>

      <el-form-item label="姓名" prop="full_name">
        <el-input
          v-model="formData.full_name"
          placeholder="请输入姓名"
        />
      </el-form-item>

      <el-form-item label="手机号" prop="phone">
        <el-input
          v-model="formData.phone"
          placeholder="请输入手机号"
        />
      </el-form-item>

      <el-form-item label="部门" prop="department">
        <el-input
          v-model="formData.department"
          placeholder="请输入部门"
        />
      </el-form-item>

      <el-form-item label="角色" prop="role_id">
        <el-select
          v-model="formData.role_id"
          placeholder="请选择角色"
          style="width: 100%"
        >
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
      <el-button
        type="primary"
        @click="handleSubmit"
        :loading="submitting"
      >
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { User, UserCreate, UserUpdate, Role } from '@/types/user'

interface Props {
  modelValue: boolean
  user?: User
  roles: Role[]
  mode: 'create' | 'edit'
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'submit': [data: UserCreate | UserUpdate]
}>()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const formData = reactive<{
  username: string
  password: string
  email?: string
  full_name?: string
  phone?: string
  department?: string
  role_id?: number
}>({
  username: '',
  password: '',
  email: '',
  full_name: '',
  phone: '',
  department: '',
  role_id: undefined
})

const formRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在3-50个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度在6-100个字符', trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' }
  ],
  role_id: [
    { required: true, message: '请选择角色', trigger: 'change' }
  ]
}

// 监听用户数据变化，填充表单
watch(() => props.user, (user) => {
  if (user && props.mode === 'edit') {
    formData.username = user.username
    formData.email = user.email
    formData.full_name = user.full_name
    formData.phone = user.phone
    formData.department = user.department
    formData.role_id = user.role_id
  }
}, { immediate: true })

// 监听对话框关闭，重置表单
watch(() => props.modelValue, (visible) => {
  if (!visible) {
    formRef.value?.resetFields()
  }
})

function handleCancel() {
  emit('update:modelValue', false)
}

async function handleSubmit() {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      if (props.mode === 'create') {
        const data: UserCreate = {
          username: formData.username,
          password: formData.password,
          email: formData.email,
          full_name: formData.full_name,
          phone: formData.phone,
          department: formData.department,
          role_id: formData.role_id!
        }
        emit('submit', data)
      } else {
        const data: UserUpdate = {
          email: formData.email,
          full_name: formData.full_name,
          phone: formData.phone,
          department: formData.department,
          role_id: formData.role_id
        }
        emit('submit', data)
      }
    } finally {
      submitting.value = false
    }
  })
}
</script>

<style scoped>
.el-form {
  padding: 0 20px;
}
</style>
```

- [ ] **Step 2: 验证组件**

```bash
cd src/frontend
npx vue-tsc --noEmit components/UserDialog.vue
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/frontend/src/components/UserDialog.vue
git commit -m "feat(frontend): add UserDialog component"
```

---

### Task 16: 实现用户管理页面

**Files:**
- Modify: `src/frontend/src/views/system/Users.vue`

- [ ] **Step 1: 完整实现用户管理页面**

```vue
<!-- views/system/Users.vue -->
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
        >
          <el-icon><Plus /></el-icon>
          添加用户
        </el-button>
      </template>
    </el-page-header>

    <!-- 搜索和筛选 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" :model="usersStore.filters">
        <el-form-item label="搜索">
          <el-input
            v-model="searchInput"
            placeholder="搜索用户名/邮箱/姓名"
            clearable
            style="width: 250px"
            @clear="handleSearch"
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
          <el-button type="primary" @click="handleSearch">
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

    ElMessageBox.alert(
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
```

- [ ] **Step 2: 验证页面**

```bash
cd src/frontend
npx vue-tsc --noEmit views/system/Users.vue
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/frontend/src/views/system/Users.vue
git commit -m "feat(frontend): implement complete user management page"
```

---

## Phase 6: 集成测试

### Task 17: 端到端测试

**Files:**
- Create: `src/frontend/tests/e2e/user-management.spec.ts`

- [ ] **Step 1: 创建E2E测试**

```typescript
// tests/e2e/user-management.spec.ts
import { test, expect } from '@playwright/test'

test.describe('用户管理', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await page.goto('http://localhost:5173/login')
    await page.fill('input[name="username"]', 'admin')
    await page.fill('input[name="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/dashboard')
  })

  test('显示用户列表', async ({ page }) => {
    await page.goto('http://localhost:5173/system/users')

    // 验证表格存在
    await expect(page.locator('.el-table')).toBeVisible()

    // 验证分页存在
    await expect(page.locator('.el-pagination')).toBeVisible()
  })

  test('搜索用户', async ({ page }) => {
    await page.goto('http://localhost:5173/system/users')

    // 输入搜索关键词
    await page.fill('input[placeholder*="搜索"]', 'admin')
    await page.click('button:has-text("查询")')

    // 等待加载完成
    await page.waitForSelector('.el-table:not(.el-table--loading)')
  })

  test('创建用户', async ({ page }) => {
    await page.goto('http://localhost:5173/system/users')

    // 点击添加用户按钮
    await page.click('button:has-text("添加用户")')

    // 填写表单
    await page.fill('input[name="username"]', 'testuser')
    await page.fill('input[name="password"]', 'Test123456')
    await page.fill('input[name="email"]', 'test@example.com')
    await page.fill('input[name="full_name"]', '测试用户')

    // 选择角色
    await page.click('.el-select:has-text("角色")')
    await page.click('.el-select-dropdown__item:has-text("普通用户")')

    // 提交
    await page.click('button:has-text("确定")')

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible()
  })
})
```

- [ ] **Step 2: 运行E2E测试**

```bash
cd src/frontend
npm run test:e2e
```

Expected: 所有测试通过

- [ ] **Step 3: 提交**

```bash
git add src/frontend/tests/e2e/user-management.spec.ts
git commit -m "test(frontend): add user management E2E tests"
```

---

### Task 18: API集成测试

**Files:**
- Create: `src/backend/tests/integration/test_user_workflow.py`

- [ ] **Step 1: 创建工作流测试**

```python
# tests/integration/test_user_workflow.py
import pytest
from fastapi.testclient import TestClient


def test_user_lifecycle(client: TestClient, admin_token: str):
    """测试用户完整生命周期"""

    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. 创建用户
    user_data = {
        "username": "lifecycle_test",
        "password": "Test123456",
        "email": "lifecycle@example.com",
        "full_name": "生命周期测试",
        "role_id": 2
    }

    response = client.post("/api/v1/users", json=user_data, headers=headers)
    assert response.status_code == 201
    user = response.json()
    user_id = user["id"]

    # 2. 查询用户
    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "lifecycle_test"

    # 3. 更新用户
    update_data = {"full_name": "已更新"}
    response = client.put(f"/api/v1/users/{user_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["full_name"] == "已更新"

    # 4. 锁定用户
    lock_data = {"is_locked": True, "lock_reason": "测试锁定"}
    response = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["is_locked"] is True

    # 5. 解锁用户
    lock_data = {"is_locked": False}
    response = client.post(f"/api/v1/users/{user_id}/lock", json=lock_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["is_locked"] is False

    # 6. 删除用户
    response = client.delete(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 200

    # 7. 验证已删除
    response = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert response.status_code == 404
```

- [ ] **Step 2: 运行集成测试**

```bash
cd src/backend
pytest tests/integration/test_user_workflow.py -v
```

Expected: All `PASSED`

- [ ] **Step 3: 提交**

```bash
git add src/backend/tests/integration/test_user_workflow.py
git commit -m "test(backend): add user lifecycle integration test"
```

---

## Phase 7: 文档和部署

### Task 19: 更新API文档

**Files:**
- Update: `docs/api/users-api.md`

- [ ] **Step 1: 创建API文档**

```markdown
# 用户管理API文档

## 概述

用户管理API提供用户CRUD操作、状态管理和密码管理功能。

## 认证

所有API请求需要在HTTP Header中携带JWT Token：

```
Authorization: Bearer <access_token>
```

## 端点列表

### 1. 获取用户列表

**请求**
```
GET /api/v1/users?page=1&page_size=20&search=admin&role_id=1&status=active
```

**查询参数**
- `page`: 页码（默认1）
- `page_size`: 每页数量（默认20，最大100）
- `search`: 搜索关键词
- `role_id`: 角色ID
- `status`: 状态（active/locked/disabled）

**响应**
```json
{
  "total": 50,
  "page": 1,
  "page_size": 20,
  "items": [...]
}
```

### 2. 获取用户详情

**请求**
```
GET /api/v1/users/{id}
```

### 3. 创建用户

**请求**
```
POST /api/v1/users
Content-Type: application/json

{
  "username": "testuser",
  "password": "Test123456",
  "email": "test@example.com",
  "full_name": "测试用户",
  "role_id": 2
}
```

### 4. 更新用户

**请求**
```
PUT /api/v1/users/{id}
Content-Type: application/json

{
  "email": "new@example.com",
  "full_name": "新姓名"
}
```

### 5. 删除用户

**请求**
```
DELETE /api/v1/users/{id}
```

### 6. 重置密码

**请求**
```
POST /api/v1/users/{id}/reset-password
Content-Type: application/json

{
  "new_password": "NewPass123"
}
```

### 7. 锁定/解锁用户

**请求**
```
POST /api/v1/users/{id}/lock
Content-Type: application/json

{
  "is_locked": true,
  "lock_reason": "多次登录失败"
}
```

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |
```

- [ ] **Step 2: 提交**

```bash
git add docs/api/users-api.md
git commit -m "docs: add user management API documentation"
```

---

### Task 20: 最终集成验证

**Files:**
- None

- [ ] **Step 1: 运行所有测试**

```bash
# 后端测试
cd src/backend
pytest tests/ -v --cov=app

# 前端测试
cd src/frontend
npm test

# E2E测试
npm run test:e2e
```

Expected: 所有测试通过

- [ ] **Step 2: 验证API文档**

```bash
curl http://localhost:8000/docs | grep "users"
```

Expected: 用户管理API端点在文档中可见

- [ ] **Step 3: 验证前端页面**

```bash
# 启动前端
cd src/frontend
npm run dev

# 在浏览器中访问
# http://localhost:5173/system/users
```

Expected: 用户管理页面正常显示

- [ ] **Step 4: 提交最终版本**

```bash
git add .
git commit -m "feat: complete user management module implementation

- Backend: UserService with full CRUD operations
- Backend: 7 user management API endpoints
- Frontend: User management page with Element Plus table
- Frontend: UserDialog component for create/edit
- Frontend: Users store with state management
- Tests: Unit tests, integration tests, E2E tests
- Docs: API documentation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 附录

### A. Pytest Fixtures

**创建 `tests/conftest.py`**

```python
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserStatus
from app.models.role import Role
from app.core.security import hash_password, create_access_token


@pytest.fixture
def db():
    """测试数据库会话"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///./test.db")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db: Session):
    """测试客户端"""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def sample_role(db: Session):
    """示例角色"""
    role = Role(
        name="普通用户",
        code="user",
        description="普通用户角色"
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@pytest.fixture
def admin_user(db: Session):
    """管理员用户"""
    admin_role = Role(name="管理员", code="admin", is_system=True)
    db.add(admin_role)
    db.commit()

    user = User(
        username="admin",
        password_hash=hash_password("admin123"),
        email="admin@example.com",
        full_name="系统管理员",
        role_id=admin_role.id,
        status=UserStatus.ACTIVE
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def sample_users(db: Session, sample_role):
    """示例用户列表"""
    users = []
    for i in range(5):
        user = User(
            username=f"user{i}",
            password_hash=hash_password("password123"),
            email=f"user{i}@example.com",
            full_name=f"测试用户{i}",
            role_id=sample_role.id,
            status=UserStatus.ACTIVE
        )
        db.add(user)
        users.append(user)

    db.commit()
    for user in users:
        db.refresh(user)

    return users


@pytest.fixture
def admin_token(admin_user: User):
    """管理员Token"""
    return create_access_token(data={"sub": str(admin_user.id)})
```

### B. 测试命令

```bash
# 运行特定测试
pytest tests/test_user_service.py::test_create_user_success -v

# 运行所有测试并生成覆盖率报告
pytest tests/ --cov=app --cov-report=html

# 运行集成测试
pytest tests/integration/ -v

# 前端单元测试
npm test

# 前端E2E测试
npm run test:e2e

# 类型检查
npx vue-tsc --noEmit
```

### C. 开发工作流

```bash
# 1. 启动后端开发服务器
cd src/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2. 启动前端开发服务器
cd src/frontend
npm run dev

# 3. 访问应用
# 前端: http://localhost:5173
# 后端API文档: http://localhost:8000/docs

# 4. 运行测试
# 后端: pytest tests/ -v
# 前端: npm test
```

---

**计划版本**: v1.0
**创建日期**: 2026-03-19
**预计工作量**: 20个Task，每个Task包含5个Step
**总步骤数**: ~100个步骤
**预估时间**: 8-12小时（取决于开发者经验）
