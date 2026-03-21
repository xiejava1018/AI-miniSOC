"""
认证API
提供登录、登出、token刷新等认证相关接口
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import create_access_token, create_refresh_token, verify_token
from app.core.security import verify_password
from app.models.user import User, UserStatus
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


# ============================================================================
# Pydantic Schemas
# ============================================================================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    user: dict = Field(..., description="用户信息")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str = Field(..., description="刷新令牌")


class RefreshTokenResponse(BaseModel):
    """刷新令牌响应"""
    access_token: str = Field(..., description="新的访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    用户登录

    验证用户凭据并返回JWT token

    Args:
        request: 登录请求（用户名、密码）
        db: 数据库会话

    Returns:
        LoginResponse: 包含access_token、refresh_token和用户信息

    Raises:
        HTTPException 401: 用户名或密码错误
        HTTPException 403: 账户被锁定或禁用
    """
    # 1. 查询用户
    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 2. 检查账户状态
    if user.status == UserStatus.LOCKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被锁定，请联系管理员"
        )

    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    # 3. 验证密码
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 4. 检查是否是管理员（is_superuser优先于role）
    is_admin = user.is_superuser or (user.role and user.role.code == "admin")

    # 5. 创建JWT tokens
    from app.core.config import settings

    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role_id": user.role_id,
        "role_name": user.role.code if user.role else None,
        "is_admin": is_admin,
        "is_active": user.status == UserStatus.ACTIVE,
        "is_locked": user.status == UserStatus.LOCKED,
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    # 6. 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()

    # 7. 返回响应
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "role_name": user.role.code if user.role else None,
            "is_admin": is_admin,
            "status": user.status,
            "last_login": user.last_login.isoformat() if user.last_login else None
        }
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    刷新访问令牌

    使用refresh_token获取新的access_token

    Args:
        request: 刷新令牌请求
        db: 数据库会话

    Returns:
        RefreshTokenResponse: 新的访问令牌

    Raises:
        HTTPException 401: 刷新令牌无效
    """
    try:
        # 1. 验证refresh token
        payload = verify_token(request.refresh_token, "refresh")
        user_id = int(payload.get("sub"))

        # 2. 查询用户
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌"
            )

        # 3. 检查用户状态
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户不可用"
            )

        # 4. 创建新的access token
        is_admin = user.is_superuser or (user.role and user.role.code == "admin")

        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "role_name": user.role.code if user.role else None,
            "is_admin": is_admin,
            "is_active": user.status == UserStatus.ACTIVE,
        }

        access_token = create_access_token(token_data)

        from app.core.config import settings

        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"刷新令牌无效: {str(e)}"
        )


@router.post("/logout")
async def logout():
    """
    用户登出

    客户端应删除存储的token
    目前token是无状态的，客户端删除即可
    未来可以实现token黑名单

    Returns:
        成功消息
    """
    return {
        "success": True,
        "message": "登出成功"
    }


@router.get("/me")
async def get_current_user_info(
    current_user: dict = Depends(lambda: None)  # 临时实现，后续需要真正的认证
):
    """
    获取当前用户信息

    需要认证

    Returns:
        当前用户信息
    """
    # TODO: 实现真实的认证逻辑
    # 目前返回401，需要前端先调用login
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="需要先登录"
    )
