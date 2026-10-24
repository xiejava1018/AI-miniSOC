"""AI Provider API（多 AI 模型配置）"""

from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.ai_provider import (
    AIProviderCreate,
    AIProviderListResponse,
    AIProviderResponse,
    AIProviderUpdate,
    AISceneCatalog,
    AITestRequest,
    AITestResponse,
    SCENES,
)
from app.services.ai_provider_service import AIProviderService
from app.services.config_test_service import ConfigTestService

router = APIRouter()


def _to_response(obj) -> AIProviderResponse:
    from app.services.ai_provider_service import AIProviderService

    resp = AIProviderResponse.model_validate(obj)
    resp.has_key = bool(obj.api_key)
    return resp


@router.get("", response_model=AIProviderListResponse)
async def list_providers(
    search: str | None = None,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = AIProviderService(db)
    items = svc.list(search=search)
    return AIProviderListResponse(
        items=[_to_response(i) for i in items], total=len(items)
    )


@router.get("/scenes", response_model=AISceneCatalog)
async def list_scenes(
    current_user: UserResponseSchema = Depends(get_current_user),
):
    return AISceneCatalog(scenes=SCENES)


@router.get("/status", summary="AI 当前生效状态")
async def ai_status(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回 AI 的实际生效来源，供配置中心显式展示。

    2026-10-24：此前页面无法区分「没配实例 → 回落 .env」与
    「配了但全停用 → 现在不可用」，用户看到「停用」却不知道 AI 还能不能用。
    """
    from app.models.ai_provider import AIProvider
    from app.services.data_source_resolver import data_source_resolver

    all_rows = db.query(AIProvider).all()
    enabled_rows = [p for p in all_rows if p.enabled]

    if enabled_rows:
        state = "db"
        detail = "使用配置中心的模型实例"
    elif all_rows:
        state = "disabled"
        detail = "全部模型实例已停用，AI 功能当前不可用（不会回落 .env）"
    else:
        state = "env"
        detail = "未配置模型实例，全部 AI 功能回落 .env GLM 环境变量"

    resolved = data_source_resolver.resolve_ai(None, db)
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "state": state,
            "detail": detail,
            "instance_count": len(all_rows),
            "enabled_count": len(enabled_rows),
            "origin": resolved.origin,
            "source_code": resolved.source_code,
        },
    }


@router.get("/{provider_id}", response_model=AIProviderResponse)
async def get_provider(
    provider_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _to_response(AIProviderService(db).get_by_id(provider_id))


@router.post("", response_model=AIProviderResponse)
@log_audit(
    action="CREATE",
    resource_type="ai_provider",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, "id") else None,
    get_resource_name=lambda result, kwargs: getattr(result, "provider_code", None),
)
async def create_provider(
    request: Request,
    data: AIProviderCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = AIProviderService(db)
    return _to_response(svc.create(data))


@router.put("/{provider_id}", response_model=AIProviderResponse)
@log_audit(
    action="UPDATE",
    resource_type="ai_provider",
    get_resource_id=lambda result, kwargs: kwargs.get("provider_id"),
)
async def update_provider(
    request: Request,
    provider_id: int,
    data: AIProviderUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    return _to_response(AIProviderService(db).update(provider_id, data))


@router.delete("/{provider_id}")
@log_audit(
    action="DELETE",
    resource_type="ai_provider",
    get_resource_id=lambda result, kwargs: kwargs.get("provider_id"),
)
async def delete_provider(
    request: Request,
    provider_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    AIProviderService(db).delete(provider_id)
    return {"success": True, "message": "已删除"}


@router.post("/{provider_id}/set-default", response_model=AIProviderResponse)
@log_audit(
    action="SET_DEFAULT",
    resource_type="ai_provider",
    get_resource_id=lambda result, kwargs: kwargs.get("provider_id"),
)
async def set_default(
    request: Request,
    provider_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    return _to_response(AIProviderService(db).set_default(provider_id))


@router.post("/test", response_model=AITestResponse)
async def test_provider(
    request: Request,
    payload: AITestRequest,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """测试连接：1-token 探活，同时验证 base_url + api_key + model。"""
    svc = AIProviderService(db)
    test_svc = ConfigTestService(db)

    if payload.id is not None:
        obj = svc.get_by_id(payload.id)
        result = test_svc._test_ai_provider(
            obj.base_url,
            "apikey",
            svc.get_decrypted_key(obj),
            {"model": obj.model_name},
            obj.timeout_seconds,
        )
        svc.record_test_result(
            payload.id, ok=result.ok, message=result.message
        )
    else:
        if payload.draft is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="id 与 draft 必填其一")
        d = payload.draft
        result = test_svc._test_ai_provider(
            d.base_url, "apikey", d.api_key, {"model": d.model_name}, d.timeout_seconds
        )
    return result
