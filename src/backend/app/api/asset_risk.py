"""
资产风险评分 API（PRD F1.1 / v1.2.1）

路由挂在 /assets 前缀下，且必须在 assets.router 之前注册
（/ask 是单段静态路径，会被 assets 的 GET /{asset_id} 抢匹配——本文件路径均为
 /risk/* 两段或 /{asset_id}/risk，不受影响；asset_query 的 /ask 才是关键）。

权限（PRD 横切 X1）：
- 查看（overview/rules/history/单资产 risk）：登录用户
- 批量重算：登录用户（operator 可触发，属于只读计算无破坏性）
- 规则调整（PUT /risk/rules）：admin only，落审计日志
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.models.audit_log import AuditLog
from app.services.asset_risk import AssetRiskService

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


def _parse_asset_id(asset_id: str):
    try:
        return uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="资产 ID 格式错误")


# ---------- 查询类 ----------

@router.get("/risk/overview")
def risk_overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """风险总览：分数段分布 + Top10 + 评分上升最快 + AI 预算状态"""
    return AssetRiskService(db).overview()


@router.get("/risk/rules")
def get_risk_rules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """当前生效的完整评分规则（默认 + DB 覆盖深合并结果）"""
    return {"rules": AssetRiskService(db).load_rules(force=True)}


class RiskRulesUpdate(BaseModel):
    override: dict  # 仅覆盖要改的键，与默认规则深合并


@router.put("/risk/rules")
def update_risk_rules(
    body: RiskRulesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """调整评分权重/阈值（admin，落审计）；权重和必须为 1.0"""
    _require_admin(current_user)
    svc = AssetRiskService(db)
    try:
        merged = svc.save_rules(body.override, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.add(AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        resource_type="system_config",
        resource_name="risk_rules",
        new_values=body.override,
        status="success",
    ))
    db.commit()
    return {"message": "评分规则已更新", "rules": merged}


@router.post("/risk/batch-score")
def batch_score(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """批量重算全部资产风险评分（规则引擎本地计算 + 限额内 GLM 摘要）"""
    stats = AssetRiskService(db).score_all()
    return {"message": "批量评分完成", "stats": stats}


# ---------- 单资产 ----------

@router.get("/{asset_id}/risk")
def get_asset_risk(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """单资产风险详情：评分 + AI 摘要 + score_breakdown（可解释性）"""
    data = AssetRiskService(db).get_risk(_parse_asset_id(asset_id))
    if not data:
        raise HTTPException(status_code=404, detail="资产不存在")
    return data


@router.get("/{asset_id}/risk/history")
def get_asset_risk_history(
    asset_id: str,
    days: int = 90,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """风险评分历史（趋势折线数据）"""
    asset_uuid = _parse_asset_id(asset_id)
    history = AssetRiskService(db).get_history(asset_uuid, days=min(max(days, 1), 365))
    return {"asset_id": asset_id, "history": history}


@router.post("/{asset_id}/risk/refresh-summary")
def refresh_asset_risk_summary(
    asset_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """单资产按需生成风险摘要（详情页「刷新」按钮）。

    绕过批量 min_score 门槛（用户显式请求），成本由 ai_budget 限流兑底；
    GLM 不可用降级规则化文案；N/A 资产返回 message 提示。
    """
    data = AssetRiskService(db).refresh_summary(_parse_asset_id(asset_id))
    if not data:
        raise HTTPException(status_code=404, detail="资产不存在")
    return data
