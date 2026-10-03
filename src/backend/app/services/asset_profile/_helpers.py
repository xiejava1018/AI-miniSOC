"""OH-2.1 公共 loader 工具函数。

提供：
- ``orm_evidence(db, asset, source)``：根据 ORM 表名 + 主表的 updated_at 生成默认 EvidenceItem
- ``safe_load(fn, default)``：loader 异常兜底装饰器；异常时返回 default（不抛）
- ``EVIDENCE_CONFIDENCE``：常量，默认 0.8（直接 ORM 读，可信度高于手工）
"""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timezone
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.services.asset_profile._main import EvidenceItem

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 默认 evidence confidence：直接 ORM 读取 = 0.8（高于手工 0.6）
EVIDENCE_CONFIDENCE = 0.8


def orm_evidence(
    db: Session,
    asset,
    source: str,
    observed_at: datetime | None = None,
    confidence: float = EVIDENCE_CONFIDENCE,
    reference: str | None = None,
    note: str | None = None,
) -> EvidenceItem:
    """根据 ORM 表生成默认 EvidenceItem。

    observed_at 优先级：
    1. 显式传入的 ``observed_at``
    2. ``asset.updated_at``
    3. ``datetime.now(timezone.utc)`` 兜底
    """
    if observed_at is None:
        observed_at = getattr(asset, "updated_at", None) or datetime.now(timezone.utc)
    return EvidenceItem(
        source=source,
        observed_at=observed_at,
        confidence=confidence,
        reference=reference,
        note=note,
    )


def safe_load(default: T) -> Callable:
    """loader 异常兜底装饰器。

    用法::

        @safe_load(default=AssetIdentity())
        def load_identity(db, asset):
            ...

    loader 内部任何异常（DB 断连、字段缺失、类型错） → 返回 default，不抛。
    logger.exception 记录完整 stack，方便回溯。
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                logger.exception(
                    "loader %s failed: %s; returning default",
                    fn.__name__, exc,
                )
                return default
        return wrapper
    return decorator
