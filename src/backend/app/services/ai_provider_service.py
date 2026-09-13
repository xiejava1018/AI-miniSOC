"""AI Provider Service（多 AI 模型配置 CRUD + 设默认 + 审计）"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ai_provider import AIProvider
from app.services.encryption_service import encryption_service

logger = logging.getLogger(__name__)


class AIProviderService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- 查询 ----------

    def list(self, search: Optional[str] = None) -> List[AIProvider]:
        q = self.db.query(AIProvider)
        if search:
            like = f"%{search}%"
            q = q.filter(
                AIProvider.provider_code.ilike(like) | AIProvider.name.ilike(like)
            )
        return q.order_by(AIProvider.id).all()

    def get_by_id(self, provider_id: int) -> AIProvider:
        obj = self.db.query(AIProvider).filter(AIProvider.id == provider_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="AI Provider 不存在")
        return obj

    # ---------- 写操作 ----------

    def create(self, data) -> AIProvider:
        if self.db.query(AIProvider).filter(
            AIProvider.provider_code == data.provider_code
        ).first():
            raise HTTPException(status_code=409, detail=f"编码 {data.provider_code} 已存在")
        obj = AIProvider(
            provider_code=data.provider_code,
            name=data.name,
            base_url=data.base_url,
            protocol=data.protocol,
            model_name=data.model_name,
            api_key=encryption_service.encrypt(data.api_key) if data.api_key else None,
            scenes=data.scenes or [],
            max_tokens=data.max_tokens,
            timeout_seconds=data.timeout_seconds,
            enabled=data.enabled,
            is_default=data.is_default,
            remark=data.remark,
        )
        if data.is_default:
            self._clear_default(exclude_id=None)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        self._invalidate()
        return obj

    def update(self, provider_id: int, data) -> AIProvider:
        obj = self.get_by_id(provider_id)
        changed = []
        for field in ("name", "base_url", "protocol", "model_name", "scenes",
                      "max_tokens", "timeout_seconds", "enabled", "remark"):
            val = getattr(data, field, None)
            if val is not None and getattr(obj, field) != val:
                setattr(obj, field, val)
                changed.append(field)
        # api_key：留空/None = 不修改
        if data.api_key:
            obj.api_key = encryption_service.encrypt(data.api_key)
            changed.append("api_key")
        if data.is_default is True and not obj.is_default:
            self._clear_default(exclude_id=obj.id)
            obj.is_default = True
            changed.append("is_default")
        elif data.is_default is False:
            obj.is_default = False
            changed.append("is_default")
        if changed:
            obj.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(obj)
            self._invalidate()
        return obj

    def delete(self, provider_id: int) -> None:
        obj = self.get_by_id(provider_id)
        self.db.delete(obj)
        self.db.commit()
        self._invalidate()

    def set_default(self, provider_id: int) -> AIProvider:
        obj = self.get_by_id(provider_id)
        self._clear_default(exclude_id=obj.id)
        obj.is_default = True
        self.db.commit()
        self.db.refresh(obj)
        self._invalidate()
        return obj

    def record_test_result(
        self, provider_id: int, *, ok: bool, message: str
    ) -> None:
        obj = self.get_by_id(provider_id)
        obj.last_test_at = datetime.now(timezone.utc)
        obj.last_test_ok = ok
        obj.last_test_message = (message or "")[:1000]
        self.db.commit()

    # ---------- 内部 ----------

    def _clear_default(self, exclude_id: Optional[int]) -> None:
        q = self.db.query(AIProvider).filter(AIProvider.is_default.is_(True))
        if exclude_id is not None:
            q = q.filter(AIProvider.id != exclude_id)
        for row in q.all():
            row.is_default = False

    def _invalidate(self) -> None:
        try:
            from app.services.data_source_resolver import data_source_resolver

            data_source_resolver.invalidate_ai()
        except Exception:
            pass

    def get_decrypted_key(self, obj: AIProvider) -> Optional[str]:
        if not obj.api_key:
            return None
        try:
            return encryption_service.decrypt_if_needed(obj.api_key)
        except Exception:
            logger.error("ai provider %s 密钥解密失败（密钥已变更？请重新录入）", obj.provider_code)
            return None
