# api/users.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin, require_menu_permission, require_role
from app.core.audit_decorator import log_audit
from app.core.security import verify_password, get_password_hash
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    ResetPasswordRequest,
    LockUserRequest
)
from app.schemas.mcp_key import (
    MCPKeyCreate,
    MCPKeyExtend,
    MCPKeyResponse,
    MCPKeyCreatedResponse,
)
from app.schemas.user_profile import ProfileResponse, ChangePasswordRequest
from app.services.user_service import UserService
from app.services.mcp_key_service import MCPKeyService
from app.services.audit_log_service import AuditLogService
from app.models.user import User, UserStatus
from app.models.mcp_key import SOCMCPKey


router = APIRouter(tags=["用户管理"])


def _build_user_response(user) -> UserResponse:
    """构建用户响应，处理关联数据"""
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "nick_name": user.nick_name,
        "phone": user.phone,
        "avatar": user.avatar,
        "gender": user.gender,
        "department_id": user.department_id,
        "department_name": user.department.name if user.department else None,
        "role_id": user.role_id,
        "role_name": user.role.name if user.role else None,
        "is_admin": user.is_admin,
        "status": user.status,
        "last_login": user.last_login,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    return UserResponse.model_validate(data)


@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    role_id: Optional[int] = Query(None, description="角色ID"),
    status: Optional[int] = Query(None, ge=1, le=2, description="状态: 1=启用, 2=禁用"),
    current_user: User = Depends(require_menu_permission("user")),
    db: Session = Depends(get_db)
):
    """
    获取用户列表

    需要权限: system-user
    """
    service = UserService(db)
    skip = (page - 1) * page_size

    # 状态转换：前端数字 -> 后端字符串
    status_str = None
    if status is not None:
        status_map = {1: UserStatus.ACTIVE, 2: UserStatus.DISABLED}
        status_str = status_map.get(status, UserStatus.ACTIVE)

    users, total = service.get_users(
        skip=skip,
        limit=page_size,
        search=search,
        role_id=role_id,
        status=status_str
    )

    return UserListResponse(
        total=total,
        items=[_build_user_response(u) for u in users]
    )


# ============================================================================
# 个人中心自助端点 /users/me/*（设计文档 §4.1 / §6）
#
# ⚠ 路由注册顺序约束：/me/* 必须注册在 /{user_id} 之前，
#   否则 FastAPI 按声明顺序匹配会把 "me" 当成 user_id 路径参数（int 解析失败→422）。
#   本块整体位于 get_user(/{user_id}) 之前，新增 /{user_id} 类路由不得插到本块前面。
# ============================================================================

# PUT /users/me 可编辑字段白名单（越权字段→422 并指明字段名，设计 §4.1）
PROFILE_EDITABLE_FIELDS = {"nick_name", "phone", "email", "avatar", "gender"}

# 不可自助管理 MCP Key 的角色（设计 §7：只读/审计角色需 admin 代发；含历史 readonly）
_MCP_KEY_SELF_FORBIDDEN_ROLES = {"viewer", "auditor", "readonly"}

# 改密失败计数（in-memory；与登录失败计数独立，key=username:ip，
# 参考 auth.py 同模式：多 worker 不共享，单进程可接受）
_pwd_change_attempts: dict[str, tuple[int, datetime]] = {}
_PWD_CHANGE_FAIL_LIMIT = 5       # 连续错 5 次
_PWD_CHANGE_LOCK_MINUTES = 15    # 锁 15 分钟


def _ensure_mcp_key_write_allowed(current_user: User) -> None:
    """viewer/auditor/readonly 不可自助申请/延期/注销 MCP Key（admin bypass，设计 §7）。"""
    if current_user.is_admin:
        return
    role_code = current_user.role.code if current_user.role else None
    if role_code in _MCP_KEY_SELF_FORBIDDEN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="审计/只读角色不可自助申请 MCP Key（如需接入请联系管理员代发）",
        )


