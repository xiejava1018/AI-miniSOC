"""
同步处理器模块

提供 Collector → AI-miniSOC 的数据处理管道。
每种 data_type 对应一个 Handler，负责去重、增量更新、变更记录。
"""

from app.services.sync_handlers.base import BaseSyncHandler
from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

# Handler 注册表：data_type → handler 实例
SYNC_HANDLERS: dict[str, BaseSyncHandler] = {
    "asset": AssetSyncHandler(),
}

__all__ = [
    "BaseSyncHandler",
    "AssetSyncHandler",
    "SYNC_HANDLERS",
]
