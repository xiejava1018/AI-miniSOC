"""
采集器基类和数据类型定义
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DataType(Enum):
    """支持的数据类型"""
    ASSET = "asset"
    VULNERABILITY = "vulnerability"
    BASELINE = "baseline"
    PORT = "port"
    DISCOVERY = "discovery"
    # S2 暴露面归位（AOG-6 / OH-6.1）：TP-Link 虚拟服务器（DNAT 端口映射）
    # 后端路由按字符串 nat_mapping 识别
    NAT_MAPPING = "nat_mapping"
    # ARL-Next 集成（docs/design/2026-11-14-ARL-Next集成设计方案.md OH-ARL.1）：
    # 外部攻击面测绘源（Web 站点/指纹/端口观测 + PoC 漏洞发现），
    # 后端路由按字符串 arl_site / arl_vuln 识别
    ARL_SITE = "arl_site"
    ARL_VULN = "arl_vuln"


@dataclass
class CollectResult:
    """单次采集结果"""
    source: str
    data_type: DataType
    items: list[dict]
    collected_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


class BaseCollector(ABC):
    """
    采集器抽象基类

    每个 Collector 必须实现:
    - collect(): 执行采集，返回 CollectResult
    - test_connection(): 测试数据源连通性
    """

    source_name: str
    supported_types: list[DataType]

    @abstractmethod
    async def collect(self, data_type: DataType) -> CollectResult:
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        ...

    def supports(self, data_type: DataType) -> bool:
        return data_type in self.supported_types
