"""
资产/业务系统重要性分级口径（治本方案 · 2026-09-14）。

第一性原理（ISO 27005 / NIST SP 800-30 / 等保 2.0）：
  资产重要性 = 业务影响(BIA) + 安全价值(CIA) + 等保合规锚点
  三个维度独立、各 5 档、互不重叠。

设计原则：
  1. 5 档对齐等保 2.0（GB/T 22239-2019）五级保护对象（事实标准）。
  2. 业务影响(BIA)驱动 SLA/处置优先级，不进风险评分。
  3. 安全价值(CIA)进风险评分（资产侧攻击价值），是评分的加权因子。
  4. 等保等级是合规锚点，合规报告/等保检查直接消费。

历史：
  - 2026-08-15：4 档 critical/high/medium/low（criticality 单字段）
  - 2026-09-14：拆 3 维度各 5 档，criticality 列保留为 deprecated read-only alias
"""
from __future__ import annotations

# ============================================================================
# 业务影响（BIA · Business Impact Analysis）
# ============================================================================
# 衡量：挂了/被毁/泄露影响多少人、多少收入、多少合规
# 决策方：业务方，资产入库时一次性录入
# 驱动：处置 SLA / 推送优先级 / 应急响应
#
# 5 档（对齐等保 2.0）：
#   5 核心业务：挂了业务停摆、影响核心收入/合规底线
#   4 重要业务：挂了影响重大业务、可用性要求高
#   3 一般业务：挂了影响一般业务、可短期恢复
#   2 辅助支撑：挂了有替代方案、影响有限
#   1 可忽略：测试/演示/可随时下线
BUSINESS_IMPACT_VALUES: tuple[str, ...] = (
    "core",          # 5 - 核心业务
    "important",     # 4 - 重要业务
    "normal",        # 3 - 一般业务
    "auxiliary",     # 2 - 辅助支撑
    "ignorable",     # 1 - 可忽略
)
BUSINESS_IMPACT_LABELS: dict[str, str] = {
    "core":       "核心业务",
    "important":  "重要业务",
    "normal":     "一般业务",
    "auxiliary":  "辅助支撑",
    "ignorable":  "可忽略",
}
BUSINESS_IMPACT_COLORS: dict[str, str] = {
    "core":       "danger",
    "important":  "danger",
    "normal":     "warning",
    "auxiliary":  "info",
    "ignorable":  "info",
}
# SLA 配置（分钟）：业务影响维度的处置优先级
#  P0 (>= critical 告警) 响应时长 / 解决时长
BUSINESS_IMPACT_SLA: dict[str, dict[str, int]] = {
    "core":       {"response_minutes": 15,  "resolve_minutes": 240},
    "important":  {"response_minutes": 60,  "resolve_minutes": 480},
    "normal":     {"response_minutes": 240, "resolve_minutes": 1440},
    "auxiliary":  {"response_minutes": 1440, "resolve_minutes": 4320},
    "ignorable":  {"response_minutes": 4320, "resolve_minutes": 10080},
}


# ============================================================================
# 数据敏感度（CIA · Confidentiality/Integrity/Availability）
# ============================================================================
# 衡量：机密性/完整性/可用性三要素敏感度
# 决策方：安全/IT 评估，可部分自动推导（如 Wazuh 漏洞等级）
# 进：风险评分加权因子（与暴露面/告警/端口并列）
#
# 5 档：
#   5 极高：核心数据（用户密码/密钥）、国密级数据、被攻破即国家级风险
#   4 高：敏感数据（PII、PHI、商业机密）、被攻破即重大合规风险
#   3 中：内部数据（业务运营数据）、被攻破即业务影响
#   2 低：低敏感数据（公开可推导的运营信息）
#   1 可公开：完全公开数据（文档/公告）
DATA_SENSITIVITY_VALUES: tuple[str, ...] = (
    "extreme",       # 5 - 极高
    "high",          # 4 - 高
    "medium",        # 3 - 中
    "low",           # 2 - 低
    "negligible",    # 1 - 可公开
)
DATA_SENSITIVITY_LABELS: dict[str, str] = {
    "extreme":    "极高",
    "high":       "高",
    "medium":     "中",
    "low":        "低",
    "negligible": "可公开",
}
DATA_SENSITIVITY_COLORS: dict[str, str] = {
    "extreme":    "danger",
    "high":       "danger",
    "medium":     "warning",
    "low":        "info",
    "negligible": "info",
}
# 风险评分权重（与现有 importance 维度的映射）
# 100/75/50/25/10（5 档非线性，反映"极高→高"的安全价值跃迁大于"低→可公开"）
DATA_SENSITIVITY_RISK_WEIGHT: dict[str, int] = {
    "extreme":    100,
    "high":       75,
    "medium":     50,
    "low":        25,
    "negligible": 10,
}


