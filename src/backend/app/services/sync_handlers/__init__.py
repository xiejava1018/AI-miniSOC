"""
同步处理器模块

提供 Collector → AI-miniSOC 的数据处理管道。
每种 data_type 对应一个 Handler，负责去重、增量更新、变更记录。
"""

from app.services.sync_handlers.base import BaseSyncHandler
from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler
# P3/F-S2：资产发现扫描器公网暴露面扫描
from app.services.sync_handlers.port_sync_handler import PortSyncHandler
# P3/F-S1：资产发现扫描器内网发现（落 soc_scan_findings，不写台账）
from app.services.sync_handlers.discovery_sync_handler import DiscoverySyncHandler

# Handler 注册表：data_type → handler 实例
SYNC_HANDLERS: dict[str, BaseSyncHandler] = {
    "asset": AssetSyncHandler(),
    "port": PortSyncHandler(),
    "discovery": DiscoverySyncHandler(),
}

__all__ = [
    "BaseSyncHandler",
    "AssetSyncHandler",
    "PortSyncHandler",
    "DiscoverySyncHandler",
    "SYNC_HANDLERS",
]
