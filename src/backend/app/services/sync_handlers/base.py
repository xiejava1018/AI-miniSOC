"""
同步处理器基类（P2-T4：失败入死信）

所有 Handler 必须实现 _handle_one() 处理单条 item；父类 handle() 会逐条 try/except，
失败入 soc_sync_dead_letter，返回 stats（含 failed + dead_letter_batch_id）。

子类可重写 _validate_one() / _handle_one()；stats 字段定义见下。
"""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BaseSyncHandler(ABC):
    """同步处理器抽象基类"""

    # 子类需指定该 handler 处理的 data_type（用于死信分组）
    data_type: str = "unknown"

    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        """批量处理 sync items（P2-T4：每条 try/except，失败入死信）。

        Args:
            source: 数据来源标识，如 "tplink-router"
            items: 原始数据列表
            db: SQLAlchemy Session

        Returns:
            {
                "total": int,
                "created": int,
                "updated": int,
                "skipped": int,
                "failed": int,
                "dead_letter_batch_id": str | None,
            }
        """
        from app.services.sync_dead_letter import DeadLetterRecorder
        batch_id = uuid.uuid4()
        recorder = DeadLetterRecorder(db, batch_id=batch_id)

        stats = {
            "total": len(items),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "dead_letter_batch_id": str(batch_id) if items else None,
        }

        for idx, item in enumerate(items):
            try:
                self._validate_one(item)
                sub = self._handle_one(source, item, db)
                # 子类返回 {"created":N,"updated":N,"skipped":N} 增量
                for k in ("created", "updated", "skipped"):
                    stats[k] += sub.get(k, 0)
            except Exception as e:
                stats["failed"] += 1
                item_key = self._item_key(item) if hasattr(self, "_item_key") else None
                logger.warning(
                    "sync handler failed: source=%s idx=%d err=%s",
                    source, idx, type(e).__name__,
                )
                try:
                    recorder.record(
                        source=source,
                        data_type=self.data_type,
                        item_index=idx,
                        raw_item=item,
                        error=e,
                        item_key=item_key,
                    )
                except Exception as rec_err:
                    logger.error("写死信失败（item_idx=%d）: %s", idx, rec_err)

        db.commit()
        return stats

    @abstractmethod
    def _handle_one(self, source: str, item: dict, db: Session) -> Dict[str, int]:
        """处理单条 item，返回 {"created","updated","skipped"} 增量。"""
        ...

    def _validate_one(self, item: dict) -> None:
        """子类可重写做字段校验；默认通过（要求子类在 _handle_one 中自校验）。

        若 raise，触发 dead_letter 写入。
        """