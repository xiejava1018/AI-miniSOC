"""业务系统 CRUD + 资产关联 API

详见 docs/design/2026-09-13-资产知识图谱研究与实施方案.md §7.0 WO-0a、§7.2.5 F9：
补齐 §6 的"图构建"工程闭环之外的组织数据入口（业务系统 / 负责人 / 部门）。

端点列表（统一前缀 /api/v1/business-systems）：
- GET    /                       列表（分页 + name/code 模糊）
- POST   /                       新建（admin only）
- GET    /{id}                   详情
- PUT    /{id}                   更新（admin only）
- DELETE /{id}                   删除（admin only）
- GET    /{id}/assets            业务系统下的资产列表
- POST   /assets/{asset_id}/systems 为某资产添加一个业务系统关联（admin only）
- DELETE /assets/{asset_id}/systems/{system_id} 移除关联（admin only）

写操作（POST/PUT/DELETE）通过 require_admin 限制；读端点 login 即可。
审计：使用 @log_audit，所有写操作进 soc_audit_logs（hash 链保护）。
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin, require_role
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.business_system import (
    BusinessSystemCreate,
    BusinessSystemUpdate,
    BusinessSystemResponse,
    BusinessSystemListResponse,
    AssetBusinessLinkCreate,
    AssetBusinessLinkResponse,
    AssetBusinessRoleUpdate,
)
from app.models.business_system import BusinessSystem, AssetBusiness
from app.models.asset import Asset

router = APIRouter(tags=["业务系统管理"])


# ----------------------- 定级建议（S4 Phase 0 · 设计 §6）-----------------------
# 注意：本组路由必须在 GET /{system_id} 之前注册——FastAPI 按注册序匹配，
# 否则 "suggest-protection-level" / "coverage-kpi" 会被 /{system_id} 当 UUID 参数捕获 → 422。


@router.post("/{system_id}/suggest-protection-level", response_model=BusinessSystemResponse)
@log_audit(
    action="SUGGEST",
    resource_type="business_system",
    get_resource_id=lambda result, kwargs: kwargs.get('system_id'),
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
)
async def suggest_protection_level(
    request: Request,
    system_id: str,
    current_user: UserResponseSchema = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    """运行定级建议引擎（OH-4.4a · 设计 §6.3）

    S4 红线：只写 suggested_protection_level + suggestion_basis，
    **永不写 protection_level**——采纳须走 PUT（显式人工确认，触发传播）。
    confirmed 状态允许重算建议（供复核）但不改状态——人工结论优先。
    """
    from app.services.protection_level_suggest import suggest, collect_evidence
    b = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    evidence = collect_evidence(db, system_id)
    basis = suggest(
        business_impact=b.business_impact,
        data_sensitivity=b.data_sensitivity,
        evidence=evidence,
    )
    b.suggested_protection_level = basis["suggested_level"]
    b.suggestion_basis = basis
    if b.rating_status == "unrated":
        b.rating_status = "suggested"
    db.commit()
    db.refresh(b)
    return _to_response(b)


@router.get("/coverage-kpi")
async def get_coverage_kpi(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """绑定覆盖率 KPI（设计 §7 T7 · 北极星 H1「关联资产覆盖率 ≥60%」度量）

    服务端聚合（CLAUDE.md §4.2 教训：禁止取 N 条客户端分桶）。
    coverage_rate = 挂 ≥1 业务系统的资产数 / 总资产数（百分比，1 位小数）。
    """
    from app.models.asset import Asset
    total_assets = db.query(func.count(Asset.id)).scalar() or 0
    linked_assets = (
        db.query(func.count(func.distinct(AssetBusiness.asset_id))).scalar() or 0
    )
    systems_count = db.query(func.count(BusinessSystem.id)).scalar() or 0
    unrated = db.query(func.count(BusinessSystem.id)) \
        .filter(BusinessSystem.rating_status == "unrated").scalar() or 0
    suggested_pending = db.query(func.count(BusinessSystem.id)) \
        .filter(BusinessSystem.rating_status == "suggested").scalar() or 0
    coverage = round(linked_assets * 100.0 / total_assets, 1) if total_assets else 0.0
    return {
        "total_assets": int(total_assets),
        "linked_assets": int(linked_assets),
        "coverage_rate": coverage,
        "systems_count": int(systems_count),
        "unrated": int(unrated),
        "suggested_pending": int(suggested_pending),
    }


@router.get("/rating-audit")
async def get_rating_audit(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """S4 定级稽核总览（OH-4.12）：状态分布 + 发现列表 + 建议覆盖率 KPI。

    红线：系统只建议不裁决，本端点只读。
    """
    from app.services.rating_audit import audit
    return audit(db)


@router.get("/{system_id}/rating-gap")
async def get_rating_gap(
    system_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """单系统定级差距分析（OH-4.12）：确认 vs 建议 vs 成员等级分布。"""
    from app.services.rating_audit import gap_analysis
    try:
        return gap_analysis(db, system_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


# ----------------------- 业务系统 CRUD -----------------------


def _to_response(b: BusinessSystem, asset_count: int = 0,
                 department_name: Optional[str] = None) -> BusinessSystemResponse:
    """BusinessSystem ORM → Response（手填 asset_count 避免 N+1；
    department_name 优先用传入值（list 批量查询），未传则从 relationship 懒加载取）"""
    from app.core.criticality import legacy_criticality_from_data_sensitivity
    if department_name is None and getattr(b, "department", None) is not None:
        department_name = b.department.name
    return BusinessSystemResponse(
        id=str(b.id),
        code=b.code,
        name=b.name,
        # === 治本方案三维度 ===
        business_impact=b.business_impact or "normal",
        data_sensitivity=b.data_sensitivity or "medium",
        protection_level=b.protection_level or "level_2",
        # 定级备案 S4 Phase 0（设计 §4.2）
        suggested_protection_level=b.suggested_protection_level,
        suggestion_basis=b.suggestion_basis if isinstance(b.suggestion_basis, dict) else None,
        rating_status=b.rating_status or "unrated",
        rating_confirmed_by=b.rating_confirmed_by,
        rating_confirmed_at=b.rating_confirmed_at,
        # criticality：兼容垫片（从 data_sensitivity 派生）
        criticality=b.criticality or legacy_criticality_from_data_sensitivity(b.data_sensitivity),
        owner=b.owner,
        owner_contact=b.owner_contact,
        owner_id=b.owner_id,
        department_id=b.department_id,
        department_name=department_name,
        description=b.description,
        asset_count=asset_count,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


@router.get("", response_model=BusinessSystemListResponse)
async def list_business_systems(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="按 name/code 模糊匹配"),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列表查询：所有登录用户可读（基础治理数据，非敏感）"""
    q = db.query(BusinessSystem)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(BusinessSystem.name.ilike(like), BusinessSystem.code.ilike(like)))
    total = q.count()
    # 排序修复（设计 §7 T1）：原 criticality.asc() 是字符串字母序（critical<high<low<medium，
    # medium 排到 low 后）且字段已 deprecated。改为等保等级档位序（level_5 在前）+ 名称序。
    from sqlalchemy import case
    pl_order = case(
        {level: idx for idx, level in enumerate(
            ("level_5", "level_4", "level_3", "level_2", "level_1"), start=1)},
        value=BusinessSystem.protection_level,
    )
    rows = q.order_by(pl_order.asc(), BusinessSystem.name.asc()) \
            .offset((page - 1) * page_size).limit(page_size).all()

    # 批量拿关联资产数（一次性 group_by 防 N+1）
    ids = [b.id for b in rows]
    counts = {}
    if ids:
        cnt_rows = db.query(AssetBusiness.system_id, func.count(AssetBusiness.asset_id)) \
                     .filter(AssetBusiness.system_id.in_(ids)) \
                     .group_by(AssetBusiness.system_id).all()
        counts = {sid: c for sid, c in cnt_rows}

    # 批量拿部门名（一次性查询防 N+1）
    dept_ids = {b.department_id for b in rows if b.department_id}
    dept_names = {}
    if dept_ids:
        from app.models.department import Department
        dept_rows = db.query(Department.id, Department.name) \
                      .filter(Department.id.in_(dept_ids)).all()
        dept_names = {did: dname for did, dname in dept_rows}

    return BusinessSystemListResponse(
        total=total,
        items=[_to_response(b, counts.get(b.id, 0),
                            department_name=dept_names.get(b.department_id)) for b in rows],
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=BusinessSystemResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="business_system",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def create_business_system(
    request: Request,
    data: BusinessSystemCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """新建业务系统（admin only）"""
    # code 全局唯一
    if db.query(BusinessSystem).filter(BusinessSystem.code == data.code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"code '{data.code}' 已存在")
    b = BusinessSystem(
        code=data.code,
        name=data.name,
        # === 治本方案三维度 ===
        business_impact=data.business_impact,
        data_sensitivity=data.data_sensitivity,
        protection_level=data.protection_level,
        # criticality：deprecated 兼容垫片（从 data_sensitivity 派生写入供旧读路径访问）
        criticality=None,  # 下面根据 data_sensitivity 推
        owner=data.owner,
        owner_contact=data.owner_contact,
        owner_id=data.owner_id,
        department_id=data.department_id,
        description=data.description,
    )
    from app.core.criticality import legacy_criticality_from_data_sensitivity
    b.criticality = legacy_criticality_from_data_sensitivity(b.data_sensitivity)
    db.add(b)
    db.commit()
    db.refresh(b)
    return _to_response(b)


@router.get("/{system_id}", response_model=BusinessSystemResponse)
async def get_business_system(
    system_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """业务系统详情"""
    b = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    cnt = db.query(func.count(AssetBusiness.asset_id)) \
            .filter(AssetBusiness.system_id == system_id).scalar() or 0
    return _to_response(b, cnt)


@router.put("/{system_id}", response_model=BusinessSystemResponse)
@log_audit(
    action="UPDATE",
    resource_type="business_system",
    get_resource_id=lambda result, kwargs: str(result.id) if hasattr(result, 'id') else kwargs.get('system_id'),
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def update_business_system(
    request: Request,
    system_id: str,
    data: BusinessSystemUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """更新业务系统（admin only）

    设计 §5.2 T4：protection_level 值有实质变化 →
      ① rating_status='confirmed' + 确认人/时间（D6 确认动作显式化）
      ② propagate_system_level_change 就高联动成员资产（D4：manual 资产跳过）
    """
    b = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    payload = data.model_dump(exclude_unset=True)
    if "code" in payload and payload["code"] and payload["code"] != b.code:
        if db.query(BusinessSystem).filter(BusinessSystem.code == payload["code"],
                                           BusinessSystem.id != system_id).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"code '{payload['code']}' 已被占用")
    # criticality 不再独立写：跟 data_sensitivity 保持一致（兼容垫片）
    payload.pop("criticality", None)

    # 定级确认检测（值有变才触发——与 §5.3 v2 资产侧语义对称）
    pl_changed = (
        "protection_level" in payload
        and payload["protection_level"] is not None
        and payload["protection_level"] != b.protection_level
    )

    for k, v in payload.items():
        setattr(b, k, v)
    if pl_changed:
        from datetime import datetime, timezone
        b.rating_status = "confirmed"
        b.rating_confirmed_by = getattr(current_user, "username", None) or "admin"
        b.rating_confirmed_at = datetime.now(timezone.utc)
    # 重同步 criticality（与新 data_sensitivity 一致）
    from app.core.criticality import legacy_criticality_from_data_sensitivity
    b.criticality = legacy_criticality_from_data_sensitivity(b.data_sensitivity)
    db.flush()

    # 就高传播（设计 §5.2）：与更新同事务；manual 资产在引擎内跳过
    if pl_changed:
        from app.services.protection_level_propagation import (
            propagate_system_level_change, log_propagation_audit,
        )
        prop_summary = propagate_system_level_change(db, system_id)
        log_propagation_audit(db, action="UPDATE", system_id=system_id,
                              current_user=current_user, result=prop_summary)
    db.commit()
    db.refresh(b)
    return _to_response(b)


@router.delete("/{system_id}")
@log_audit(
    action="DELETE",
    resource_type="business_system",
    get_resource_id=lambda result, kwargs: kwargs.get('system_id'),
    get_resource_name=lambda result, kwargs: result.get('name') if isinstance(result, dict) else None,
)
async def delete_business_system(
    request: Request,
    system_id: str,
    force: bool = Query(False, description="成员资产 >0 时必须 force=true 才能删除（D9 防护）"),
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """删除业务系统（admin only）

    D9 防护：有关联资产时需显式 force=true；删除流程 =
      解绑全部 → 逐资产按 D4 重算等级（inherited 值保留转 manual）→ 删系统。
    """
    from app.services.protection_level_propagation import recompute_asset, log_propagation_audit
    b = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    name = b.name
    member_ids = [r[0] for r in db.query(AssetBusiness.asset_id)
                  .filter(AssetBusiness.system_id == system_id).all()]
    if member_ids and not force:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"业务系统 '{name}' 下有 {len(member_ids)} 个资产关联。"
                   f"删除将解除全部关联并重算资产等级，请带 force=true 确认执行。",
        )
    # 先解绑资产关联（FK cascade 已设为 CASCADE 但显式更安全）
    db.query(AssetBusiness).filter(AssetBusiness.system_id == system_id).delete()
    db.flush()
    # 逐资产重算（设计 §5.2：unlink 规则；manual 资产天然跳过）
    details = []
    for aid in member_ids:
        details.append(recompute_asset(db, aid, allow_manual=False))
    changed = sum(1 for d in details if d.get("changed"))
    if member_ids:
        log_propagation_audit(db, action="DELETE", system_id=system_id,
                              current_user=current_user,
                              result={"affected": len(member_ids), "changed": changed,
                                      "details": details})
    db.delete(b)
    db.commit()
    # 返回 dict 以让装饰器 get_resource_name 拿到 name
    return {"success": True, "message": f"业务系统 '{name}' 已删除", "name": name,
            "unlinked_assets": len(member_ids), "recomputed_changed": changed}


# ----------------------- 资产关联 -----------------------


@router.get("/{system_id}/assets", response_model=List[dict])
async def list_assets_in_system(
    system_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出业务系统下的资产（id/name/ip/role/criticality）"""
    if not db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    rows = db.query(Asset, AssetBusiness.role) \
             .join(AssetBusiness, AssetBusiness.asset_id == Asset.id) \
             .filter(AssetBusiness.system_id == system_id) \
             .order_by(Asset.name.asc()).all()
    return [
        {
            "asset_id": str(a.id),
            "name": a.name,
            "asset_ip": a.asset_ip,
            # === 治本方案三维度（响应中同时提供供前端迁移）===
            "business_impact": a.business_impact,
            "data_sensitivity": a.data_sensitivity,
            "protection_level": a.protection_level,
            # 等级来源徽标（设计 §7 T3：inherited=跟随系统 / manual=人工）
            "protection_level_source": a.protection_level_source or "manual",
            "criticality": a.criticality,  # DEPRECATED 兼容垫片
            "role": role,
        }
        for a, role in rows
    ]


@router.post("/assets/{asset_id}/systems", response_model=AssetBusinessLinkResponse,
             status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="asset_business",
    get_resource_id=lambda result, kwargs: str(result.asset_id) if hasattr(result, 'asset_id') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def link_asset_to_system(
    request: Request,
    asset_id: str,
    data: AssetBusinessLinkCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """为某资产关联一个业务系统（admin only）；唯一约束防重复

    设计 §5.2 T4：link 后传播等保等级。data.inherit 语义（D4）：
      None = 仅 inherited 资产重算（存量兼容）；true = 强制继承；false = 不传播
    """
    from app.services.protection_level_propagation import recompute_asset, log_propagation_audit
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="资产不存在")
    sys = db.query(BusinessSystem).filter(BusinessSystem.id == data.system_id).first()
    if not sys:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    existing = db.query(AssetBusiness).filter(
        AssetBusiness.asset_id == asset_id,
        AssetBusiness.system_id == data.system_id,
    ).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该资产已关联此业务系统")
    link = AssetBusiness(asset_id=asset_id, system_id=data.system_id, role=data.role)
    db.add(link)
    db.flush()  # 先落 link，传播计算能看到新关联
    # 传播（设计 §5.2）：与 link 同事务
    prop_result = recompute_asset(db, asset.id, allow_manual=data.inherit is True)
    if prop_result.get("changed") or prop_result.get("event"):
        log_propagation_audit(db, action="UPDATE", system_id=data.system_id,
                              current_user=current_user,
                              result={"affected": 1, "changed": 1 if prop_result.get("changed") else 0,
                                      "details": [prop_result]})
    db.commit()
    db.refresh(link)
    return AssetBusinessLinkResponse(
        asset_id=str(link.asset_id),
        system_id=str(link.system_id),
        role=link.role,
        created_at=link.created_at,
    )


@router.patch("/assets/{asset_id}/systems/{system_id}", response_model=AssetBusinessLinkResponse)
@log_audit(
    action="UPDATE",
    resource_type="asset_business",
    get_resource_id=lambda result, kwargs: f"{kwargs.get('asset_id')}:{kwargs.get('system_id')}",
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def update_asset_business_role(
    request: Request,
    asset_id: str,
    system_id: str,
    data: AssetBusinessRoleUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """只改关联的架构角色（设计 §7 T2；role 枚举校验在 schema 层）"""
    link = db.query(AssetBusiness).filter(
        AssetBusiness.asset_id == asset_id,
        AssetBusiness.system_id == system_id,
    ).first()
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="关联不存在")
    link.role = data.role
    db.commit()
    db.refresh(link)
    return AssetBusinessLinkResponse(
        asset_id=str(link.asset_id),
        system_id=str(link.system_id),
        role=link.role,
        created_at=link.created_at,
    )


@router.delete("/assets/{asset_id}/systems/{system_id}")
@log_audit(
    action="DELETE",
    resource_type="asset_business",
    get_resource_id=lambda result, kwargs: f"{kwargs.get('asset_id')}:{kwargs.get('system_id')}",
    get_resource_name=lambda result, kwargs: kwargs.get('asset_id'),
)
async def unlink_asset_from_system(
    request: Request,
    asset_id: str,
    system_id: str,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """移除资产-业务系统关联（admin only）；按 D4 重算资产等级（值保留语义见传播引擎）"""
    from app.services.protection_level_propagation import recompute_asset, log_propagation_audit
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="资产不存在")
    n = db.query(AssetBusiness).filter(
        AssetBusiness.asset_id == asset_id,
        AssetBusiness.system_id == system_id,
    ).delete()
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="关联不存在")
    db.flush()
    # 传播（设计 §5.2）：unlink 后重算；manual 资产天然跳过
    prop_result = recompute_asset(db, asset.id, allow_manual=False)
    if prop_result.get("changed") or prop_result.get("event"):
        log_propagation_audit(db, action="UPDATE", system_id=system_id,
                              current_user=current_user,
                              result={"affected": 1, "changed": 1 if prop_result.get("changed") else 0,
                                      "details": [prop_result]})
    db.commit()
    return {"success": True, "message": "关联已移除"}
