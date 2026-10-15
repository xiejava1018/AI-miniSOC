"""
同步死信管理 API（D - dead letter resolve / replay）

前置背景：
  - 死信表 `soc_sync_dead_letter` 早已存在（soc_sync_dead_letter.py）
  - 但此前**没有任何 API 暴露**，只有后台任务在写
  - 2026-10-08 修复（wazuh 采集器 trim data_type + asset_sync 漂移识别）
    之后留下的"陈年死信"无法人工标记 resolved / 重新入队
  - 数据健康页面因此长期显示"已修复的问题"为"故障"（A 已经在
    前端做了 7 天窗口过滤，本模块提供后端操作入口）

设计原则：
  - admin only（死信 replay 等价"重新跑数据导入"，影响生产库）
  - 写操作走 @log_audit，列入 hash 链审计（CLAUDE.md §1.5）
  - bulk 操作分页（limit ≤ 200）防止误操作把整表改掉
  - resolve 与 replay 互不破坏 raw_item（保留审计价值）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit_decorator import log_audit
from app.core.database import get_db
from app.core.permissions import require_admin
from app.models.sync_dead_letter import SyncDeadLetter
from app.models.user import User
from app.services.sync_handlers import SYNC_HANDLERS

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class DeadLetterResolveRequest(BaseModel):
    """单条死信标记 resolved（不重放，仅归档）"""
    reason: Optional[str] = Field(
        None, max_length=200, description="标记原因（写入审计）"
    )


class DeadLetterReplayRequest(BaseModel):
    """单条死信重新入队"""
    reason: Optional[str] = Field(
        None, max_length=200, description="重放原因（写入审计）"
    )


class DeadLetterBulkResolveRequest(BaseModel):
    """批量死信处理请求（按 source / data_type / 时间 / error 过滤）"""
    source: Optional[str] = None
    data_type: Optional[str] = None
    error_class: Optional[str] = None
    error_message_contains: Optional[str] = Field(
        None, description="LIKE 匹配 error_message 子串"
    )
    before: Optional[datetime] = Field(
        None, description="只处理 created_at < before 的记录"
    )
    limit: int = Field(
        200, ge=1, le=500,
        description="批量上限（防误操作全表；500 是硬上限）",
    )
    dry_run: bool = Field(
        True, description="true 只返回将命中的条数，false 实际执行（默认 dry_run）"
    )


# ---------------------------------------------------------------------------
# 列表 / 详情
# ---------------------------------------------------------------------------


@router.get("/dead-letter", summary="死信列表（支持多维过滤）")
async def list_dead_letters(
    source: Optional[str] = None,
    data_type: Optional[str] = None,
    error_class: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin()),
):
    """死信列表。admin only。"""
    q = select(SyncDeadLetter)
    if source is not None:
        q = q.where(SyncDeadLetter.source == source)
    if data_type is not None:
        q = q.where(SyncDeadLetter.data_type == data_type)
    if error_class is not None:
        q = q.where(SyncDeadLetter.error_class == error_class)
    if resolved is not None:
        q = q.where(SyncDeadLetter.resolved.is_(resolved))
    q = q.order_by(SyncDeadLetter.created_at.desc()).limit(limit).offset(offset)

    rows = db.execute(q).scalars().all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(r.id),
                "batch_id": str(r.batch_id),
                "source": r.source,
                "data_type": r.data_type,
                "item_index": r.item_index,
                "item_key": r.item_key,
                "error_class": r.error_class,
                "error_message": (r.error_message or "")[:300],
                "replay_count": r.replay_count,
                "resolved": r.resolved,
                "last_replayed_at": r.last_replayed_at.isoformat() if r.last_replayed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/dead-letter/{dead_letter_id}", summary="死信详情")
async def get_dead_letter(
    dead_letter_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin()),
):
    row = db.get(SyncDeadLetter, dead_letter_id)
    if not row:
        raise HTTPException(status_code=404, detail="死信记录不存在")
    return {
        "id": str(row.id),
        "batch_id": str(row.batch_id),
        "source": row.source,
        "data_type": row.data_type,
        "item_index": row.item_index,
        "item_key": row.item_key,
        "error_class": row.error_class,
        "error_message": row.error_message,
        "raw_item": row.raw_item,
        "replay_count": row.replay_count,
        "resolved": row.resolved,
        "last_replayed_at": row.last_replayed_at.isoformat() if row.last_replayed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# 单条 resolve
# ---------------------------------------------------------------------------


@router.post(
    "/dead-letter/{dead_letter_id}/resolve",
    summary="单条死信标记为已解决（不重放）",
)
@log_audit(
    action="UPDATE",
    resource_type="sync_dead_letter",
    # soc_audit_logs.resource_id 是 BigInteger，UUID 走 resource_name（见 audit_decorator.py:110 注释）
    get_resource_id=lambda result, kwargs: None,
    get_resource_name=lambda result, kwargs: str(kwargs.get("dead_letter_id")),
    get_new_values=lambda result, kwargs: {
        "resolved": True,
        "reason": (kwargs.get("payload").reason if kwargs.get("payload") else None),
    },
)
async def resolve_dead_letter(
    dead_letter_id: UUID,
    payload: DeadLetterResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    把单条死信标记为 resolved=true。

    与 replay 的区别：
      - resolve：只归档（"已知问题，留作审计"）
      - replay：重新跑 handler，期望 raw_item 能被处理掉

    标记 resolved 不会删除 raw_item（保留审计价值）。
    """
    row = db.get(SyncDeadLetter, dead_letter_id)
    if not row:
        raise HTTPException(status_code=404, detail="死信记录不存在")
    if row.resolved:
        # 幂等：不报错，返回当前状态
        return {"id": str(row.id), "resolved": True, "already": True}

    row.resolved = True
    row.last_replayed_at = datetime.now(timezone.utc)  # 复用字段记录"最后处理时间"
    db.commit()
    logger.info(
        "dead_letter resolve: id=%s user=%s reason=%s",
        dead_letter_id, current_user.username, (payload.reason or ""),
    )
    return {"id": str(row.id), "resolved": True, "already": False}


