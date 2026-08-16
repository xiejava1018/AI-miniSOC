"""
同步失败死信与重放（P2-T4）

提供：
- record_dead_letter：把失败的 item 入死信（带 batch_id + 错误明细）
- replay_batch：按 batch_id 重放一批失败记录，返回重放结果

设计：
- 部分失败不阻断整批（base handler 已 try/except 每条 item）
- 失败记录可查、可重放（replay_count 累加，resolved=True 标记成功）
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.sync_dead_letter import SyncDeadLetter

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeadLetterRecorder:
    """死信记录器。"""

    def __init__(self, db: Session, batch_id: Optional[uuid.UUID] = None) -> None:
        self.db = db
        self.batch_id = batch_id or uuid.uuid4()

    def record(
        self,
        *,
        source: str,
        data_type: str,
        item_index: int,
        raw_item: dict,
        error: Exception,
        item_key: Optional[str] = None,
    ) -> None:
        """把一个失败 item 入死信（不提交）。"""
        row = SyncDeadLetter(
            batch_id=self.batch_id,
            source=source,
            data_type=data_type,
            item_index=item_index,
            item_key=item_key,
            error_class=type(error).__name__,
            error_message=str(error)[:2000],
            raw_item=raw_item,
            created_at=utc_now(),
        )
        self.db.add(row)
        logger.warning(
            "dead_letter: batch=%s src=%s item_idx=%d err=%s",
            self.batch_id, source, item_index, type(error).__name__,
        )


def replay_batch(
    db: Session,
    *,
    batch_id: uuid.UUID,
    handler_callable,
) -> Dict[str, int]:
    """按 batch_id 重放死信记录。

    Args:
        db: SQLAlchemy Session
        batch_id: 死信批次 UUID
        handler_callable: 重放回调，签名 (source, items, db) -> dict
            （与 BaseSyncHandler.handle 一致）

    Returns:
        {"total": N, "resolved": M, "still_failing": K}
    """
    rows: List[SyncDeadLetter] = (
        db.query(SyncDeadLetter)
        .filter(SyncDeadLetter.batch_id == batch_id, SyncDeadLetter.resolved == False)
        .all()
    )
    if not rows:
        return {"total": 0, "resolved": 0, "still_failing": 0}

    # 按 source + data_type 分组（同一 handler 处理一组）
    grouped: Dict[tuple, List[SyncDeadLetter]] = {}
    for r in rows:
        key = (r.source, r.data_type)
        grouped.setdefault(key, []).append(r)

    total = len(rows)
    resolved = 0
    still_failing = 0

    for (source, data_type), group in grouped.items():
        # 按 item_index 排序保证重放顺序稳定
        group.sort(key=lambda r: r.item_index)
        items = [r.raw_item for r in group]
        try:
            handler_callable(source, items, db)
            # 整组成功：全部 mark resolved
            for r in group:
                r.resolved = True
                r.replay_count = (r.replay_count or 0) + 1
                r.last_replayed_at = utc_now()
            resolved += len(group)
            logger.info("dead_letter replay: batch=%s (%s/%s) all %d resolved", batch_id, source, data_type, len(group))
        except Exception as e:
            # 部分成功也可能（如 handler 内部 try/except）但整组抛错 = 整组仍失败
            logger.error("dead_letter replay failed: %s", e)
            for r in group:
                r.replay_count = (r.replay_count or 0) + 1
                r.last_replayed_at = utc_now()
            still_failing += len(group)

    db.commit()
    return {"total": total, "resolved": resolved, "still_failing": still_failing}