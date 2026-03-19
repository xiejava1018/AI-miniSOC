"""
认证API端点
提供登录、登出、令牌刷新、密码修改等接口
"""

import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, security
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Dict, List

from app.database import get_db
from app.core.auth import get_current_user, verify_token, create_access_token
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    UserMeResponse,
    RefreshTokenRequest
)
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.models.user import User
from app.models.user_session import UserSession
from app.models.menu import Menu


router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    req: Request = None
) -> TokenResponse:
    """
    用户登录

    Args:
        request: 登录请求（用户名、密码）
        db: 数据库会话
        req: FastAPI Request对象（用于获取IP和User-Agent）

    Returns:
        TokenResponse: 包含access_token和refresh_token

    Raises:
        HTTPException 400: 请求参数错误
        HTTPException 401: 认证失败
    """
    # 获取客户端信息
    ip_address = req.client.host if req and req.client else None
    user_agent = req.headers.get("user-agent") if req else None

    # 验证用户
    user, error_msg, token_data = AuthService.authenticate_user(
        db=db,
        username=request.username,
        password=request.password,
        ip_address=ip_address,
        user_agent=user_agent
    )

    if error_msg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )

    # 添加expires_in到响应
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    token_data["expires_in"] = expires_in

    return TokenResponse(**token_data)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    req: Request = None
):
    """
    用户登出

    Args:
        credentials: HTTP Bearer认证凭据
        db: 数据库会话
        current_user: 当前认证用户
        req: FastAPI Request对象

    Returns:
        dict: 成功消息

    Raises:
        HTTPException 401: 未认证
    """
    token = credentials.credentials

    # 从token中解析session_id
    # session_id通过对access_token哈希匹配数据库中存储的token_hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # 查找对应的会话
    session = db.query(UserSession).filter(
        and_(
            UserSession.token_hash == token_hash,
            UserSession.user_id == current_user.id,
            UserSession.is_active == True
        )
    ).first()

    ip_address = req.client.host if req and req.client else None
    user_agent = req.headers.get("user-agent") if req else None

    # 查询完整用户对象
    user = db.query(User).filter(User.id == current_user.id).first()

    if session:
        AuthService.logout_user(
            db=db,
            user=user,
            session_id=session.id,
            ip_address=ip_address,
            user_agent=user_agent
        )
    else:
        # 如果找不到会话，仍然返回成功（幂等操作）
        pass

    return {"message": "登出成功"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    刷新访问令牌

    Args:
        request: 刷新令牌请求
        db: 数据库会话

    Returns:
        TokenResponse: 新的访问令牌

    Raises:
        HTTPException 401: 刷新令牌无效
    """
    # 验证refresh_token签名和类型
    try:
        payload = verify_token(request.refresh_token, "refresh")
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 获取用户ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌载荷"
        )

    # 查询用户
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    # 检查用户状态
    from app.models.user import UserStatus
    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账户已被禁用"
        )

    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账户已被锁定"
        )

    # 验证refresh_token是否在数据库中存在且激活
    refresh_token_hash = hashlib.sha256(request.refresh_token.encode()).hexdigest()
    session = db.query(UserSession).filter(
        and_(
            UserSession.refresh_token_hash == refresh_token_hash,
            UserSession.user_id == user.id,
            UserSession.is_active == True
        )
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌已失效，请重新登录"
        )

    # 生成新的access_token
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "role_name": user.role.code if user.role else None,
            "is_admin": user.is_admin
        }
    )

    # 计算过期时间
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(
        access_token=access_token,
        refresh_token=request.refresh_token,
        token_type="bearer",
        expires_in=expires_in
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    req: Request = None
):
    """
    修改密码

    Args:
        request: 修改密码请求
        db: 数据库会话
        current_user: 当前认证用户
        req: FastAPI Request对象

    Returns:
        dict: 成功消息

    Raises:
        HTTPException 400: 请求参数错误
        HTTPException 401: 未认证
    """
    # 验证新密码和确认密码是否一致
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码和确认密码不一致"
        )

    ip_address = req.client.host if req and req.client else None
    user_agent = req.headers.get("user-agent") if req else None

    # 查询完整用户对象
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    # 修改密码
    success, error_msg = AuthService.change_password(
        db=db,
        user=user,
        old_password=request.old_password,
        new_password=request.new_password,
        ip_address=ip_address,
        user_agent=user_agent
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    return {"message": "密码修改成功"}


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user)
) -> UserMeResponse:
    """
    获取当前用户信息，包括菜单权限

    Args:
        db: 数据库会话
        current_user: 当前认证用户

    Returns:
        UserMeResponse: 当前用户信息和权限
    """
    # 查询完整用户对象
    user = db.query(User).filter(User.id == current_user.id).first()

    # 获取用户菜单权限（提取权限路径列表）
    permissions: List[str] = []
    if user and user.role and user.role.menus:
        for menu in user.role.menus:
            if menu.path:
                permissions.append(menu.path)

    # 如果是管理员，添加所有权限（通过标记以区分特殊权限）
    if user and user.is_admin:
        permissions.append("*")

    return UserMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        role_id=current_user.role_id,
        role_name=current_user.role_name,
        permissions=permissions
    )
