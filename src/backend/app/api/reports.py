"""AI 安全报告 API（PRD P3 / F2.2）

PRD 端点：
  POST /api/v1/reports/generate            # 同步生成（用户点一下等结果）
  GET  /api/v1/reports                     # 列表（分页）
  GET  /api/v1/reports/latest              # 按类型取最新一份
  GET  /api/v1/reports/{report_id}         # 详情
  POST /api/v1/reports/check-incident-trigger   # 事件驱动触发检查（供 cron / 前端按钮）

错误约定：
  业务错误走响应中间件（body.code 非 200），HTTP 状态恒为 200。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.models.security_report import REPORT_TYPES
from app.services.report_generator import (
    DEFAULT_INCIDENT_THRESHOLD,
    SecurityReportService,
    _get_config,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schema（仅本地用；完整 schema 不公开，仅 API 入参出参）
# ---------------------------------------------------------------------------

class GenerateReportRequest(BaseModel):
    report_type: str = Field(..., description="weekly/monthly/on_demand/incident_driven")
    period_start: Optional[datetime] = Field(None, description="on_demand 必填")
    period_end: Optional[datetime] = Field(None, description="on_demand 必填")
    force_glm: bool = Field(True, description="是否尝试调用 GLM；false 则强制走模板")


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.post("/reports/generate", summary="生成 AI 安全报告（同步）")
async def generate_report(
    body: GenerateReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.report_type not in REPORT_TYPES:
        return {
            "code": 400,
            "msg": f"report_type 须为 {sorted(REPORT_TYPES)} 之一",
            "data": None,
        }
    if body.report_type == "on_demand" and (not body.period_start or not body.period_end):
        return {
            "code": 400,
            "msg": "on_demand 类型必须传 period_start 与 period_end",
            "data": None,
        }

    svc = SecurityReportService(db)
    try:
        report = svc.generate(
            report_type=body.report_type,
            triggered_by=current_user.username,
            period_start=body.period_start,
            period_end=body.period_end,
            force_glm=body.force_glm,
        )
    except ValueError as exc:
        return {"code": 400, "msg": str(exc), "data": None}
    except Exception as exc:  # noqa: BLE001
        # 报告生成失败不影响其它功能，给清楚原因
        return {
            "code": 500,
            "msg": f"报告生成失败：{exc.__class__.__name__}: {exc}",
            "data": None,
        }
    return {
        "code": 200,
        "msg": "success",
        "data": SecurityReportService._serialize(report),
    }


@router.get("/reports", summary="报告列表")
async def list_reports(
    report_type: Optional[str] = Query(None, description="按类型过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_type and report_type not in REPORT_TYPES:
        return {
            "code": 400,
            "msg": f"report_type 须为 {sorted(REPORT_TYPES)} 之一",
            "data": None,
        }
    result = SecurityReportService(db).list(report_type, page, page_size)
    return {"code": 200, "msg": "success", "data": result}


@router.get("/reports/latest", summary="最新一份报告（按类型）")
async def latest_report(
    report_type: str = Query(..., description="weekly/monthly/incident_driven/..."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_type not in REPORT_TYPES:
        return {
            "code": 400,
            "msg": f"report_type 须为 {sorted(REPORT_TYPES)} 之一",
            "data": None,
        }
    result = SecurityReportService(db).latest(report_type)
    if not result:
        return {
            "code": 404,
            "msg": f"尚无 {report_type} 类型的报告，请先生成",
            "data": None,
        }
    return {"code": 200, "msg": "success", "data": result}


@router.get("/reports/{report_id}", summary="报告详情")
async def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = SecurityReportService(db).get(report_id)
    if not result:
        return {"code": 404, "msg": "报告不存在", "data": None}
    return {"code": 200, "msg": "success", "data": result}


@router.post("/reports/check-incident-trigger", summary="事件驱动触发检查")
async def check_incident_trigger(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """过去 24h 累计 critical+high 告警 ≥ 阈值时生成 incident_driven 报告。

    返回 { triggered: bool, report?: dict, critical_high_count: int, threshold: int }
    未达阈值也返回 200，便于前端定时器心跳式调用。
    """
    svc = SecurityReportService(db)
    # 复用 svc 的内部方法（不重复 _collect_alert_trends 逻辑）
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    opensearch_ok, err, alerts = svc._collect_alert_trends(start, now)
    crit_high = alerts.get("critical", 0) + alerts.get("high", 0)
    threshold = _get_config(db, "incident_threshold", DEFAULT_INCIDENT_THRESHOLD)
    payload = {
        "triggered": False,
        "critical_high_count": crit_high,
        "threshold": threshold,
        "opensearch_ok": opensearch_ok,
        "opensearch_error": err,
    }
    if not opensearch_ok:
        payload["reason"] = "opensearch_unavailable"
        return {"code": 200, "msg": "ok", "data": payload}
    if crit_high < threshold:
        payload["reason"] = "below_threshold"
        return {"code": 200, "msg": "ok", "data": payload}

    report = svc.check_incident_trigger(triggered_by=current_user.username)
    if report:
        payload["triggered"] = True
        payload["report"] = SecurityReportService._serialize(report)
    return {"code": 200, "msg": "ok", "data": payload}