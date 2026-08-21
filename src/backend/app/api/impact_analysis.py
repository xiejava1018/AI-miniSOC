"""
变更影响分析 API（PRD P3 / F3.1）

端点：
  POST /api/v1/assets/impact-analysis    # 用户描述计划变更，AI 评估影响范围

注意：路由必须在 assets.router 之前注册——否则 /assets/{asset_id}
抢匹配（虽然「impact-analysis」带连字符不易撞，但保险起见同 asset_reconciliation 同款做法）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.permissions import require_role
from app.models import User
from app.services.impact_analysis import ImpactAnalysisService
from app.services.audit_log_service import AuditLogService

router = APIRouter()


class ImpactAnalysisRequest(BaseModel):
    change_description: str = Field(..., min_length=3, max_length=2000,
                                     description="计划变更的自然语言描述")
    change_window_hours: int = Field(4, ge=1, le=168,
                                     description="计划维护窗口时长（1-168 小时）")


@router.post("/impact-analysis", summary="智能变更影响分析（PRD P3 / F3.1）")
async def impact_analysis(
    body: ImpactAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """
    输入变更描述，返回受影响资产、关联业务、历史告警、潜在风险与维护窗口建议。

    降级说明（与 reconcile_ai 同款）：
      - OpenSearch 不可达 / GLM 预算耗尽 / GLM Key 缺失 / 调用失败
        → 自动降级为基于事实拼出的模板报告，并在 data_degraded=true 时
        显式声明「数据可信度降级，结果可能不全」
      - 描述里没有识别到具体资产 → 返回未匹配提示，仍会尝试粗略建议
    """
    try:
        result = ImpactAnalysisService(db).analyze(
            change_description=body.change_description.strip(),
            change_window_hours=body.change_window_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # X1：写操作落审计。impact-analysis 是查询+分析，无数据变更，
    # 但 PRD X1 把"知识/AI 产物"视为软性资产，审计可追溯谁用何时触发了分析。
    AuditLogService(db).create_audit_log(
        user_id=current_user.id,
        username=current_user.username,
        action="QUERY",
        resource_type="impact_analysis",
        resource_name=f"impact:{result.get('provenance', {}).get('generated_at', '')[:19]}",
        new_values={
            "change_description": body.change_description[:200],
            "window_hours": body.change_window_hours,
            "target_count": result.get("provenance", {}).get("target_count", 0),
            "source": result.get("source"),
        },
    )

    return {"code": 200, "msg": "success", "data": result}