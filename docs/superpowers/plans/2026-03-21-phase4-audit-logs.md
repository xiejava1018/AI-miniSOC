# Phase 4: 审计日志实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现完整的审计日志系统，记录所有关键操作并支持查询导出

**Architecture:**
- 后端：审计装饰器自动记录操作 + 3个查询API端点
- 前端：审计日志查询页面，支持多维度筛选和导出
- 记录范围：认证、用户/角色/菜单管理、数据操作、敏感操作

**Dependencies:**
- 无依赖，可独立开发或最后集成

---

## Task 1: 实现审计装饰器

**Files:**
- Create: `src/backend/app/core/audit.py`

- [ ] **Step 1: 创建审计装饰器**

```python
# src/backend/app/core/audit.py
from functools import wraps
from sqlalchemy.orm import Session
from fastapi import Request
import json
import uuid

from app.models.audit_log import AuditLog
from app.models.user import User


def audit_log(action: str, resource_type: str):
    """
    审计日志装饰器

    Usage:
        @audit_log("CREATE", "User")
        async def create_user(...):
            ...

    注意: 被装饰函数需要接收 request: Request 参数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db: Session = kwargs.get('db')
            current_user = kwargs.get('current_user')
            request: Request = kwargs.get('request')

            # 提取客户端信息
            ip_address = request.client.host if request and request.client else None
            user_agent = request.headers.get('user-agent') if request else None

            # 生成请求ID
            request_id = str(uuid.uuid4())

            # 对于更新操作，捕获变更前数据
            old_values = None
            if action in ['UPDATE', 'DELETE'] and 'id' in kwargs:
                resource_id = kwargs.get('id')
                if resource_id and resource_type == 'User':
                    old_obj = db.query(User).filter(User.id == resource_id).first()
                    if old_obj:
                        old_values = {
                            'username': old_obj.username,
                            'email': old_obj.email,
                            'status': old_obj.status,
                            'role_id': old_obj.role_id
                        }

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

                # 对于更新操作，捕获变更后数据
                if action == 'UPDATE' and result:
                    new_values = {
                        'username': result.username,
                        'email': result.email,
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

---

## Task 2: 实现审计日志API

**Files:**
- Create: `src/backend/app/api/audit.py`
- Modify: `src/backend/main.py`

- [ ] **Step 1: 创建audit API**

```python
# src/backend/app/api/audit.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
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

    # 筛选
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


@router.get("/export")
async def export_audit_logs(
    format: str = Query("csv"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """导出审计日志（TODO: Phase 2实现）"""
    return {"message": "导出功能待实现"}
```

---

## Task 3: 应用审计装饰器

**Files:**
- Modify: `src/backend/app/api/users.py`
- Modify: `src/backend/app/api/roles.py`

- [ ] **Step 1: 在users.py应用装饰器**

在每个关键函数添加 `@audit_log` 装饰器：
```python
from app.core.audit import audit_log
from app.constants.audit_actions import *

@router.post("")
@audit_log(AUDIT_USER_CREATE, "User")
async def create_user(...):
    ...

@router.put("/{user_id}")
@audit_log(AUDIT_USER_UPDATE, "User")
async def update_user(...):
    ...
```

---

## Task 4: 前端审计日志页面

**Files:**
- Create: `src/frontend/src/views/system/AuditLogs.vue`
- Create: `src/frontend/src/stores/audit.ts`

- [ ] **Step 1: 创建审计日志页面**

（简化版，包含筛选器、表格、详情对话框）

---

## 验收标准

- [ ] 所有关键操作被记录
- [ ] 可以按用户/操作/时间筛选
- [ ] 可以查看变更前后数据
- [ ] 失败操作也被记录

---

**所有Phase完成后的总结**:
- Phase 1-4完成后，系统管理核心功能全部实现
- 可以开始集成测试和文档更新
- 准备生产环境部署
