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
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.business_system import (
    BusinessSystemCreate,
    BusinessSystemUpdate,
    BusinessSystemResponse,
    BusinessSystemListResponse,
    AssetBusinessLinkCreate,
    AssetBusinessLinkResponse,
)
from app.models.business_system import BusinessSystem, AssetBusiness
from app.models.asset import Asset

router = APIRouter(tags=["业务系统管理"])


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
    rows = q.order_by(BusinessSystem.criticality.asc(), BusinessSystem.name.asc()) \
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
    """更新业务系统（admin only）"""
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
    for k, v in payload.items():
        setattr(b, k, v)
    # 重同步 criticality（与新 data_sensitivity 一致）
    from app.core.criticality import legacy_criticality_from_data_sensitivity
    b.criticality = legacy_criticality_from_data_sensitivity(b.data_sensitivity)
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
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """删除业务系统（admin only）；同时清掉 soc_asset_business 关联"""
    b = db.query(BusinessSystem).filter(BusinessSystem.id == system_id).first()
    if not b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="业务系统不存在")
    name = b.name
    # 先解绑资产关联（FK cascade 已设为 CASCADE 但显式更安全）
    db.query(AssetBusiness).filter(AssetBusiness.system_id == system_id).delete()
    db.delete(b)
    db.commit()
    # 返回 dict 以让装饰器 get_resource_name 拿到 name
    return {"success": True, "message": f"业务系统 '{name}' 已删除", "name": name}


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
    """为某资产关联一个业务系统（admin only）；唯一约束防重复"""
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
    """移除资产-业务系统关联（admin only）"""
    n = db.query(AssetBusiness).filter(
        AssetBusiness.asset_id == asset_id,
        AssetBusiness.system_id == system_id,
    ).delete()
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="关联不存在")
    db.commit()
    return {"success": True, "message": "关联已移除"}
