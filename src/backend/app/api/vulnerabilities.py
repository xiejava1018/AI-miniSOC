"""
脆弱性管理 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from app.core.database import get_db
from app.models.vulnerability import Vulnerability, AssetVulnerability, ScanTask
from app.models.asset import Asset
from app.schemas.vulnerability import (
    VulnerabilityCreate, VulnerabilityUpdate, VulnerabilityResponse, VulnerabilityListResponse,
    AssetVulnerabilityCreate, AssetVulnerabilityUpdate, AssetVulnerabilityResponse, AssetVulnerabilityListResponse,
    ScanTaskCreate, ScanTaskUpdate, ScanTaskResponse, ScanTaskListResponse,
    VulnerabilityStats, AIVulnerabilitySuggestion
)
from app.schemas.vulnerability import (
    SeverityEnum,
    VulnerabilityStatusEnum,
    ScannerEnum,
    TaskStatusEnum,
    VulnerabilityTypeEnum  # 新增
)
from app.services.vulnerability_ai import VulnerabilityAIService
import uuid

router = APIRouter()


# ==================== 漏洞统计 ====================

@router.get("/stats/overview", response_model=VulnerabilityStats)
async def get_vulnerability_stats(
    db: Session = Depends(get_db)
):
    """获取CVE漏洞统计概览（仅SCAP类型）"""
    # 统计各严重程度的未修复漏洞数（仅SCAP类型）
    stats = db.query(
        AssetVulnerability.status,
        Vulnerability.severity,
        func.count(AssetVulnerability.id)
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN,
        Vulnerability.type == "scap"  # 只统计SCAP类型
    ).group_by(
        AssetVulnerability.status,
        Vulnerability.severity
    ).all()

    result = VulnerabilityStats()
    for status, severity, count in stats:
        if severity == SeverityEnum.CRITICAL:
            result.critical = count
        elif severity == SeverityEnum.HIGH:
            result.high = count
        elif severity == SeverityEnum.MEDIUM:
            result.medium = count
        elif severity == SeverityEnum.LOW:
            result.low = count

    result.total = result.critical + result.high + result.medium + result.low
    return result


@router.get("/stats/sca-overview")
async def get_sca_stats(
    db: Session = Depends(get_db)
):
    """获取配置检查统计概览（仅SCA类型）"""
    # 统计各严重程度的未修复配置检查数（仅SCA类型）
    stats = db.query(
        AssetVulnerability.status,
        Vulnerability.severity,
        func.count(AssetVulnerability.id)
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN,
        Vulnerability.type == "sca"  # 只统计SCA类型
    ).group_by(
        AssetVulnerability.status,
        Vulnerability.severity
    ).all()

    result = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "total": 0
    }
    for status, severity, count in stats:
        if severity == SeverityEnum.CRITICAL:
            result["critical"] = count
        elif severity == SeverityEnum.HIGH:
            result["high"] = count
        elif severity == SeverityEnum.MEDIUM:
            result["medium"] = count
        elif severity == SeverityEnum.LOW:
            result["low"] = count

    result["total"] = result["critical"] + result["high"] + result["medium"] + result["low"]
    return result


@router.get("/stats/trend")
async def get_vulnerability_trend(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
    db: Session = Depends(get_db)
):
    """获取脆弱性趋势数据（最近N天）"""
    from datetime import timedelta, date as date_class

    # 计算日期范围
    end_date = date_class.today()
    start_date = end_date - timedelta(days=days-1)

    # CVE趋势
    cve_trend = db.query(
        func.date(AssetVulnerability.detected_at).label('date'),
        func.count(AssetVulnerability.id).label('count')
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        Vulnerability.type == "scap",
        AssetVulnerability.detected_at >= start_date
    ).group_by(
        func.date(AssetVulnerability.detected_at)
    ).order_by(func.date(AssetVulnerability.detected_at)).all()

    # SCA趋势
    sca_trend = db.query(
        func.date(AssetVulnerability.detected_at).label('date'),
        func.count(AssetVulnerability.id).label('count')
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        Vulnerability.type == "sca",
        AssetVulnerability.detected_at >= start_date
    ).group_by(
        func.date(AssetVulnerability.detected_at)
    ).order_by(func.date(AssetVulnerability.detected_at)).all()

    # 计算当前总数和变化
    cve_current = db.query(AssetVulnerability).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        Vulnerability.type == "scap",
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).count()

    sca_current = db.query(AssetVulnerability).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        Vulnerability.type == "sca",
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).count()

    # 计算变化（简单对比今天和days天前的数量）
    cve_change = 0
    sca_change = 0

    if len(cve_trend) >= 2:
        first_count = cve_trend[0][1] if cve_trend[0] else 0
        last_count = cve_trend[-1][1] if cve_trend[-1] else 0
        cve_change = last_count - first_count

    if len(sca_trend) >= 2:
        first_count = sca_trend[0][1] if sca_trend[0] else 0
        last_count = sca_trend[-1][1] if sca_trend[-1] else 0
        sca_change = last_count - first_count

    # 计算变化百分比
    cve_change_percent = 0
    sca_change_percent = 0

    if cve_current > 0:
        cve_change_percent = round((cve_change / cve_current) * 100, 1)

    if sca_current > 0:
        sca_change_percent = round((sca_change / sca_current) * 100, 1)

    return {
        "cve": {
            "current": cve_current,
            "change": cve_change,
            "change_percent": cve_change_percent
        },
        "sca": {
            "current": sca_current,
            "change": sca_change,
            "change_percent": sca_change_percent
        }
    }


@router.get("/stats/top-assets")
async def get_top_risky_assets(
    limit: int = Query(5, ge=1, le=10, description="返回数量"),
    db: Session = Depends(get_db)
):
    """获取高风险资产排行"""
    from sqlalchemy import case, desc

    # 计算每个资产的风险分数
    # 严重: 10分, 高危: 5分, 中危: 2分, 低危: 1分
    risk_score = (
        func.sum(
            case(
                (Vulnerability.severity == SeverityEnum.CRITICAL, 10),
                (Vulnerability.severity == SeverityEnum.HIGH, 5),
                (Vulnerability.severity == SeverityEnum.MEDIUM, 2),
                (Vulnerability.severity == SeverityEnum.LOW, 1),
                else_=0
            )
        )
    )

    subquery = db.query(
        AssetVulnerability.asset_id,
        risk_score.label('risk_score')
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).group_by(
        AssetVulnerability.asset_id
    ).subquery()

    # 统计每个资产各级别数量
    asset_stats = db.query(
        Asset,
        func.sum(
            case(
                (Vulnerability.severity == SeverityEnum.CRITICAL, 1),
                else_=0
            )
        ).label('critical_count'),
        func.sum(
            case(
                (Vulnerability.severity == SeverityEnum.HIGH, 1),
                else_=0
            )
        ).label('high_count'),
        func.sum(
            case(
                (Vulnerability.severity == SeverityEnum.MEDIUM, 1),
                else_=0
            )
        ).label('medium_count')
    ).join(
        AssetVulnerability, Asset.id == AssetVulnerability.asset_id
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).filter(
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).group_by(
        Asset.id
    ).order_by(
        desc('critical_count'),
        desc('high_count'),
        desc('medium_count')
    ).limit(limit).all()

    result = []
    for rank, (asset, critical_count, high_count, medium_count) in enumerate(asset_stats, 1):
        result.append({
            "rank": rank,
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "asset_ip": asset.asset_ip,
            "critical_count": int(critical_count or 0),
            "high_count": int(high_count or 0),
            "medium_count": int(medium_count or 0)
        })

    return result


@router.get("/stats/recent")
async def get_recent_discoveries(
    vuln_type: str = Query(..., description="类型: cve或sca"),
    limit: int = Query(5, ge=1, le=10, description="返回数量"),
    db: Session = Depends(get_db)
):
    """获取最近发现的脆弱性"""
    # 验证类型参数
    if vuln_type not in ["cve", "sca"]:
        raise HTTPException(status_code=400, detail="类型参数必须是cve或sca")

    db_type = "scap" if vuln_type == "cve" else "sca"

    # 查询最近发现的脆弱性
    vulnerabilities = db.query(
        Vulnerability,
        Asset.name.label('asset_name'),
        Asset.asset_ip
    ).join(
        AssetVulnerability, Vulnerability.id == AssetVulnerability.vulnerability_id
    ).join(
        Asset, AssetVulnerability.asset_id == Asset.id
    ).filter(
        Vulnerability.type == db_type,
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).order_by(
        Vulnerability.discovered_at.desc()
    ).limit(limit).all()

    result = []
    for vuln, asset_name, asset_ip in vulnerabilities:
        result.append({
            "id": str(vuln.id),
            "cve_id": vuln.cve_id,
            "title": vuln.title,
            "severity": vuln.severity,
            "asset_name": asset_name or "Unknown",
            "asset_ip": asset_ip or "Unknown",
            "discovered_at": vuln.discovered_at.isoformat() if vuln.discovered_at else None
        })

    return result


@router.get("/stats/ai-suggestions", response_model=List[AIVulnerabilitySuggestion])
async def get_ai_suggestions(
    limit: int = Query(5, ge=1, le=10, description="返回数量"),
    min_severity: Optional[str] = Query(None, description="最低严重程度(critical/high/medium/low)"),
    db: Session = Depends(get_db)
):
    """获取AI优先修复建议（Top N）"""
    # 使用AI排序算法
    suggestions = VulnerabilityAIService.get_ai_suggestions(
        db=db,
        limit=limit,
        min_severity=min_severity
    )

    return suggestions


@router.get("/vulnerabilities/{vulnerability_id}/score-breakdown")
@router.get("/vulnerabilities/{vulnerability_id}/score-breakdown/")
async def get_vulnerability_score_breakdown(
    vulnerability_id: str,
    db: Session = Depends(get_db)
):
    """获取漏洞的AI评分分解详情"""
    try:
        vuln_id_uuid = uuid.UUID(vulnerability_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的漏洞ID格式")

    breakdown = VulnerabilityAIService.get_score_breakdown(
        db=db,
        vulnerability_id=vuln_id_uuid
    )

    if not breakdown:
        raise HTTPException(status_code=404, detail="漏洞不存在或没有未修复的资产")

    return breakdown


# ==================== 漏洞基础 CRUD ====================

@router.get("/vulnerabilities", response_model=VulnerabilityListResponse)
@router.get("/vulnerabilities/", response_model=VulnerabilityListResponse)
async def list_vulnerabilities(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    type: Optional[VulnerabilityTypeEnum] = Query(None, description="脆弱性类型: sca或scap"),
    severity: Optional[SeverityEnum] = None,
    scanner: Optional[ScannerEnum] = None,
    status: Optional[VulnerabilityStatusEnum] = None,
    search: Optional[str] = Query(None, description="搜索CVE、标题"),
    db: Session = Depends(get_db)
):
    """获取漏洞列表"""
    query = db.query(Vulnerability).distinct()

    # 关联asset_vulnerabilities用于筛选
    if scanner or status:
        query = query.join(AssetVulnerability)

    # 筛选条件
    if type:
        query = query.filter(Vulnerability.type == type)
    if severity:
        query = query.filter(Vulnerability.severity == severity)
    if scanner:
        query = query.filter(AssetVulnerability.scanner == scanner)
    if status:
        query = query.filter(AssetVulnerability.status == status)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Vulnerability.cve_id.ilike(search_pattern)) |
            (Vulnerability.title.ilike(search_pattern))
        )

    # 总数
    total = query.count()

    # 分页
    vulnerabilities = query.offset(skip).limit(limit).all()

    # 批量计算受影响资产数 + AI风险评分（取关联资产中的最高分，与 score-breakdown 口径一致）
    vuln_ids = [v.id for v in vulnerabilities]
    asset_rows = []
    if vuln_ids:
        asset_rows = db.query(
            AssetVulnerability.vulnerability_id,
            Vulnerability.cvss_score,
            Vulnerability.has_exploit,
            Asset.criticality,
            Asset.exposure_level
        ).join(
            Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
        ).join(
            Asset, AssetVulnerability.asset_id == Asset.id
        ).filter(
            AssetVulnerability.vulnerability_id.in_(vuln_ids),
            AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
        ).all()

    asset_count_map: dict = {}
    risk_score_map: dict = {}
    for row in asset_rows:
        vid = row.vulnerability_id
        asset_count_map[vid] = asset_count_map.get(vid, 0) + 1
        score = VulnerabilityAIService.calculate_risk_score(
            cvss_score=float(row.cvss_score) if row.cvss_score else 0.0,
            asset_criticality=row.criticality or 'medium',
            exposure_level=row.exposure_level or 'internal',
            has_exploit=row.has_exploit or False
        )
        if vid not in risk_score_map or score > risk_score_map[vid]:
            risk_score_map[vid] = score

    items = [
        VulnerabilityResponse(
            id=str(v.id),
            type=v.type,
            cve_id=v.cve_id,
            title=v.title,
            description=v.description,
            cvss_score=float(v.cvss_score) if v.cvss_score else None,
            cvss_vector=v.cvss_vector,
            severity=v.severity,
            affected_packages=v.affected_packages,
            fix_suggestion=v.fix_suggestion,
            references=v.references,
            published_date=v.published_date,
            has_exploit=v.has_exploit,
            discovered_at=v.discovered_at,
            updated_at=v.updated_at,
            affected_asset_count=asset_count_map.get(v.id, 0),
            risk_score=risk_score_map.get(v.id)
        ) for v in vulnerabilities
    ]

    return VulnerabilityListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/vulnerabilities/{vulnerability_id}", response_model=VulnerabilityResponse)
@router.get("/vulnerabilities/{vulnerability_id}/", response_model=VulnerabilityResponse)
async def get_vulnerability(
    vulnerability_id: str,
    db: Session = Depends(get_db)
):
    """获取漏洞详情"""
    try:
        vuln_id_uuid = uuid.UUID(vulnerability_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的漏洞ID格式")

    vulnerability = db.query(Vulnerability).filter(Vulnerability.id == vuln_id_uuid).first()

    if not vulnerability:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    return VulnerabilityResponse(
        id=str(vulnerability.id),
        type=vulnerability.type,  # C4 修复（评审 §14.3）：原先漏传 → SCA 漏洞被误标为默认 'scap'
        cve_id=vulnerability.cve_id,
        title=vulnerability.title,
        description=vulnerability.description,
        cvss_score=float(vulnerability.cvss_score) if vulnerability.cvss_score else None,
        cvss_vector=vulnerability.cvss_vector,
        severity=vulnerability.severity,
        affected_packages=vulnerability.affected_packages,
        fix_suggestion=vulnerability.fix_suggestion,
        references=vulnerability.references,
        published_date=vulnerability.published_date,
        has_exploit=vulnerability.has_exploit,
        discovered_at=vulnerability.discovered_at,
        updated_at=vulnerability.updated_at
    )


# ==================== 资产-漏洞关联 ====================

@router.get("/asset-vulnerabilities", response_model=AssetVulnerabilityListResponse)
@router.get("/asset-vulnerabilities/", response_model=AssetVulnerabilityListResponse)
async def list_asset_vulnerabilities(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    asset_id: Optional[str] = None,
    vulnerability_id: Optional[str] = Query(None, description="按漏洞定义过滤（T11 详情弹窗用）"),
    severity: Optional[SeverityEnum] = None,
    status: Optional[VulnerabilityStatusEnum] = None,
    scanner: Optional[ScannerEnum] = None,
    vuln_type: Optional[VulnerabilityTypeEnum] = Query(None, description="按漏洞类型过滤(scap=CVE漏洞/sca=基线)，与 scanner 正交"),
    db: Session = Depends(get_db)
):
    """获取资产-漏洞关联列表（含 SLA 状态，运行时计算）"""
    query = db.query(
        AssetVulnerability,
        Vulnerability,
        Asset
    ).join(
        Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id
    ).join(
        Asset, AssetVulnerability.asset_id == Asset.id
    )

    # 筛选条件
    if asset_id:
        try:
            asset_id_uuid = uuid.UUID(asset_id)
            query = query.filter(AssetVulnerability.asset_id == asset_id_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的资产ID格式")

    if vulnerability_id:
        try:
            vuln_id_uuid = uuid.UUID(vulnerability_id)
            query = query.filter(AssetVulnerability.vulnerability_id == vuln_id_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的漏洞ID格式")

    if severity:
        query = query.filter(Vulnerability.severity == severity)
    if status:
        query = query.filter(AssetVulnerability.status == status)
    if scanner:
        query = query.filter(AssetVulnerability.scanner == scanner)
    if vuln_type:
        query = query.filter(Vulnerability.type == vuln_type)

    # 总数
    total = query.count()

    # 分页
    results = query.offset(skip).limit(limit).all()

    items = []
    for av, vuln, asset in results:
        # M1/T4：AI 风险评分（与主列表同口径：calculate_risk_score + 资产关键度/暴露面）
        risk_score = None
        if vuln.cvss_score is not None:
            risk_score = VulnerabilityAIService.calculate_risk_score(
                cvss_score=float(vuln.cvss_score) if vuln.cvss_score else 0.0,
                asset_criticality=asset.criticality or 'medium',
                exposure_level=asset.exposure_level or 'internal',
                has_exploit=bool(vuln.has_exploit)
            )
        items.append({
            "id": str(av.id),
            "asset_id": str(av.asset_id),
            "asset_name": asset.name,
            "asset_ip": asset.asset_ip,
            "vulnerability_id": str(av.vulnerability_id),
            "cve_id": vuln.cve_id,
            "title": vuln.title,
            "severity": vuln.severity,
            "cvss_score": float(vuln.cvss_score) if vuln.cvss_score else None,
            "status": av.status,
            "scanner": av.scanner,
            "detected_at": av.detected_at,
            "fixed_at": av.fixed_at,
            # T11：SLA（运行时计算，不落库）
            "due_date": av.due_date,
            "sla_status": AssetVulnerability.sla_status_of(av.status, av.due_date),
            # M1/T4：AI 风险评分
            "risk_score": risk_score,
            # M2/T5：基线展示字段（SCA 检查项专用，SCAP 为 None）
            "fix_suggestion": vuln.fix_suggestion,
        })

    return AssetVulnerabilityListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.patch("/asset-vulnerabilities/{av_id}/status")
@router.patch("/asset-vulnerabilities/{av_id}/status/")
async def update_asset_vulnerability_status(
    av_id: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """更新漏洞状态

    C1 修复（评审 §14.3）：改收 JSON body {status, notes?}，
    与前端 request.patch 对齐（原先 Query 收参 + 前端 PUT 双重不匹配）。
    """
    from app.schemas.vulnerability import VulnerabilityStatusEnum as VSE

    try:
        av_id_uuid = uuid.UUID(av_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的关联ID格式")

    raw_status = payload.get("status")
    try:
        status = VSE(str(raw_status).lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效状态: {raw_status}（合法: open/in_progress/fixed）",
        )
    notes = payload.get("notes")

    av = db.query(AssetVulnerability).filter(AssetVulnerability.id == av_id_uuid).first()

    if not av:
        raise HTTPException(status_code=404, detail="资产-漏洞关联不存在")

    av.status = status
    if status == VSE.FIXED:
        av.fixed_at = func.now()
    if notes:
        av.notes = notes

    db.commit()
    db.refresh(av)

    return {"message": "状态更新成功", "status": status.value}


@router.post("/asset-vulnerabilities/{av_id}/create-incident")
async def create_incident_from_vulnerability(
    av_id: str,
    db: Session = Depends(get_db)
):
    """漏洞→事件：一键生成安全事件（T11 / Phase 4.1，仅手动触发）

    复用 alert_incident_service 的 _persist_incident 范式：
    - 标题 = CVE + 资产；severity 由漏洞 severity 直接映射；
    - 资产关联走 AssetIncident（asset_ids），描述内嵌 CVE / av_id，零 schema 变更（§14.5-4）。
    """
    from app.services.alert_incident_service import build_incident_from_vulnerability, incident_to_dict

    try:
        av_id_uuid = uuid.UUID(av_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的关联ID格式")

    try:
        incident = build_incident_from_vulnerability(db, av_id_uuid, created_by="vulnerability-console")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "message": "事件创建成功",
        "incident": incident_to_dict(incident),
    }


# ==================== 扫描任务 ====================

@router.post("/scan-tasks", response_model=ScanTaskResponse)
async def create_scan_task(
    task: ScanTaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """创建扫描任务（T9 / 决策4："Wazuh 持续扫描"的手动重评估封装）

    定位：Wazuh（SCAP+SCA）已是持续扫描源，本接口 = 按需立即触发一次
    重新拉取 + 落库，不重复造扫描引擎；OpenVAS 深度扫描属 P2/P5 增强，
    不在本期（task_type 收敛为 wazuh_scap / wazuh_sca / manual）。
    """
    if task.task_type not in ("wazuh_scap", "wazuh_sca", "manual"):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 task_type: {task.task_type}（合法: wazuh_scap/wazuh_sca/manual）",
        )

    scan_task = ScanTask(
        task_type=task.task_type,
        name=task.name,
        target_assets=task.target_assets,
        scan_config=task.scan_config,
        status=TaskStatusEnum.PENDING
    )

    db.add(scan_task)
    db.commit()
    db.refresh(scan_task)

    # T9：真实后台执行（原 TODO）——重评估 + 进度/结果回写
    background_tasks.add_task(_execute_scan_task, str(scan_task.id), task.task_type)

    return ScanTaskResponse(
        id=str(scan_task.id),
        task_type=scan_task.task_type,
        name=scan_task.name,
        target_assets=scan_task.target_assets,
        scan_config=scan_task.scan_config,
        status=scan_task.status,
        progress=scan_task.progress,
        result_summary=scan_task.result_summary,
        error_message=scan_task.error_message,
        created_by=str(scan_task.created_by) if scan_task.created_by else None,
        created_at=scan_task.created_at,
        started_at=scan_task.started_at,
        completed_at=scan_task.completed_at
    )


def _execute_scan_task(task_id: str, task_type: str):
    """后台执行扫描任务（BackgroundTasks 线程）：拉取 → 回写状态/进度/结果

    注意：BackgroundTasks 的函数运行在独立线程，需自建 DB 会话；
    每阶段（SCAP / SCA / KEV）完成后回写一次进度，便于前端轮询观感。
    """
    import logging as _logging
    from datetime import datetime as _dt
    from app.core.database import SessionLocal

    _logger = _logging.getLogger(__name__)
    db = SessionLocal()
    try:
        t = db.query(ScanTask).filter(ScanTask.id == uuid.UUID(task_id)).first()
        if not t:
            return
        t.status = TaskStatusEnum.RUNNING
        t.started_at = _dt.utcnow()
        t.progress = 5
        db.commit()

        result_summary = {}

        # 阶段 1：SCAP（OpenSearch 源重评估）
        if task_type in ("wazuh_scap", "manual"):
            from app.services.opensearch_scap_sync import OpenSearchSCAPSyncService
            stats = OpenSearchSCAPSyncService.sync_all_vulnerabilities(db, limit=1000)
            result_summary["scap"] = stats
            t.progress = 50
            db.commit()

        # 阶段 2：SCA（Wazuh API /sca 重评估）
        if task_type in ("wazuh_sca", "manual"):
            from app.services.wazuh_sca_sync import WazuhSCASyncService
            stats = WazuhSCASyncService.sync_all_sca_checks(db, limit=1000)
            result_summary["sca"] = stats
            t.progress = 80
            db.commit()

        # 阶段 3：KEV 富化
        try:
            from app.services.cisa_kev_service import CisaKevService
            result_summary["kev_enriched"] = CisaKevService.enrich_has_exploit(db)
        except Exception as e:
            result_summary["kev_enriched"] = f"error: {e}"

        t.result_summary = result_summary
        t.status = TaskStatusEnum.COMPLETED
        t.progress = 100
        t.completed_at = _dt.utcnow()
        db.commit()
        _logger.info("scan task %s completed: %s", task_id, result_summary)
    except Exception as e:
        db.rollback()
        t = db.query(ScanTask).filter(ScanTask.id == uuid.UUID(task_id)).first()
        if t:
            t.status = TaskStatusEnum.FAILED
            t.error_message = str(e)[:2000]
            t.completed_at = _dt.utcnow()
            db.commit()
        _logger.error("scan task %s failed: %s", task_id, e)
    finally:
        db.close()


@router.get("/scan-tasks", response_model=ScanTaskListResponse)
@router.get("/scan-tasks/", response_model=ScanTaskListResponse)
async def list_scan_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[TaskStatusEnum] = None,
    task_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取扫描任务列表"""
    query = db.query(ScanTask)

    if status:
        query = query.filter(ScanTask.status == status)
    if task_type:
        query = query.filter(ScanTask.task_type == task_type)

    total = query.count()
    tasks = query.order_by(ScanTask.created_at.desc()).offset(skip).limit(limit).all()

    items = [
        ScanTaskResponse(
            id=str(task.id),
            task_type=task.task_type,
            name=task.name,
            target_assets=task.target_assets,
            scan_config=task.scan_config,
            status=task.status,
            progress=task.progress,
            result_summary=task.result_summary,
            error_message=task.error_message,
            created_by=str(task.created_by) if task.created_by else None,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at
        ) for task in tasks
    ]

    return ScanTaskListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/scan-tasks/{task_id}", response_model=ScanTaskResponse)
