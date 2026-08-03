"""
上网行为异常检测服务包

模块组成：
  - config.py         : 检测配置（从 soc_system_config 读取，带缓存）
  - loki_client.py    : Loki API 客户端
  - log_parser.py     : 日志解析（字段提取 + 去重）
  - rule_engine.py    : 6 类规则 + 打分
  - baseline_service.py: 基线读写/清理
  - event_service.py  : 事件入库 + 升级 soc_incidents + 通知
  - scheduler.py      : 后台调度（lifespan 启动）
"""

from app.services.browsing_detection.scheduler import (
    start_browsing_detector,
    stop_browsing_detector,
)

__all__ = ["start_browsing_detector", "stop_browsing_detector"]
