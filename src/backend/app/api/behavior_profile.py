"""行为画像 API（Phase 2，方案 §9.4 v1.5）

权限（X1 矩阵对齐）：
  - 读（profile/domains/trend/list）：admin + auditor（审计用途）
  - 写（refresh）：admin + operator（require_button_permission，authMark 种在子菜单 permissions）
所有查看行为记入 soc_audit_logs（§6 访问控制）。
注意：HTTP 状态码恒 200，业务错误在 body.code（envelope 中间件）。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.permissions import require_button_permission, require_role
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.behavior_profile import service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _audit(user: User, action: str, ip: str, detail: str = "") -> None:
    """画像查看/操作留痕（§6）。独立 session，失败不阻断业务。"""
    try:
        AuditLogService(SessionLocal()).create_audit_log(
            user_id=user.id,
            username=user.username,
            action=action,
            resource_type="behavior_profile",
            resource_name=ip,
            new_values={"target": ip, "detail": detail} if detail else {"target": ip},
        )
    except Exception:
        logger.exception("画像审计留痕失败（不阻断）")


@router.get("/behavior-profile/list")
async def get_behavior_profiles(
    traffic_type: Optional[str] = Query(None, pattern="^(human|machine|mixed)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_profiles_summary(db, traffic_type=traffic_type, limit=limit)
    _audit(current_user, "QUERY", "*", f"list traffic_type={traffic_type}")
    return {"total": len(data), "items": data}


@router.get("/behavior-profile/{ip}")
async def get_behavior_profile(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    realtime: int = Query(0, ge=0, le=1,
                          description="1=当日实时（仅限当日口径，不走快照）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    if realtime:
        try:
            data = svc.compute_realtime(db, ip)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"实时计算失败: {e}")
        _audit(current_user, "QUERY", ip, "realtime=24h")
        return {"realtime": True, **data}

    data = svc.get_profile(db, ip, days)
    if data is None:
        raise HTTPException(status_code=404, detail=f"该 IP 无画像快照: {ip}")
    _audit(current_user, "QUERY", ip, f"days={days}")
    return data


@router.get("/behavior-profile/{ip}/domains")
async def get_behavior_domains(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=200),
    category: Optional[str] = Query(None, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_domains(db, ip, days, limit=limit, category=category)
    _audit(current_user, "QUERY", ip, f"domains days={days} category={category}")
    return {"ip": ip, "days": days, "total": len(data), "items": data}


@router.get("/behavior-profile/{ip}/trend")
async def get_behavior_trend(
    ip: str,
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_trend(db, ip, days)
    _audit(current_user, "QUERY", ip, f"trend days={days}")
    return {"ip": ip, "days": days, "items": data}




@router.post("/behavior-profile/{ip}/refresh")
async def refresh_behavior_profile(
    ip: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("behavior-profile", "refresh")),
):
    """触发当日实时重算（写操作，admin/operator）。"""
    try:
        data = svc.compute_realtime(db, ip)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"实时重算失败: {e}")
    _audit(current_user, "UPDATE", ip, "refresh(实时重算)")
    return data
