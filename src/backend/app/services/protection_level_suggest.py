"""等保等级建议引擎（OH-4.4a · 确定性矩阵版 · 设计 §6）

GB/T 22240-2020《网络安全等级保护定级指南》定级矩阵 × 现有三维字段的代理映射（D7）：
  - data_sensitivity → 受侵害客体（代理）
  - business_impact   → 侵害程度（代理）

纯函数，无 IO、无 LLM——可独立单测。AI 增强版是后续迭代，不改变本模块输出契约。

红线（主方案 §0.0 S4）：
  1. 本引擎只产出建议，**永不直接写 protection_level**
  2. 等保定级为法律判定，系统只建议不裁决——建议须走人工确认
  3. basis 中强制携带 approximation_note，不得让用户误以为是法定定级结论
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# 受侵害客体代理映射：data_sensitivity → 客体维度
VICTIM_PROXY = {
    "negligible": "citizen_legal",   # 公民、法人和其他组织的合法权益
    "low": "citizen_legal",
    "medium": "social_order",        # 社会秩序、公共利益
    "high": "social_order",
    "extreme": "national_security",  # 国家安全
}

# 侵害程度代理映射：business_impact → 程度维度
HARM_PROXY = {
    "ignorable": "general",            # 一般损害
    "auxiliary": "general",
    "normal": "serious",               # 严重损害
    "important": "serious",
    "core": "extremely_serious",       # 特别严重损害
}

VICTIM_LABELS = {
    "citizen_legal": "公民、法人和其他组织的合法权益",
    "social_order": "社会秩序、公共利益",
    "national_security": "国家安全",
}
HARM_LABELS = {
    "general": "一般损害",
    "serious": "严重损害",
    "extremely_serious": "特别严重损害",
}

# GB/T 22240-2020 定级矩阵（客体 × 程度 → 等级）
MATRIX = {
    ("citizen_legal", "general"): "level_1",
    ("citizen_legal", "serious"): "level_2",
    ("citizen_legal", "extremely_serious"): "level_2",
    ("social_order", "general"): "level_2",
    ("social_order", "serious"): "level_3",
    ("social_order", "extremely_serious"): "level_4",
    ("national_security", "general"): "level_3",
    ("national_security", "serious"): "level_4",
    ("national_security", "extremely_serious"): "level_5",
}

PL_LABELS = {
    "level_5": "等保五级",
    "level_4": "等保四级",
    "level_3": "等保三级",
    "level_2": "等保二级",
    "level_1": "等保一级",
}

APPROXIMATION_NOTE = (
    "受侵害客体/侵害程度由数据敏感度/业务影响代理推断（GB/T 22240 二维矩阵），"
    "非法定调查结论；等保定级为法律判定，本建议仅供参考，须经人工确认。"
)


class SuggestionInputError(ValueError):
    """输入字段非法（不在 5 档枚举内）"""


def build_filing_hint(level: str) -> str:
    """备案义务提示（D5）：一级自主保护无需备案；二级起向公安机关备案。"""
    rank = {"level_1": 1, "level_2": 2, "level_3": 3, "level_4": 4, "level_5": 5}.get(level)
    if rank is None:
        return ""
    if rank == 1:
        return "等保一级：自主保护，无需备案"
    return f"{PL_LABELS[level]}：需向公安机关备案" + (
        "（三级及以上另需专家评审与定期测评）" if rank >= 3 else ""
    )


def suggest(
    business_impact: str,
    data_sensitivity: str,
    evidence: Optional[dict] = None,
    generated_at: Optional[datetime] = None,
) -> dict:
    """生成定级建议。返回设计 §6.2 契约结构（可直接落 suggestion_basis JSONB）。

    参数：
      business_impact / data_sensitivity：业务系统当前三维值（5 档枚举）
      evidence：调用方从 DB 聚合的证据 {asset_count, role_dist, public_exposed_assets}
      generated_at：时间戳（默认当前 UTC；测试可注入固定值）
    """
    from app.core.criticality import BUSINESS_IMPACT_VALUES, DATA_SENSITIVITY_VALUES

    if business_impact not in BUSINESS_IMPACT_VALUES:
        raise SuggestionInputError(
            f"business_impact 必须为 {list(BUSINESS_IMPACT_VALUES)} 之一，得到 {business_impact!r}")
    if data_sensitivity not in DATA_SENSITIVITY_VALUES:
        raise SuggestionInputError(
            f"data_sensitivity 必须为 {list(DATA_SENSITIVITY_VALUES)} 之一，得到 {data_sensitivity!r}")

    victim = VICTIM_PROXY[data_sensitivity]
    harm = HARM_PROXY[business_impact]
    suggested = MATRIX[(victim, harm)]

    return {
        "engine": "matrix_v1",
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
        "matrix_inputs": {
            "victim_object": victim,
            "victim_object_label": VICTIM_LABELS[victim],
            "harm_degree": harm,
            "harm_degree_label": HARM_LABELS[harm],
            "proxies": {
                "data_sensitivity": data_sensitivity,
                "business_impact": business_impact,
            },
            "approximation_note": APPROXIMATION_NOTE,
        },
        "filing_hint": build_filing_hint(suggested),
        "evidence": evidence or {},
        "suggested_level": suggested,
    }


def collect_evidence(db, system_id) -> dict:
    """聚合业务系统的成员证据（调用方传 DB session；服务端聚合，禁止客户端分桶）。

    返回 {asset_count, role_dist, public_exposed_assets}。
    """
    from sqlalchemy import func as sa_func
    from app.models.asset import Asset
    from app.models.business_system import AssetBusiness, BusinessSystem

    role_rows = (
        db.query(AssetBusiness.role, sa_func.count(AssetBusiness.asset_id))
        .filter(AssetBusiness.system_id == system_id)
        .group_by(AssetBusiness.role)
        .all()
    )
    role_dist = {(r or "unspecified"): int(c) for r, c in role_rows}
    asset_count = sum(role_dist.values())

    exposed = (
        db.query(sa_func.count(Asset.id))
        .join(AssetBusiness, AssetBusiness.asset_id == Asset.id)
        .filter(AssetBusiness.system_id == system_id)
        .filter(Asset.exposure_level == "public")
        .scalar()
    ) or 0

    return {
        "asset_count": int(asset_count),
        "role_dist": role_dist,
        "public_exposed_assets": int(exposed),
    }