# ============================================================================
# 等保等级（Protection Level · 等保 2.0 锚点）
# ============================================================================
# 衡量：网络安全等级保护级别（合规锚点）
# 决策方：合规/IT 评估；业务系统有则继承给资产
# 用途：合规报告 / 等保检查 / 监管报送
#
# 5 档（GB/T 22239-2019）：
#   level_5 五级：国家关键信息基础设施
#   level_4 四级：重要行业核心系统
#   level_3 三级：地市级以上重要系统
#   level_2 二级：一般业务系统
#   level_1 一级：一般小型系统
PROTECTION_LEVEL_VALUES: tuple[str, ...] = (
    "level_5",
    "level_4",
    "level_3",
    "level_2",
    "level_1",
)
PROTECTION_LEVEL_LABELS: dict[str, str] = {
    "level_5": "等保五级",
    "level_4": "等保四级",
    "level_3": "等保三级",
    "level_2": "等保二级",
    "level_1": "等保一级",
}
PROTECTION_LEVEL_COLORS: dict[str, str] = {
    "level_5": "danger",
    "level_4": "danger",
    "level_3": "warning",
    "level_2": "info",
    "level_1": "info",
}


# ============================================================================
# 旧 criticality (4 档) → 新维度映射（治本回填 + 6 个月兼容垫片）
# ============================================================================
# 旧 criticality 是 4 档 critical/high/medium/low + 遗留 'core' 'normal'
# 新维度：
#   - 旧 criticality 表达的是「综合重要性」，新方案拆为业务影响+数据敏感度
#   - 历史回填策略：
#       criticality='critical' → BIA=core,           CIA=extreme
#       criticality='high'     → BIA=important,      CIA=high
#       criticality='medium'   → BIA=normal,         CIA=medium
#       criticality='low'      → BIA=auxiliary,      CIA=low
#       criticality='core'     → BIA=core,           CIA=extreme  (遗留值)
#       criticality='normal'   → BIA=normal,         CIA=medium   (遗留值, 已回填 medium)
#   - 等保等级无历史锚点，默认 level_2（最常见）；后续由合规评估校正
LEGACY_CRITICALITY_MAP: dict[str, dict[str, str]] = {
    # legacy criticality  → business_impact, data_sensitivity, protection_level
    "critical": {"business_impact": "core",       "data_sensitivity": "extreme",    "protection_level": "level_3"},
    "high":     {"business_impact": "important",  "data_sensitivity": "high",       "protection_level": "level_3"},
    "medium":   {"business_impact": "normal",     "data_sensitivity": "medium",     "protection_level": "level_2"},
    "low":      {"business_impact": "auxiliary",  "data_sensitivity": "low",        "protection_level": "level_2"},
    "core":     {"business_impact": "core",       "data_sensitivity": "extreme",    "protection_level": "level_3"},
    "normal":   {"business_impact": "normal",     "data_sensitivity": "medium",     "protection_level": "level_2"},
}
LEGACY_CRITICALITY_DEFAULT: dict[str, str] = {
    "business_impact": "normal",
    "data_sensitivity": "medium",
    "protection_level": "level_2",
}