@router.get("/scan-tasks/{task_id}/", response_model=ScanTaskResponse)
async def get_scan_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """获取扫描任务详情"""
    try:
        task_id_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的任务ID格式")

    task = db.query(ScanTask).filter(ScanTask.id == task_id_uuid).first()

    if not task:
        raise HTTPException(status_code=404, detail="扫描任务不存在")

    return ScanTaskResponse(
        id=str(task.id),
        task_type=task.task_type,
        name=task.name,
        target_assets=task.target_assets,
        scan_config=task.scan_config,
        status=task.status,
        progress=task.progress,
        result_summary=task.result_summary,
        error_message=task.error_message,
        created_by=str(task.created_by) if task.created_by else None,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at
    )


@router.post("/scan-tasks/{task_id}/cancel")
@router.post("/scan-tasks/{task_id}/cancel/")
async def cancel_scan_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """取消扫描任务"""
    try:
        task_id_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的任务ID格式")

    task = db.query(ScanTask).filter(ScanTask.id == task_id_uuid).first()

    if not task:
        raise HTTPException(status_code=404, detail="扫描任务不存在")

    if task.status not in [TaskStatusEnum.PENDING, TaskStatusEnum.RUNNING]:
        raise HTTPException(status_code=400, detail="只能取消待执行或运行中的任务")

    task.status = TaskStatusEnum.CANCELLED
    db.commit()

    return {"message": "任务已取消"}