# ---------------------------------------------------------------------------
# 单条 replay
# ---------------------------------------------------------------------------


@router.post(
    "/dead-letter/{dead_letter_id}/replay",
    summary="单条死信重放（重新走 sync handler）",
)
@log_audit(
    action="UPDATE",
    resource_type="sync_dead_letter",
    get_resource_id=lambda result, kwargs: None,
    get_resource_name=lambda result, kwargs: str(kwargs.get("dead_letter_id")),
    get_new_values=lambda result, kwargs: {
        "replayed": True,
        "reason": (kwargs.get("payload").reason if kwargs.get("payload") else None),
    },
)
async def replay_dead_letter(
    dead_letter_id: UUID,
    payload: DeadLetterReplayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    重放单条死信：把 raw_item 重新跑一遍对应 handler。

    成功：resolved=true，replay_count+1
    失败：resolved 不变，replay_count+1，error_message 更新为新错误

    不删除 raw_item（即使重放成功，保留原始失败现场供审计）。
    """
    row = db.get(SyncDeadLetter, dead_letter_id)
    if not row:
        raise HTTPException(status_code=404, detail="死信记录不存在")
    if row.resolved:
        raise HTTPException(
            status_code=409,
            detail="已 resolved 的死信不能重放（已归档，保留审计）",
        )

    handler = SYNC_HANDLERS.get(row.data_type)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"当前 SYNC_HANDLERS 不支持 {row.data_type}（handler 已下线？）："
                   f"支持 {', '.join(SYNC_HANDLERS.keys())}",
        )

    # raw_item 是 list（一条死信对应一个原始 item）
    raw_item = row.raw_item
    if not isinstance(raw_item, list):
        # 兼容老数据
        items = [raw_item]
    else:
        items = raw_item

    try:
        handler.handle(row.source, items, db)
        # 成功：归档 + 计数
        row.replay_count = (row.replay_count or 0) + 1
        row.last_replayed_at = datetime.now(timezone.utc)
        row.resolved = True
        db.commit()
        logger.info(
            "dead_letter replay ok: id=%s user=%s source=%s data_type=%s",
            dead_letter_id, current_user.username, row.source, row.data_type,
        )
        return {
            "id": str(row.id),
            "replayed": True,
            "resolved": True,
            "replay_count": row.replay_count,
        }
    except Exception as e:
        # 失败：保留 resolved=false，更新错误信息
        row.replay_count = (row.replay_count or 0) + 1
        row.last_replayed_at = datetime.now(timezone.utc)
        row.error_message = f"[replay {row.replay_count}] {type(e).__name__}: {e}"[:2000]
        db.commit()
        logger.warning(
            "dead_letter replay fail: id=%s user=%s err=%s",
            dead_letter_id, current_user.username, e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"重放失败：{type(e).__name__}: {e}",
        )


# ---------------------------------------------------------------------------
# 批量 resolve
# ---------------------------------------------------------------------------


@router.post(
    "/dead-letter/bulk-resolve",
    summary="批量死信标记 resolved（dry_run 默认 true）",
)
@log_audit(
    action="UPDATE",
    resource_type="sync_dead_letter_bulk",
    get_resource_id=lambda result, kwargs: None,
    get_resource_name=lambda result, kwargs: "bulk",
    get_new_values=lambda result, kwargs: {
        "filter": kwargs.get("payload").model_dump() if kwargs.get("payload") else None,
    },
)
async def bulk_resolve_dead_letters(
    payload: DeadLetterBulkResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    按多维条件批量标记 resolved。

    **默认 dry_run=true**：先返回将命中的条数，必须再次以 dry_run=false 才会真改。
    防止一次操作清空整张表——历史数据清理工具（B+C）走的就是这个端点。

    必传过滤条件至少一个（强制显式）：source / data_type / error_class /
    error_message_contains / before 之中至少一个不为 None。
    """
    filters = [
        payload.source,
        payload.data_type,
        payload.error_class,
        payload.error_message_contains,
        payload.before,
    ]
    if not any(f is not None for f in filters):
        raise HTTPException(
            status_code=422,
            detail="必须至少传一个过滤条件（source / data_type / error_class / "
                   "error_message_contains / before），防止误操作全表。",
        )

    q = select(SyncDeadLetter).where(SyncDeadLetter.resolved.is_(False))
    if payload.source is not None:
        q = q.where(SyncDeadLetter.source == payload.source)
    if payload.data_type is not None:
        q = q.where(SyncDeadLetter.data_type == payload.data_type)
    if payload.error_class is not None:
        q = q.where(SyncDeadLetter.error_class == payload.error_class)
    if payload.error_message_contains is not None:
        q = q.where(
            SyncDeadLetter.error_message.contains(payload.error_message_contains)
        )
    if payload.before is not None:
        q = q.where(SyncDeadLetter.created_at < payload.before)

    # 先 count 命中数
    from sqlalchemy import func
    count_q = select(func.count()).select_from(q.subquery())
    matched = db.execute(count_q).scalar() or 0

    if payload.dry_run:
        return {
            "dry_run": True,
            "matched": matched,
            "would_resolve": min(matched, payload.limit),
            "limit": payload.limit,
            "action": "重发同请求 + dry_run=false 才会真改",
        }

    # 真改：限制在 limit 条
    update_q = q.limit(payload.limit)
    ids = [r.id for r in db.execute(update_q).scalars().all()]
    if not ids:
        return {"dry_run": False, "resolved_count": 0}

    db.execute(
        update(SyncDeadLetter)
        .where(SyncDeadLetter.id.in_(ids))
        .values(
            resolved=True,
            last_replayed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    logger.info(
        "dead_letter bulk resolve: user=%s count=%d filters=%s",
        current_user.username, len(ids),
        payload.model_dump(exclude={"dry_run", "limit"}),
    )
    return {
        "dry_run": False,
        "resolved_count": len(ids),
        "matched": matched,
        "limit": payload.limit,
        "ids": [str(i) for i in ids[:20]],  # 只回前 20 个 id，避免响应爆炸
    }
