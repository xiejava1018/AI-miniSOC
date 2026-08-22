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

# 通知/处置阈值：level >= SEVERE_LEVEL 视为“严重”，触发站内通知 + WS 推送
# （app/api/webhooks.py）。注意：SEVERE_LEVEL(12) 与 LEVEL_HIGH(10) 是**两个
# 不同语义**——前者是“是否值得打扰人”，后者是“风险等级 high”。不可混用。
SEVERE_LEVEL = 12


def level_to_severity(level) -> str:
    """Wazuh rule.level(1-15) → 事件/展示 severity(critical/high/medium/low)。

    权威口径：>=13 critical / >=10 high / >=7 medium / 其余 low。
    无效输入（None / 非数字）回退 'low'，调用方不应因此崩溃。
    """
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return "low"
    if lv >= LEVEL_CRITICAL:
        return "critical"
    if lv >= LEVEL_HIGH:
        return "high"
    if lv >= LEVEL_MEDIUM:
        return "medium"
    return "low"


def level_to_priority(level) -> str:
    """Wazuh rule.level → AI 研判优先级 P0-P3。

    与 _PRIORITY_TO_SEVERITY（P0=critical/P1=high/P2=medium/P3=low）
    互为逆映射，供降级研判（_heuristic_verdict）与 LLM 路径对齐。
    """
    return {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
    }[level_to_severity(level)]