# ==================== Wazuh / OpenSearch SCAP 同步 ====================

@router.post("/sync/wazuh")
async def sync_wazuh_vulnerabilities(
    limit: int = Query(1000, ge=1, le=10000, description="同步数量限制"),
    use_mock: bool = Query(False, description="使用模拟数据（测试用）"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """同步 SCAP（CVE）漏洞数据

    T5（2026-08-15）：真实数据源由 Wazuh API 改为 OpenSearch
    `wazuh-states-vulnerabilities-*`（POC-1 证实 Wazuh API /vulnerability 全 404）。
    同步完成后自动触发 CISA KEV 存量富化（T6）。
    """
    from app.services.opensearch_scap_sync import OpenSearchSCAPSyncService
    from app.services.cisa_kev_service import CisaKevService

    try:
        stats = OpenSearchSCAPSyncService.sync_all_vulnerabilities(
            db=db, limit=limit, use_mock=use_mock
        )
        # T6：同步后富化在野利用标记（真实分支才有意义；mock 数据自带 has_exploit）
        if not use_mock:
            try:
                stats["kev_enriched"] = CisaKevService.enrich_has_exploit(db)
            except Exception as e:
                stats["kev_enriched"] = f"error: {e}"

        return {
            "message": "同步完成" if not use_mock else "模拟数据同步完成",
            "mode": "mock" if use_mock else "production",
            "source": "opensearch:wazuh-states-vulnerabilities",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"同步失败: {str(e)}"
        )


@router.get("/sync/wazuh/status")
@router.get("/sync/wazuh/status/")
async def get_wazuh_sync_status(
    db: Session = Depends(get_db)
):
    """获取SCAP同步状态"""
    from app.services.wazuh_scap_sync import WazuhSCAPSyncService

    status = WazuhSCAPSyncService.get_sync_status(db=db)

    return status


@router.post("/sync/wazuh/agents/{agent_id}")
async def sync_agent_vulnerabilities(
    agent_id: str,
    limit: int = Query(500, ge=1, le=5000, description="同步数量限制"),
    db: Session = Depends(get_db)
):
    """同步单个Agent的SCAP漏洞数据（T5：OpenSearch 源）"""
    from app.services.opensearch_scap_sync import OpenSearchSCAPSyncService

    try:
        stats = OpenSearchSCAPSyncService.sync_agent_vulnerabilities(
            db=db,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "message": f"Agent {agent_id} 同步完成",
            "agent_id": agent_id,
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"同步失败: {str(e)}"
        )


# ==================== CISA KEV 同步（T6，决策2） ====================

@router.post("/sync/kev")
async def sync_cisa_kev(
    db: Session = Depends(get_db)
):
    """手动触发 CISA KEV 目录同步 + 存量 has_exploit 富化"""
    from app.services.cisa_kev_service import CisaKevService

    try:
        result = CisaKevService.sync_kev(db)
        result["enriched"] = CisaKevService.enrich_has_exploit(db)
        return {"message": "CISA KEV 同步完成", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KEV 同步失败: {str(e)}")


@router.get("/stats/exploit")
async def get_exploit_stats(
    db: Session = Depends(get_db)
):
    """在野利用（KEV）统计：目录规模 / 命中漏洞 / 影响资产关联 / 勒索相关"""
    from app.models.cisa_kev import CisaKev

    kev_total = db.query(CisaKev).count()
    kev_ransom = db.query(CisaKev).filter(CisaKev.known_ransomware.is_(True)).count()

    hit_vulns = db.query(Vulnerability).filter(Vulnerability.has_exploit.is_(True)).count()

    from app.models.vulnerability import AssetVulnerability as AV
    hit_open_assocs = (
        db.query(AV)
        .join(Vulnerability, AV.vulnerability_id == Vulnerability.id)
        .filter(Vulnerability.has_exploit.is_(True), AV.status == "open")
        .count()
    )

    return {
        "kev_catalog_total": kev_total,
        "kev_ransomware_related": kev_ransom,
        "vulnerabilities_with_exploit": hit_vulns,
        "open_associations_with_exploit": hit_open_assocs,
    }



# ==================== Wazuh SCA 同步 ====================

@router.post("/sync/wazuh/sca")
async def sync_wazuh_sca_checks(
    limit: int = Query(1000, ge=1, le=10000, description="同步数量限制"),
    db: Session = Depends(get_db)
):
    """同步Wazuh SCA配置检查数据"""
    from app.services.wazuh_sca_sync import WazuhSCASyncService

    try:
        stats = WazuhSCASyncService.sync_all_sca_checks(
            db=db,
            limit=limit
        )

        return {
            "message": "SCA配置检查同步完成",
            "type": "sca",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SCA同步失败: {str(e)}"
        )


@router.post("/sync/wazuh/sca/agents/{agent_id}")
async def sync_agent_sca_checks(
    agent_id: str,
    limit: int = Query(500, ge=1, le=5000, description="同步数量限制"),
    db: Session = Depends(get_db)
):
    """同步单个Agent的SCA配置检查数据"""
    from app.services.wazuh_sca_sync import WazuhSCASyncService
    from app.services.wazuh_client import wazuh_client

    try:
        # 获取agent信息
        agent_info = wazuh_client.get_agent_info(agent_id)
        agent_name = agent_info.get("name", agent_id)
        agent_ip = agent_info.get("ip", "")

        stats = WazuhSCASyncService.sync_agent_sca_checks(
            db=db,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_ip=agent_ip,
            limit=limit
        )

        return {
            "message": f"Agent {agent_name} SCA配置检查同步完成",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "type": "sca",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SCA同步失败: {str(e)}"
        )


@router.get("/stats/by-type")
async def get_stats_by_type(
    db: Session = Depends(get_db)
):
    """按类型获取脆弱性统计"""
    from sqlalchemy import func
    
    # 统计SCA和CVE的数量
    stats = db.query(
        Vulnerability.type,
        Vulnerability.severity,
        func.count(Vulnerability.id).label("count")
    ).join(
        AssetVulnerability, Vulnerability.id == AssetVulnerability.vulnerability_id
    ).filter(
        AssetVulnerability.status == VulnerabilityStatusEnum.OPEN
    ).group_by(
        Vulnerability.type,
        Vulnerability.severity
    ).all()
    
    # 整理结果
    result = {
        "sca": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0
        },
        "scap": {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0
        }
    }
    
    for vuln_type, severity, count in stats:
        if vuln_type in result:
            result[vuln_type][severity] = count
            result[vuln_type]["total"] += count
    
    return result
