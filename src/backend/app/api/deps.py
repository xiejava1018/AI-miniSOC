"""
认证相关 FastAPI 依赖集中层

将 `get_current_user` / `require_admin` / `RequireAdmin` / `require_active_user`
/ `require_api_key` 等高频复用依赖统一暴露，方便新代码直接 `from app.api.deps import ...`。

历史原因：`app.core.auth` 仍保留同名符号的导入路径，老代码可继续使用。
新代码优先从本模块导入，便于后续将 `core/auth.py` 收敛为纯 token 编解码原语。
"""

from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.auth import (
    get_current_user,
    RequireAdmin,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User, UserStatus


# 共享 security 依赖（与 core.auth 保持同一实例）
security = HTTPBearer()


# ---------------------------------------------------------------------------
# 便捷依赖
# ---------------------------------------------------------------------------

async def require_active_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    要求当前用户处于 `ACTIVE` 状态的 FastAPI 依赖。

    与 `get_current_user` 的差异：
    - `get_current_user` 允许 `LOCKED` 状态通过（部分业务接口仍可读）
    - `require_active_user` 在 `LOCKED` / `DISABLED` 状态时均返回 403

    用法：
        @router.post("/sensitive-action")
        async def sensitive(
            current_user: User = Depends(require_active_user),
        ):
            ...
    """
    user: User = await get_current_user(credentials, db)
    if user.status in (UserStatus.LOCKED, UserStatus.DISABLED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账户不可用（当前状态：{user.status.value}）",
        )
    return user


async def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> str:
    """
    Collector 服务间认证 — 校验 X-API-Key 请求头。

    用法：
        @router.post("/sync")
        async def sync(_auth: str = Depends(require_api_key)):
            ...
    """
    valid_keys = settings.collector_api_keys_list
    if not valid_keys or x_api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# 扫描器鉴权依赖（P3 资产扫描控制面）
# ---------------------------------------------------------------------------
async def require_scanner_api_key(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    """扫描器端点鉴权：从 X-API-Key 反查 soc_scanner_agents.api_key_hash。

    与 require_api_key（普通采集器）的区别：
      - 普通采集器鉴权走环境变量 COLLECTOR_API_KEYS（多机共享）
      - 扫描器鉴权走 soc_scanner_agents.api_key_hash（每台扫描器独立 Key）

    admin bypass 不提供（扫描器不是人）；hash反查提供 scanner_id 注入 request.state。
    """
    import hashlib
    from app.models.scanner_models import ScannerAgent

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-API-Key",
        )
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    scanner = (
        db.query(ScannerAgent)
        .filter(
            ScannerAgent.api_key_hash == key_hash,
            ScannerAgent.enabled == True,  # noqa: E712
        )
        .first()
    )
    if not scanner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or disabled scanner",
        )
    request.state.scanner_id = scanner.scanner_id
    return scanner


# ---------------------------------------------------------------------------
# 统一导出
# ---------------------------------------------------------------------------

__all__ = [
    "get_current_user",
    "RequireAdmin",
    "require_admin",
    "require_active_user",
    "require_api_key",
    "require_scanner_api_key",
]


# RequireAdmin 实例的便捷别名
# 兼容旧用法：`Depends(require_admin)` / `Depends(RequireAdmin())`
require_admin = RequireAdmin()