# ============================================================================
# 应用层兼容垫片（6 个月过渡期）
# ============================================================================
# criticality 列保留为 deprecated read-only alias，外部读时自动从 data_sensitivity 派生
# 业务侧只读 criticality 不再被回写
def legacy_criticality_from_data_sensitivity(data_sensitivity: str | None) -> str:
    """从 5 档 CIA 反向映射到 4 档 criticality（兼容垫片）。

    数据敏感度（5 档）→ 旧 criticality（4 档）：
      extreme    → critical
      high       → high
      medium     → medium
      low        → low
      negligible → low（5 档的低和 4 档的低合并；旧代码无 negligible 概念）
    """
    if not data_sensitivity:
        return "medium"
    return {
        "extreme":    "critical",
        "high":       "high",
        "medium":     "medium",
        "low":        "low",
        "negligible": "low",
    }.get(data_sensitivity, "medium")


# ============================================================================
# 联动校验（写入校验器使用）
# ============================================================================
# 等保等级 vs 业务影响/数据敏感度：合规底线
# 等保五级必须是 BIA=核心 + CIA=极高；等保四级必须 BIA 至少 重要
def is_valid_protection_level_combination(
    protection_level: str | None,
    business_impact: str | None,
    data_sensitivity: str | None,
) -> tuple[bool, str]:
    """校验三维度组合是否符合合规底线。

    返回：(is_valid, error_message)
    """
    if not protection_level:
        return True, ""
    # 等保五级：必须 BIA=core + CIA=extreme
    if protection_level == "level_5":
        if business_impact != "core":
            return False, "等保五级必须配合「核心业务」（业务影响）"
        if data_sensitivity != "extreme":
            return False, "等保五级必须配合「极高」数据敏感度"
    # 等保四级：BIA 至少 important
    if protection_level == "level_4":
        if business_impact in ("auxiliary", "ignorable"):
            return False, "等保四级不适合「辅助/可忽略」业务影响"
    return True, ""


# ============================================================================
# 字典 dict_type 名称（与 init_system_data.py 对齐）
# ============================================================================
DICT_TYPE_BUSINESS_IMPACT = "asset_business_impact"
DICT_TYPE_DATA_SENSITIVITY = "asset_data_sensitivity"
DICT_TYPE_PROTECTION_LEVEL = "protection_level"
# 业务系统维度（仅业务影响，5 档）
DICT_TYPE_BIZ_SYSTEM_IMPACT = "biz_system_business_impact"


def get_business_impact_dict_items() -> list[dict]:
    """生成资产业务影响字典项（用于 init_system_data / 迁移 seed）。"""
    return [
        {
            "dict_type": DICT_TYPE_BUSINESS_IMPACT,
            "dict_code": code,
            "dict_label": BUSINESS_IMPACT_LABELS[code],
            "color": BUSINESS_IMPACT_COLORS[code],
            "sort_order": idx + 1,
        }
        for idx, code in enumerate(BUSINESS_IMPACT_VALUES)
    ]


def get_data_sensitivity_dict_items() -> list[dict]:
    """生成数据敏感度字典项。"""
    return [
        {
            "dict_type": DICT_TYPE_DATA_SENSITIVITY,
            "dict_code": code,
            "dict_label": DATA_SENSITIVITY_LABELS[code],
            "color": DATA_SENSITIVITY_COLORS[code],
            "sort_order": idx + 1,
        }
        for idx, code in enumerate(DATA_SENSITIVITY_VALUES)
    ]


def get_protection_level_dict_items() -> list[dict]:
    """生成等保等级字典项。"""
    return [
        {
            "dict_type": DICT_TYPE_PROTECTION_LEVEL,
            "dict_code": code,
            "dict_label": PROTECTION_LEVEL_LABELS[code],
            "color": PROTECTION_LEVEL_COLORS[code],
            "sort_order": idx + 1,
        }
        for idx, code in enumerate(PROTECTION_LEVEL_VALUES)
    ]


def get_biz_system_impact_dict_items() -> list[dict]:
    """业务系统的业务影响字典项（5 档，与资产 BIA 同语义）。"""
    return [
        {
            "dict_type": DICT_TYPE_BIZ_SYSTEM_IMPACT,
            "dict_code": code,
            "dict_label": BUSINESS_IMPACT_LABELS[code],
            "color": BUSINESS_IMPACT_COLORS[code],
            "sort_order": idx + 1,
        }
        for idx, code in enumerate(BUSINESS_IMPACT_VALUES)
    ]
