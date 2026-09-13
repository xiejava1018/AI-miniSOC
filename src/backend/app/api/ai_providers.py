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
