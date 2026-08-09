"""
告警治理 API：告警簇聚合查询 + 每日摘要

前缀挂在 /alerts 下：
  GET /alerts/groups            -> 告警指纹聚合（去重为"簇"）
  GET /alerts/groups/{fp}       -> 单簇明细 + 样本 + 资产关联
  POST /alerts/digest/generate  -> 手动生成摘要
  GET  /alerts/digest/latest    -> 最近一条摘要
  GET  /alerts/digest?date=     -> 按日期取摘要
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.services.alert_query import AlertQueryService
from app.services.alert_digest_service import AlertDigestService
from app.services.alert_group_snapshot_service import AlertGroupSnapshotService
from app.services.alert_group_triage_service import AlertGroupTriageService

router = APIRouter()


@router.get("/groups")
async def list_alert_groups(
    hours: int = Query(24, ge=1, le=720),
    min_count: int = Query(1, ge=1, description="簇最小告警数，低于此不计"),
    level: Optional[int] = Query(None, description="仅统计 >= 该等级的告警"),
    limit: int = Query(20, ge=1, le=100, description="按簇大小返回的 TopN"),
    db: Session = Depends(get_db),
):
    """将原始告警按 (rule.id, agent.id) 聚合为有限个告警簇，按数量降序。"""
    try:
        svc = AlertQueryService(db)
        return svc.get_alert_groups(
            hours=hours, min_count=min_count, level=level, limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"告警簇聚合失败: {str(e)}")


@router.get("/groups/history")
async def get_alert_group_history(
    date: Optional[str] = Query(None, description="按快照日期 YYYY-MM-DD 过滤"),
    asset_ip: Optional[str] = Query(None, description="按资产 IP 过滤"),
    level: Optional[int] = Query(None, description="仅返回最高等级 >= 该值的簇"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """历史快照列表（方案 B）：来自 soc_alert_groups，可按日期/资产/等级过滤。"""
    try:
        svc = AlertGroupSnapshotService(db)
        rows = svc.query_history(date=date, asset_ip=asset_ip, level=level, limit=limit)
        return [r.to_dict() for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询告警簇历史失败: {str(e)}")


@router.get("/groups/trend")
async def get_alert_group_trend(
    days: int = Query(14, ge=1, le=90, description="趋势跨度（天）"),
    db: Session = Depends(get_db),
):
    """趋势数据（方案 B）：按天聚合簇数 / 告警量 / 关联资产，供趋势图。"""
    try:
        svc = AlertGroupSnapshotService(db)
        return svc.get_trend(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询告警簇趋势失败: {str(e)}")


@router.post("/snapshot/generate")
async def generate_snapshot(
    hours: int = Query(24, ge=1, le=720, description="统计窗口(小时)"),
    db: Session = Depends(get_db),
):
    """手动触发一次告警簇快照（落库 soc_alert_groups）。"""
    try:
        svc = AlertGroupSnapshotService(db)
        return svc.snapshot(hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成告警簇快照失败: {str(e)}")


@router.get("/groups/triage-top")
async def get_alert_triage_top(
    hours: int = Query(24, ge=1, le=720, description="统计窗口(小时)"),
    top_n: int = Query(None, ge=1, le=100, description="研判 TopN（缺省用系统配置）"),
    force_refresh: bool = Query(False, description="强制刷新缓存 verdict"),
    db: Session = Depends(get_db),
):
    """今日必处理清单：对 TopN 告警簇做 AI 研判，按 P0>P1>P2>P3 排序返回。

    注意：本路由必须在 /groups/{fingerprint} 之前注册，否则会被其 catch-all 抢匹配。
    """
    try:
        svc = AlertGroupTriageService(db)
        return await svc.triage_top_groups(hours=hours, top_n=top_n, force_refresh=force_refresh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"告警簇 AI 研判失败: {str(e)}")


@router.get("/groups/{fingerprint}")
async def get_alert_group(
    fingerprint: str,
    hours: int = Query(24, ge=1, le=720),
    sample_size: int = Query(5, ge=1, le=20, description="返回的样本告警条数"),
    db: Session = Depends(get_db),
):
    """单簇明细：样本、等级/时间分布、攻击者源 IP、关联资产。"""
    try:
        svc = AlertQueryService(db)
        return svc.get_alert_group_detail(
            fingerprint=fingerprint, hours=hours, sample_size=sample_size
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"告警簇明细失败: {str(e)}")


@router.get("/groups/{fingerprint}/triage")
async def get_alert_group_triage(
    fingerprint: str,
    db: Session = Depends(get_db),
):
    """取某告警簇的缓存 AI verdict（无则返回 404）。"""
    svc = AlertGroupTriageService(db)
    verdict = svc.get_cached_verdict(fingerprint)
    if not verdict:
        raise HTTPException(status_code=404, detail="该告警簇尚无 AI 研判缓存")
    return verdict


@router.post("/groups/{fingerprint}/triage")
async def triage_alert_group(
    fingerprint: str,
    hours: int = Query(24, ge=1, le=720, description="统计窗口(小时)"),
    force_refresh: bool = Query(False, description="强制刷新，忽略缓存"),
    db: Session = Depends(get_db),
):
    """对单簇触发/刷新 AI 研判，返回结构化 verdict。"""
    try:
        svc = AlertGroupTriageService(db)
        return await svc.triage_one(fingerprint, hours=hours, force_refresh=force_refresh)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"单簇研判失败: {str(e)}")


@router.post("/digest/generate")
async def generate_digest(
    hours: int = Query(24, ge=1, le=720, description="统计窗口(小时)"),
    db: Session = Depends(get_db),
):
    """手动生成一份告警摘要并落库（Phase 1：含 TopN 簇的 AI 研判）。"""
    try:
        svc = AlertDigestService(db)
        digest = await svc.generate(hours=hours)
        return digest.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成摘要失败: {str(e)}")


@router.get("/digest/latest")
async def get_digest_latest(db: Session = Depends(get_db)):
    """最近一条摘要。"""
    svc = AlertDigestService(db)
    d = svc.get_latest()
    if not d:
        raise HTTPException(status_code=404, detail="尚无摘要，请先 POST /alerts/digest/generate")
    return d.to_dict()


@router.get("/digest")
async def get_digest(
    date: Optional[str] = Query(None, description="按日期查询 YYYY-MM-DD（缺省取最新）"),
    db: Session = Depends(get_db),
):
    """按日期或最新取摘要。"""
    svc = AlertDigestService(db)
    try:
        d = svc.get_by_date(date) if date else svc.get_latest()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not d:
        raise HTTPException(status_code=404, detail="未找到摘要")
    return d.to_dict()
