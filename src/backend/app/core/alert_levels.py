"""告警分级阈值 —— 全项目唯一权威定义

背景（2026-08-22 统一）：此前项目里同时存在 4 套阈值——
  alert_query/report_generator/impact_analysis/query_templates 用 13/10/7/4；
  ai_analysis 用 12/7（两处）与 12/8（一处）；asset_summary 用 12。
同一条 level-10 告警在「AI 分析」页显示"中风险"、在「安全报告」里计为 high，
生产实测 7 天内该区间有 4,921 条告警受影响。

对齐依据：report_generator.py 的 Wazuh 标准注释
  （level>=13 critical / >=10 high / >=7 medium / >=4 low；level<4 视为噪音）。

所有新代码一律 `from app.core.alert_levels import LEVEL_CRITICAL, ...`；
禁止再写裸数字比较。alert_query.AlertQueryService.LEVEL_* 从此处 re-export，
旧 import 不受影响。
"""

LEVEL_CRITICAL = 13
LEVEL_HIGH = 10
LEVEL_MEDIUM = 7
LEVEL_LOW = 4

# 噪音下限：level < LEVEL_LOW 视为噪音，不计入分级计数
LEVEL_NOISE_BELOW = LEVEL_LOW
