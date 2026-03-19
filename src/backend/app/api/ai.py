"""
AI 分析 API (智谱AI集成)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.services.ai_analysis import AIAnalysisService
from app.models import AIAnalysis

router = APIRouter()


class AlertAnalysisRequest(BaseModel):
    """告警分析请求"""
    alert_id: str
    rule_id: Optional[int] = None
    rule_level: Optional[int] = None
    rule_description: Optional[str] = None
    full_log: Optional[str] = None
    agent_name: Optional[str] = None
    agent_ip: Optional[str] = None
    force_refresh: Optional[bool] = False


class LogExplainRequest(BaseModel):
    """日志解释请求"""
    log_content: str


@router.post("/analyze-alert")
async def analyze_alert(request: AlertAnalysisRequest, db: Session = Depends(get_db)):
    """使用 AI 分析告警"""
    try:
        ai_service = AIAnalysisService(db)

        # 调用AI分析
        analysis = ai_service.analyze_alert(
            alert_id=request.alert_id,
            rule_id=request.rule_id,
            rule_level=request.rule_level,
            rule_description=request.rule_description,
            full_log=request.full_log,
            agent_name=request.agent_name,
            agent_ip=request.agent_ip,
            force_refresh=request.force_refresh or False
        )

        return {
            "id": str(analysis.id),
            "alert_id": analysis.alert_id,
            "explanation": analysis.explanation,
            "risk_assessment": analysis.risk_assessment,
            "recommendations": analysis.recommendations,
            "model_name": analysis.model_name,
            "created_at": analysis.created_at,
            "expires_at": analysis.expires_at
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI分析失败: {str(e)}"
        )


@router.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    """获取 AI 分析结果"""
    import uuid

    try:
        analysis_uuid = uuid.UUID(analysis_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的分析ID格式")

    analysis = db.query(AIAnalysis).filter(
        AIAnalysis.id == analysis_uuid
    ).first()

    if not analysis:
        raise HTTPException(status_code=404, detail="分析结果不存在")

    return {
        "id": str(analysis.id),
        "alert_id": analysis.alert_id,
        "explanation": analysis.explanation,
        "risk_assessment": analysis.risk_assessment,
        "recommendations": analysis.recommendations,
        "model_name": analysis.model_name,
        "created_at": analysis.created_at,
        "expires_at": analysis.expires_at
    }


@router.post("/explain")
async def explain_log(request: LogExplainRequest, db: Session = Depends(get_db)):
    """自然语言解释日志"""
    try:
        ai_service = AIAnalysisService(db)
        result = ai_service.analyze_log(request.log_content)

        return {
            "log_content": request.log_content[:100] + "...",
            "explanation": result["explanation"]
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"日志解释失败: {str(e)}"
        )


@router.post("/analyze-alert/batch")
async def analyze_alerts_batch(
    alerts: list[AlertAnalysisRequest],
    db: Session = Depends(get_db)
):
    """批量分析告警"""
    try:
        ai_service = AIAnalysisService(db)
        results = []

        for alert_request in alerts:
            try:
                analysis = ai_service.analyze_alert(
                    alert_id=alert_request.alert_id,
                    rule_id=alert_request.rule_id,
                    rule_level=alert_request.rule_level,
                    rule_description=alert_request.rule_description,
                    full_log=alert_request.full_log,
                    agent_name=alert_request.agent_name,
                    agent_ip=alert_request.agent_ip
                )

                results.append({
                    "alert_id": alert_request.alert_id,
                    "status": "success",
                    "analysis_id": str(analysis.id),
                    "explanation": analysis.explanation
                })

            except Exception as e:
                results.append({
                    "alert_id": alert_request.alert_id,
                    "status": "failed",
                    "error": str(e)
                })

        return {
            "total": len(alerts),
            "success": sum(1 for r in results if r["status"] == "success"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"批量分析失败: {str(e)}"
        )
