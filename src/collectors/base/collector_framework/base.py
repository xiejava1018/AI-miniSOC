"""
采集器基类和数据类型定义
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class DataType(Enum):
    """支持的数据类型"""
    ASSET = "asset"
    VULNERABILITY = "vulnerability"
    BASELINE = "baseline"
    PORT = "port"


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
