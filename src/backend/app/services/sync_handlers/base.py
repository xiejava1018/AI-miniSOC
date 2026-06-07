"""
同步处理器基类

所有 Handler 必须实现 handle() 方法，接收原始数据列表，
执行去重、增量更新、变更记录，返回统计结果。
"""

from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseSyncHandler(ABC):
    """同步处理器抽象基类"""

    @abstractmethod
    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        """
        处理同步数据

        Args:
            source: 数据来源标识，如 "tplink-router"
            items: 原始数据列表（Collector 推送的标准格式）
            db: SQLAlchemy Session

        Returns:
            {
                "total": int,
                "created": int,
                "updated": int,
                "skipped": int,
                "failed": int,
                "errors": list[str],
            }
        """
        ...
