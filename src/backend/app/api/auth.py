"""
认证API
提供登录、登出、token刷新等认证相关接口
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import create_access_token, create_refresh_token, verify_token, get_current_user
from app.core.config import settings
from app.core.security import verify_password
from app.core.captcha import create_captcha, verify_captcha
from app.core.token_blacklist import revoke as revoke_token
from app.models.user import User, UserStatus
from app.services.audit_log_service import AuditLogService
from app.schemas.user import UserResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


# ============================================================================
# 登录失败计数（in-memory）
# 多 worker 部署不共享；单进程可接受，生产建议替换为 Redis
# key = "username:ip" → (consecutive_failures, first_fail_at)
# ============================================================================
_login_attempts: dict[str, tuple[int, datetime]] = {}


def _record_login_failure(username: str, ip: Optional[str]) -> int:
    """
    记录一次登录失败，返回当前累计连续失败次数。

    若首次失败时间距今已超过 ``ACCESS_TOKEN_LOCKOUT_MINUTES``，自动重置计数，
    避免攻击者以极低频"打草稿"式长期探测。
    """
    key = f"{username}:{ip or 'unknown'}"
    now = datetime.utcnow()
    count, first_fail = _login_attempts.get(key, (0, now))

    if first_fail and (now - first_fail) > timedelta(
        minutes=settings.ACCESS_TOKEN_LOCKOUT_MINUTES
    ):
        count = 0
        first_fail = now

    count += 1
    _login_attempts[key] = (count, first_fail)
    return count


def _clear_login_attempts(username: str, ip: Optional[str]) -> None:
    """登录成功后清除该 username:ip 的失败计数与首次失败时间戳。"""
    key = f"{username}:{ip or 'unknown'}"
    _login_attempts.pop(key, None)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    captcha_key: Optional[str] = Field(None, description="验证码key")
    captcha_code: Optional[str] = Field(None, description="验证码")


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
    refresh_token: str = Field(..., description="新的刷新令牌（旧的已被撤销，轮换后旧 refresh 一次性使用）")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    用户登录

    验证用户凭据并返回JWT token

    Args:
        request: 登录请求（用户名、密码）
        req: FastAPI Request对象（用于获取IP和User-Agent）
        db: 数据库会话

    Returns:
        LoginResponse: 包含access_token、refresh_token和用户信息

    Raises:
        HTTPException 401: 用户名或密码错误
        HTTPException 403: 账户被锁定或禁用
    """
    # 获取客户端信息
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")

    # 初始化审计日志服务
    audit_service = AuditLogService(db)

    # 1. 验证码校验（如果提供了验证码）
    if request.captcha_key and request.captcha_code:
        if not verify_captcha(request.captcha_key, request.captcha_code):
            audit_service.log_login(
                user_id=None,
                username=request.username,
                ip_address=client_ip,
                user_agent=user_agent,
                status="failure",
                error_message="验证码错误"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="验证码错误或已过期"
            )

    # 2. 查询用户
    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        # 记录登录失败审计日志（用户不存在）
        audit_service.log_login(
            user_id=None,
            username=request.username,
            ip_address=client_ip,
            user_agent=user_agent,
            status="failure",
            error_message="用户名或密码错误"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 2. 检查账户状态
    if user.status == UserStatus.LOCKED:
        # 记录登录失败审计日志（账户锁定）
        audit_service.log_login(
            user_id=user.id,
            username=user.username,
            ip_address=client_ip,
            user_agent=user_agent,
            status="failure",
            error_message="账户已被锁定"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被锁定，请联系管理员"
        )

    if user.status == UserStatus.DISABLED:
        # 记录登录失败审计日志（账户禁用）
        audit_service.log_login(
            user_id=user.id,
            username=user.username,
            ip_address=client_ip,
            user_agent=user_agent,
            status="failure",
            error_message="账户已被禁用"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    # 3. 验证密码
    if not verify_password(request.password, user.password_hash):
        # 累计连续失败次数，达到阈值自动锁定账户
        fail_count = _record_login_failure(request.username, client_ip)
        if fail_count >= settings.ACCESS_TOKEN_ATTEMPT_LIMIT:
            user.status = UserStatus.LOCKED
            db.commit()
            audit_service.log_login(
                user_id=user.id,
                username=user.username,
                ip_address=client_ip,
                user_agent=user_agent,
                status="failure",
                error_message=f"连续{fail_count}次登录失败，账户已自动锁定"
            )
        else:
            audit_service.log_login(
                user_id=user.id,
                username=user.username,
                ip_address=client_ip,
                user_agent=user_agent,
                status="failure",
                error_message="用户名或密码错误"
            )
        # 不在 401 响应里透露锁定状态，避免攻击者判断用户名是否有效
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 4. 检查是否是管理员（is_superuser优先于role）
    is_admin = user.is_superuser or (user.role and user.role.code == "admin")

    # 5. 创建JWT tokens
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

    # 6. 登录成功：清零该 username:ip 的失败计数
    _clear_login_attempts(user.username, client_ip)

    # 7. 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()

    # 8. 记录登录成功审计日志
    audit_service.log_login(
        user_id=user.id,
        username=user.username,
        ip_address=client_ip,
        user_agent=user_agent,
        status="success"
    )

    # 9. 返回响应
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


@router.get("/captcha")
async def get_captcha():
    """
    获取验证码

    生成图形验证码并返回base64图片

    Returns:
        captcha_key: 验证码key（用于登录时验证）
        captcha_image: base64编码的验证码图片
    """
    key, image = create_captcha()
    return {
        "captcha_key": key,
        "captcha_image": image
    }


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    刷新访问令牌（refresh token 轮换）

    每次刷新都会：
    1. 把传入的旧 refresh jti 加入黑名单（一次性使用，防重放）
    2. 签发新 access + 新 refresh
    3. 同时返回两个新 token

    Args:
        request: 刷新令牌请求
        db: 数据库会话

    Returns:
        RefreshTokenResponse: 新的 access + 新的 refresh

    Raises:
        HTTPException 401: 刷新令牌无效（已撤销/过期/伪造/账户不可用）
    """
    try:
        # 1. 验证 refresh token（包含黑名单校验）
        payload = verify_token(request.refresh_token, "refresh")
        user_id = int(payload.get("sub"))

        # 2. 把旧 refresh 的 jti 加入黑名单（一次性使用）
        old_jti = payload.get("jti")
        old_exp = payload.get("exp")
        if old_jti and old_exp is not None:
            old_exp_ts = old_exp.timestamp() if hasattr(old_exp, "timestamp") else float(old_exp)
            revoke_token(old_jti, old_exp_ts)

        # 3. 查询用户
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌"
            )

        # 4. 检查用户状态
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户不可用"
            )

        # 5. 创建新的 access token + 新的 refresh token
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

        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token({"sub": str(user.id)})

        return RefreshTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"刷新令牌无效: {str(e)}"
        )


@router.post("/logout")
async def logout(
    req: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    用户登出

    将当前 access token 的 jti 加入黑名单，使该 token 立即失效。
    客户端也应删除本地存储的 access / refresh token。
    """
    # 1. 解码当前 access token 拿到 jti / exp，加入黑名单
    # verify_token 已包含黑名单校验（首次登出时该 jti 尚未撤销，必然通过）
    payload = verify_token(credentials.credentials, "access")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp is not None:
        # jose 返回的 exp 是带 tz 的 datetime
        exp_ts = exp.timestamp() if hasattr(exp, "timestamp") else float(exp)
        revoke_token(jti, exp_ts)

    # 2. 记录登出审计日志
    audit_service = AuditLogService(db)
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")

    audit_service.log_logout(
        user_id=current_user.id,
        username=current_user.username,
        ip_address=client_ip,
        user_agent=user_agent
    )

    return {
        "success": True,
        "message": "登出成功"
    }


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户信息

    需要认证。

    Returns:
        当前用户信息（通过 ``UserResponse`` 显式序列化，避免 ORM 对象直返）。
    """
    return UserResponse.model_validate(current_user)