def _build_profile_response(user: User) -> ProfileResponse:
    """构建 GET/PUT /users/me 响应（含角色编码与部门名，供个人中心展示）。"""
    return ProfileResponse.model_validate({
        "id": user.id,
        "username": user.username,
        "nick_name": user.nick_name,
        "email": user.email,
        "phone": user.phone,
        "avatar": user.avatar,
        "gender": user.gender,
        "role_code": user.role.code if user.role else None,
        "role_name": user.role.name if user.role else None,
        "department_id": user.department_id,
        "department_name": user.department.name if user.department else None,
        "status": user.status,
        "last_login": user.last_login,
        "created_at": user.created_at,
    })


def _build_key_response(key_obj, include_plaintext: str = None):
    """SOCMCPKey ORM → MCPKeyResponse；days_remaining 运行时实时计算（不落库）。"""
    days = None
    if key_obj.expires_at is not None:
        exp = key_obj.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        days = max(0, (exp - datetime.now(timezone.utc)).days)
    data = {
        "id": key_obj.id,
        "name": key_obj.name,
        "key_prefix": key_obj.key_prefix,
        "status": key_obj.status,
        "days_remaining": days,
        "expires_at": key_obj.expires_at,
        "last_used_at": key_obj.last_used_at,
        "created_at": key_obj.created_at,
    }
    if include_plaintext is not None:
        return MCPKeyCreatedResponse(**data, key=include_plaintext)
    return MCPKeyResponse.model_validate(data)


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """我的完整资料（个人中心 Tab1 数据源，与 /auth/me 并存，设计 §4.1 B2）"""
    return _build_profile_response(current_user)


