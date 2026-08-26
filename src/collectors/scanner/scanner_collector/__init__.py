"""scanner-collector: 资产发现与攻击面扫描采集器包。"""

from collector_framework.base import DataType

# DataType 枚举当前只有 PORT；Phase 1 仅暴露公网端口扫描
# Phase 2 (DiscoverySyncHandler 落地后) 再加 INTERNAL / DISCOVERY
SUPPORTED_TYPES = [DataType.PORT]

__version__ = "1.3.0"