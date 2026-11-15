"""系统配置 API"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.audit_decorator import log_audit
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.permissions import require_admin
from app.schemas.system_config import (
    CategoryItem,
    SystemConfigCreate,
    SystemConfigListResponse,
    SystemConfigResponse,
    SystemConfigUpdate,
)
from app.schemas.user import UserResponse as UserResponseSchema
from app.services import config_validation
from app.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/arl/test-connection")
async def test_arl_connection(
    db: Session = Depends(get_db),
    _admin: UserResponseSchema = Depends(require_admin),
):
    """OH-ARL.7：ARL-Next 连通性测试（admin）。

    配置读取顺序：配置中心 arl.base_url → Settings.ARL_PROFILE_BASE_URL（env）。
    凭据走 env（ARL_PROFILE_API_KEY / ARL_PROFILE_USERNAME+PASSWORD）——
    凭据不入配置中心（C4：system_configs 未接加密链路，入库即明文）。
    测试动作：login（或 Key 直用）→ GET /api/asset_site/?size=1（code===200 判据）。
    只读不触发扫描（C3）。
    """
    import time

    from app.core.config import settings

    started = time.monotonic()
    # 配置中心 arl.base_url 优先，env 兜底
    cfg = SystemConfigService(db)
    base_url = None
    try:
        row = cfg.get_by_category_and_key("arl", "arl.base_url")
        if row and (row.value or "").strip():
            base_url = row.value.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("配置中心 arl.base_url 读取失败（env 兜底）: %s", e)
    if not base_url:
        base_url = settings.ARL_PROFILE_BASE_URL
    if not base_url:
        return {
            "ok": False,
            "message": "未配置 ARL 地址（配置中心 arl.base_url 或环境变量 ARL_PROFILE_BASE_URL）",
            "elapsed_ms": 0,
        }


    async def _probe() -> tuple[bool, str]:
        import httpx
        token: str | None = None
        if settings.ARL_PROFILE_API_KEY:
            token = settings.ARL_PROFILE_API_KEY
        elif settings.ARL_PROFILE_USERNAME and settings.ARL_PROFILE_PASSWORD:
            async with httpx.AsyncClient(
                verify=settings.ARL_PROFILE_VERIFY_TLS, timeout=8.0, trust_env=False,
            ) as client:
                r = await client.post(
                    f"{base_url.rstrip('/')}/api/user/login",
                    json={"username": settings.ARL_PROFILE_USERNAME,
                          "password": settings.ARL_PROFILE_PASSWORD},
                )
                r.raise_for_status()
                body = r.json()
                if body.get("code") != 200:
                    return False, f"login 失败 code={body.get('code')}"
                token = (body.get("data") or {}).get("token")
        if not token:
            return False, "凭据未配置（ARL_PROFILE_API_KEY 或 USERNAME+PASSWORD）"
        async with httpx.AsyncClient(
            verify=settings.ARL_PROFILE_VERIFY_TLS, timeout=8.0, trust_env=False,
        ) as client:
            r = await client.get(
                f"{base_url.rstrip('/')}/api/asset_site/",
                headers={"Token": token},
                params={"page": 1, "size": 1},
            )
            r.raise_for_status()
            body = r.json()
            if body.get("code") != 200:
                return False, f"asset_site 业务失败 code={body.get('code')}"
            return True, f"可达，归档站点 {body.get('total')} 条"

    try:
        ok, message = await _probe()
        elapsed = int((time.monotonic() - started) * 1000)
        return {"ok": ok, "message": message, "elapsed_ms": elapsed, "base_url": base_url}
    except Exception as e:  # noqa: BLE001
        elapsed = int((time.monotonic() - started) * 1000)
        return {"ok": False, "message": f"{type(e).__name__}: {e}", "elapsed_ms": elapsed}


@router.get("/categories", response_model=list[CategoryItem])
async def get_config_categories(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取所有配置分类及数量"""
    service = SystemConfigService(db)
    return service.get_all_categories()


@router.get("/by-category/{category}", response_model=list[SystemConfigResponse])
async def get_configs_by_category(
    category: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按分类取全部配置（不分页）"""
    service = SystemConfigService(db)
    items = service.get_by_category(category)
    return [SystemConfigResponse.model_validate(i) for i in items]


@router.get("", response_model=SystemConfigListResponse)
async def get_config_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    category: str | None = Query(None),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页获取配置列表"""
    service = SystemConfigService(db)
    skip = (page - 1) * page_size
    items, total = service.get_list(
        skip=skip, limit=page_size, search=search, category=category
    )
    return SystemConfigListResponse(
        total=total,
        items=[SystemConfigResponse.model_validate(i) for i in items],
        page=page,
        page_size=page_size,
    )


@router.get("/{config_id}", response_model=SystemConfigResponse)
async def get_config(
    config_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        item = service.get_by_id(config_id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=SystemConfigResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: f"{result.category}.{result.key}" if hasattr(result, 'category') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def create_config(
    request: Request,
    data: SystemConfigCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        # schema 校验：已注册项按类型/范围/正则校验，editable=False 拒绝
        config_validation.validate_value(db, data.category, data.key, data.value)
        item = service.create(data, user_id=current_user.id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{config_id}", response_model=SystemConfigResponse)
@log_audit(
    action="UPDATE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: kwargs.get('config_id'),
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def update_config(
    request: Request,
    config_id: int,
    data: SystemConfigUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        # schema 校验：按现有行的 category/key 校验新值
        existing = service.get_by_id(config_id)
        if data.value is not None:
            config_validation.validate_value(db, existing.category, existing.key, data.value)
        item = service.update(config_id, data, user_id=current_user.id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{config_id}")
@log_audit(
    action="DELETE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: kwargs.get('config_id'),
)
async def delete_config(
    request: Request,
    config_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        # schema 保护：已注册项禁止删除（防静默回落默认值）
        existing = service.get_by_id(config_id)
        config_validation.validate_delete(db, existing.category, existing.key)
        service.delete(config_id)
        return {"success": True, "message": "配置项已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