@router.put("/me", response_model=ProfileResponse)
@log_audit(
    action="UPDATE",
    resource_type="user_profile",
    get_resource_id=lambda result, kwargs: kwargs.get("current_user").id,
    get_resource_name=lambda result, kwargs: kwargs.get("current_user").username,
    get_new_values=lambda result, kwargs: kwargs.get("payload"),
)
async def update_my_profile(
    request: Request,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    修改自己的可编辑资料。

    白名单: nick_name / phone / email / avatar / gender；
    传 username / role_id 等越权字段 → 422 + detail 指明字段名。
    """
    extra = set(payload) - PROFILE_EDITABLE_FIELDS
    if extra:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"字段不可修改（仅支持 {'/'.join(sorted(PROFILE_EDITABLE_FIELDS))}）：{', '.join(sorted(extra))}",
        )
    if "gender" in payload and payload["gender"] is not None and payload["gender"] not in (0, 1, 2):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="gender 取值须为 0(未知)/1(男)/2(女)")

    for field in PROFILE_EDITABLE_FIELDS:
        if field in payload:
            setattr(current_user, field, payload[field])
    db.commit()
    db.refresh(current_user)
    return _build_profile_response(current_user)


@router.post("/me/change-password")
async def change_my_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    修改自己密码。

    - 旧密码错 → 401（计入失败锁定，连续 5 次锁 15 分钟，第 5 次起 429）
    - 新密码 <6 位 → 422
    - 成功 → 200；审计 password.change.success / password.change.fail
    - 成功后不需要做 JWT 黑名单——前端负责引导重新登录（设计 §4.1）
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    audit_service = AuditLogService(db)
    lock_key = f"{current_user.username}:{client_ip or 'unknown'}"

    # 1) 失败锁定检查（窗口内达上限 → 429）
    now = datetime.utcnow()
    count, first_fail = _pwd_change_attempts.get(lock_key, (0, now))
    if count >= _PWD_CHANGE_FAIL_LIMIT and (now - first_fail) < timedelta(minutes=_PWD_CHANGE_LOCK_MINUTES):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"连续失败次数过多，请 {_PWD_CHANGE_LOCK_MINUTES} 分钟后再试",
        )

    # 2) 新密码强度（422，不计失败）
    if len(payload.new_password) < 6:
        audit_service.create_audit_log(
            user_id=current_user.id, username=current_user.username,
            action="password.change.fail", resource_type="user_profile",
            ip_address=client_ip, user_agent=user_agent,
            status="failure", error_message="新密码强度不足（<6 位）",
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="新密码至少 6 位")

    # 3) 旧密码验证（401，计入失败锁定）
    if not verify_password(payload.old_password, current_user.password_hash):
        count, first_fail = _pwd_change_attempts.get(lock_key, (0, datetime.utcnow()))
        if (datetime.utcnow() - first_fail) > timedelta(minutes=_PWD_CHANGE_LOCK_MINUTES):
            count, first_fail = 0, datetime.utcnow()
        count += 1
        _pwd_change_attempts[lock_key] = (count, first_fail)
        audit_service.create_audit_log(
            user_id=current_user.id, username=current_user.username,
            action="password.change.fail", resource_type="user_profile",
            ip_address=client_ip, user_agent=user_agent,
            status="failure", error_message=f"旧密码错误（第 {count} 次失败）",
        )
        if count >= _PWD_CHANGE_FAIL_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"连续失败 {_PWD_CHANGE_FAIL_LIMIT} 次，请 {_PWD_CHANGE_LOCK_MINUTES} 分钟后再试",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="当前密码错误")

    # 4) 成功：更新哈希 + 清计数 + 审计
    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    _pwd_change_attempts.pop(lock_key, None)
    audit_service.create_audit_log(
        user_id=current_user.id, username=current_user.username,
        action="password.change.success", resource_type="user_profile",
        ip_address=client_ip, user_agent=user_agent, status="success",
    )
    return {"success": True, "message": "密码已修改，请重新登录"}


@router.get("/me/mcp-keys", response_model=list[MCPKeyResponse])
async def list_my_mcp_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的 MCP Key 列表（任何角色可看自己的，永不返回明文）"""
    keys = MCPKeyService(db).list_keys(current_user.id)
    return [_build_key_response(k) for k in keys]


@router.post("/me/mcp-keys", response_model=MCPKeyCreatedResponse)
@log_audit(
    action="mcp_key.create",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: result.id,
    get_resource_name=lambda result, kwargs: result.name,
    # ⚠ 审计 detail 只记 key_prefix，明文永不落审计链（设计 §8）
    get_new_values=lambda result, kwargs: {"name": result.name, "key_prefix": result.key_prefix},
)
async def create_my_mcp_key(
    request: Request,
    payload: MCPKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    申请新 MCP Key（明文仅本次响应返回一次）。

    viewer/auditor/readonly → 403（需 admin 代发，设计 §7）。
    """
    _ensure_mcp_key_write_allowed(current_user)
    key_obj, plaintext = MCPKeyService(db).create_key(
        user_id=current_user.id, name=payload.name, validity_days=payload.validity_days,
    )
    return _build_key_response(key_obj, include_plaintext=plaintext)


@router.post("/me/mcp-keys/{key_id}/extend", response_model=MCPKeyResponse)
@log_audit(
    action="mcp_key.extend",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: kwargs.get("key_id"),
    get_resource_name=lambda result, kwargs: result.name,
    get_new_values=lambda result, kwargs: {"expires_at": str(result.expires_at)},
)
async def extend_my_mcp_key(
    request: Request,
    key_id: int,
    payload: MCPKeyExtend,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """延期自己的 Key（仅 active 可延期，409 由 service 抛出）"""
    _ensure_mcp_key_write_allowed(current_user)
    key_obj = MCPKeyService(db).extend_key(
        user_id=current_user.id, key_id=key_id, new_validity_days=payload.new_validity_days,
    )
    return _build_key_response(key_obj)


@router.delete("/me/mcp-keys/{key_id}", response_model=MCPKeyResponse)
@log_audit(
    action="mcp_key.revoke",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: kwargs.get("key_id"),
    get_resource_name=lambda result, kwargs: result.name,
)
async def revoke_my_mcp_key(
    request: Request,
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注销自己的 Key（幂等；同步清缓存即时生效）"""
    _ensure_mcp_key_write_allowed(current_user)
    key_obj = MCPKeyService(db).revoke_key(
        user_id=current_user.id, key_id=key_id, reason="user_revoked",
    )
    return _build_key_response(key_obj)


@router.delete("/me/mcp-keys/{key_id}/purge")
@log_audit(
    action="mcp_key.purge",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: kwargs.get("key_id"),
    get_resource_name=lambda result, kwargs: result.get("name"),
    get_old_values=lambda result, kwargs: result.get("snapshot"),
    get_new_values=lambda result, kwargs: {"deleted": True},
)
async def purge_my_mcp_key(
    request: Request,
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """彻底删除已注销的 Key（双步走：先 revoke、再 purge）。

    设计原则：
    1) active Key 不可直接 purge（强制先 revoke），避免静默删除造成 Agent 失联无审计
    2) purge 仅限已 revoke 的 Key，物理 DELETE FROM soc_mcp_keys
    3) 审计作为「mcp_key.purge」事件落 hash 链（与 revoke 一致，不绕过）
    4) viewer/auditor 无自助写权限（与 revoke 一致）
    """
    _ensure_mcp_key_write_allowed(current_user)
    service = MCPKeyService(db)
    # 先拿一次取快照（不能直接调 purge_key 拿不到快照了）
    row = db.query(SOCMCPKey).filter(
        SOCMCPKey.id == key_id, SOCMCPKey.user_id == current_user.id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="MCP Key 不存在")
    if row.status != "revoked":
        raise HTTPException(
            status_code=409,
            detail="仅可彻底删除已注销的 Key；请先「注销」该 Key",
        )
    snapshot = {
        "id": row.id, "name": row.name, "key_prefix": row.key_prefix,
        "key_hash": row.key_hash, "user_id": row.user_id,
        "revoke_reason": row.revoke_reason,
    }
    service.purge_key(user_id=current_user.id, key_id=key_id)
    # 返回值供装饰器取用
    return {"deleted": True, "key_id": key_id, "name": snapshot["name"], "snapshot": snapshot}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_menu_permission("user")),
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

    return _build_user_response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    创建用户

    需要权限: 仅管理员（由 ``require_admin()`` 声明式依赖保证）
    """
    service = UserService(db)
    try:
        user = service.create_user(user_data, creator_id=current_user.id)
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{user_id}", response_model=UserResponse)
@log_audit(
    action="UPDATE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id'),
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    更新用户

    需要权限: 仅管理员（由 ``require_admin()`` 声明式依赖保证）
    """
    service = UserService(db)
    try:
        user = service.update_user(user_id, user_data, updater_id=current_user.id)
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}")
@log_audit(
    action="DELETE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id')
)
async def delete_user(
    request: Request,
    user_id: int,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    删除用户

    需要权限: 仅管理员（由 ``require_admin()`` 声明式依赖保证）
    """
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
@log_audit(
    action="RESET_PASSWORD",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id')
)
async def reset_password(
    request: Request,
    user_id: int,
    password_data: ResetPasswordRequest,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    重置用户密码

    需要权限: 仅管理员（由 ``require_admin()`` 声明式依赖保证）
    """
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
@log_audit(
    action="LOCK",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id'),
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: {"is_locked": kwargs.get('lock_data').is_locked, "lock_reason": kwargs.get('lock_data').lock_reason}
)
async def lock_user(
    request: Request,
    user_id: int,
    lock_data: LockUserRequest,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    锁定或解锁用户

    需要权限: 仅管理员（由 ``require_admin()`` 声明式依赖保证）
    """
    service = UserService(db)
    try:
        user = service.lock_user(
            user_id,
            locked=lock_data.is_locked,
            reason=lock_data.lock_reason,
            admin_id=current_user.id
        )
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# MCP Key 管理端点（admin，设计文档 §4.1 / §6.6）
#
# admin 的权力边界是"断"不是"用"：可看列表（只有前缀）、可代发、可强制注销，
# 任何情况下拿不到明文（库里只有哈希）。
# ============================================================================


def _get_target_user(db: Session, user_id: int) -> User:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return target


@router.get("/{user_id}/mcp-keys", response_model=list[MCPKeyResponse])
async def admin_list_user_mcp_keys(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """查看指定用户的 MCP Key 列表（admin，只读，无明文）"""
    _get_target_user(db, user_id)
    keys = MCPKeyService(db).list_keys(user_id)
    return [_build_key_response(k) for k in keys]


@router.post("/{user_id}/mcp-keys", response_model=MCPKeyCreatedResponse)
@log_audit(
    action="mcp_key.create",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: result.id,
    get_resource_name=lambda result, kwargs: result.name,
    get_new_values=lambda result, kwargs: {
        "name": result.name, "key_prefix": result.key_prefix,
        "proxy_for_user_id": kwargs.get("user_id"),
    },
)
async def admin_create_user_mcp_key(
    request: Request,
    user_id: int,
    payload: MCPKeyCreate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    admin 代发 MCP Key（viewer/auditor 无自助权时由此代发，设计 §7）。

    明文仅在本次响应中返回，由 admin 转交用户，不落库不落日志。
    """
    _get_target_user(db, user_id)
    key_obj, plaintext = MCPKeyService(db).create_key(
        user_id=user_id, name=payload.name, validity_days=payload.validity_days,
    )
    return _build_key_response(key_obj, include_plaintext=plaintext)


@router.delete("/{user_id}/mcp-keys/{key_id}", response_model=MCPKeyResponse)
@log_audit(
    action="mcp_key.admin_revoke",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: kwargs.get("key_id"),
    get_resource_name=lambda result, kwargs: result.name,
    get_new_values=lambda result, kwargs: {"owner_user_id": kwargs.get("user_id")},
)
async def admin_revoke_user_mcp_key(
    request: Request,
    user_id: int,
    key_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """强制注销指定用户的 MCP Key（revoke_reason=admin_revoked）"""
    _get_target_user(db, user_id)
    key_obj = MCPKeyService(db).admin_revoke_key(key_id)
    return _build_key_response(key_obj)


@router.delete("/{user_id}/mcp-keys/{key_id}/purge")
@log_audit(
    action="mcp_key.admin_purge",
    resource_type="mcp_key",
    get_resource_id=lambda result, kwargs: kwargs.get("key_id"),
    get_resource_name=lambda result, kwargs: result.get("name"),
    get_old_values=lambda result, kwargs: result.get("snapshot"),
    get_new_values=lambda result, kwargs: {"deleted": True, "owner_user_id": kwargs.get("user_id")},
)
async def admin_purge_user_mcp_key(
    request: Request,
    user_id: int,
    key_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """admin 彻底删除已注销的 Key（仅可对 status=revoked 物理删除）。

    审计作为「mcp_key.admin_purge」事件落 hash 链；双重审计：先 admin_revoke、再 admin_purge。
    """
    _get_target_user(db, user_id)
    row = db.query(SOCMCPKey).filter(
        SOCMCPKey.id == key_id, SOCMCPKey.user_id == user_id
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="MCP Key 不存在")
    if row.status != "revoked":
        raise HTTPException(
            status_code=409,
            detail="仅可彻底删除已注销的 Key；请先「强制注销」该 Key",
        )
    snapshot = {
        "id": row.id, "name": row.name, "key_prefix": row.key_prefix,
        "key_hash": row.key_hash, "user_id": row.user_id,
        "revoke_reason": row.revoke_reason,
    }
    MCPKeyService(db).admin_purge_key(key_id=key_id)
    return {"deleted": True, "key_id": key_id, "name": snapshot["name"], "snapshot": snapshot}