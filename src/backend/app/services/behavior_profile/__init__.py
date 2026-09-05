"""行为画像服务包

模块组成（方案 §9.3）：
  - classifier.py   : 分类体系 + 时段定义
  - loki_source.py  : Loki 原始日志递归分块拉取（逐条时间戳计数口径）
  - aggregator.py   : 单日聚合 / 滚动窗口合并 / 机器流量判定
  - tagger.py       : 画像标签规则引擎 + 人设映射 + 置信度
  - snapshot_job.py : 每日快照 + 水位回溯补拉 + gap 缺口标记
"""

from .snapshot_job import (
    start_behavior_profile_scheduler,
    stop_behavior_profile_scheduler,
)

__all__ = ["start_behavior_profile_scheduler", "stop_behavior_profile_scheduler"]
