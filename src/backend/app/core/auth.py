"""
JWT认证和授权模块
提供JWT token创建/验证、用户认证依赖等功能
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Union

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


# OAuth2密码模式的token URL（用于FastAPI文档UI）
# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 使用HTTP Bearer认证（更灵活）
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌

    Args:
        data: 要编码到token中的数据（通常包含user_id, username等）
        expires_delta: 过期时间增量，默认2小时

    Returns:
        str: JWT访问令牌
    """
    to_encode = data.copy()

    # 设置过期时间
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # 添加token类型、过期时间以及标准声明（iss, aud, iat, jti）
    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "type": "access"
    })

    # 编码JWT
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    创建JWT刷新令牌

    Args:
        data: 要编码到token中的数据（通常包含user_id）

    Returns:
        str: JWT刷新令牌（有效期7天）
    """
    to_encode = data.copy()

    # 设置7天过期
    now = datetime.utcnow()
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    # 添加标准声明
    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "type": "refresh"
    })

    # 编码JWT
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> dict:
    """
    验证并解码JWT令牌

    Args:
        token: JWT令牌
        token_type: 令牌类型（"access" 或 "refresh"）

    Returns:
        dict: 解码后的payload

    Raises:
        HTTPException: 令牌无效或过期时抛出401错误
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 解码JWT，校验 iss / aud / exp / iat
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        # 验证token类型
        if token_type and payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"无效的令牌类型，期望{token_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 校验黑名单
        from app.core.token_blacklist import is_revoked
        jti = payload.get("jti")
        if jti and is_revoked(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌已撤销",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"令牌验证失败: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI依赖：从JWT令牌中获取当前用户

    用法：
        @app.get("/api/users/me")
        async def get_me(current_user: User = Depends(get_current_user)):
            return current_user

    Args:
        credentials: HTTP Bearer认证凭据
        db: 数据库会话

    Returns:
        User: 当前用户信息

    Raises:
        HTTPException: 认证失败或用户状态无效时抛出401/403错误
    """
    # 1. 验证token
    token = credentials.credentials
    payload = verify_token(token, "access")

    # 2. 从payload中提取用户信息
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌载荷",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. 从数据库查询用户
    from app.models.user import User, UserStatus
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. 检查用户状态
    if user.status == UserStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账户已被禁用"
        )
    # 允许 locked 状态，有些接口可能需要处理逻辑，但登录会被拦截

    return user


class RequireAdmin:
    """
    FastAPI依赖类：要求管理员权限

    用法：
        @app.post("/api/users")
        async def create_user(
            current_user: User = Depends(RequireAdmin())
        ):
            # 只有管理员可以访问
            pass

    或者作为类依赖：
        @app.post("/api/users", dependencies=[Depends(RequireAdmin())])
        async def create_user():
            pass
    """

    def __init__(self):
        """初始化RequireAdmin依赖"""
        pass

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> User:
        """
        验证当前用户是否为管理员

        Args:
            credentials: HTTP Bearer认证凭据
            db: 数据库会话

        Returns:
            User: 当前管理员用户

        Raises:
            HTTPException: 非管理员用户抛出403错误
        """
        # 获取当前用户
        current_user = await get_current_user(credentials, db)

        # 检查是否为管理员
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，需要管理员角色"
            )

        return current_user


# 便捷函数：创建 RequireAdmin 依赖实例
require_admin = RequireAdmin()
