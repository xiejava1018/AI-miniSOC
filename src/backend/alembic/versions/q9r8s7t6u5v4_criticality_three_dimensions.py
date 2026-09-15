"""
资产/业务系统重要性三维度改造（治本方案 · 2026-09-14）

第一性原理（ISO 27005 / NIST SP 800-30 / 等保 2.0）：
  4 档 criticality 单字段表达不出「业务影响 BIA」「数据敏感度 CIA」「等保合规锚点」
  三个独立维度的语义。本迁移拆为 3 字段、各 5 档，对齐等保 2.0 五级保护对象。

变更：
  soc_assets:
    + business_impact   VARCHAR(20) NOT NULL DEFAULT 'normal'
    + data_sensitivity  VARCHAR(20) NOT NULL DEFAULT 'medium'
    + protection_level  VARCHAR(20) NOT NULL DEFAULT 'level_2'
    ~ criticality 标记 DEPRECATED（6 个月过渡期后由后续迁移 DROP）

  soc_business_systems:
    + business_impact   VARCHAR(20) NOT NULL DEFAULT 'normal'
    + data_sensitivity  VARCHAR(20) NOT NULL DEFAULT 'medium'
    + protection_level  VARCHAR(20) NOT NULL DEFAULT 'level_2'
    ~ criticality 标记 DEPRECATED

  soc_dicts:
    + asset_business_impact    5 档字典项
    + asset_data_sensitivity   5 档字典项
    + protection_level         5 档字典项
    + biz_system_business_impact  5 档字典项（业务系统专用）
    ~ asset_criticality  4 档字典项保留（read-only deprecated）

  数据回填：
    根据 app.core.criticality.LEGACY_CRITICALITY_MAP 把旧 criticality 拆到 3 字段：
      critical → BIA=core,         CIA=extreme,    等保=level_3
      high     → BIA=important,    CIA=high,       等保=level_3
      medium   → BIA=normal,       CIA=medium,     等保=level_2
      low      → BIA=auxiliary,    CIA=low,        等保=level_2
      core(遗留) → BIA=core,       CIA=extreme,    等保=level_3
      normal(遗留) → BIA=normal,   CIA=medium,     等保=level_2

幂等保证：每条 DDL/DML 都用 IF NOT EXISTS / WHERE NOT EXISTS 守卫。

设计依据：docs/design/2026-09-14-asset-criticality-three-dimensions.md （本轮同步生成）
CLAUDE.md 上下文：2026-09-14 续三 治本方案第一段
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q9r8s7t6u5v4"
down_revision: Union[str, None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================================
# 字典项 seed 数据（与 app.core.criticality.py 常量对齐，单一来源）
# ============================================================================

_NEW_DICTS = [
    # asset_business_impact 5 档
    ("asset_business_impact", "core",       "核心业务", "danger", 1),
    ("asset_business_impact", "important",  "重要业务", "danger", 2),
    ("asset_business_impact", "normal",     "一般业务", "warning", 3),
    ("asset_business_impact", "auxiliary",  "辅助支撑", "info", 4),
    ("asset_business_impact", "ignorable",  "可忽略",   "info", 5),
    # asset_data_sensitivity 5 档
    ("asset_data_sensitivity", "extreme",    "极高",   "danger", 1),
    ("asset_data_sensitivity", "high",       "高",     "danger", 2),
    ("asset_data_sensitivity", "medium",     "中",     "warning", 3),
    ("asset_data_sensitivity", "low",        "低",     "info", 4),
    ("asset_data_sensitivity", "negligible", "可公开", "info", 5),
    # protection_level 5 档
    ("protection_level", "level_5", "等保五级", "danger", 1),
    ("protection_level", "level_4", "等保四级", "danger", 2),
    ("protection_level", "level_3", "等保三级", "warning", 3),
    ("protection_level", "level_2", "等保二级", "info", 4),
    ("protection_level", "level_1", "等保一级", "info", 5),
    # biz_system_business_impact 5 档（业务系统专用，与 asset BIA 语义一致）
    ("biz_system_business_impact", "core",       "核心业务", "danger", 1),
    ("biz_system_business_impact", "important",  "重要业务", "danger", 2),
    ("biz_system_business_impact", "normal",     "一般业务", "warning", 3),
    ("biz_system_business_impact", "auxiliary",  "辅助支撑", "info", 4),
    ("biz_system_business_impact", "ignorable",  "可忽略",   "info", 5),
]

# 旧 criticality → 新维度回填映射（与 app.core.criticality.LEGACY_CRITICALITY_MAP 同步）
_BACKFILL_MAP = {
    "critical": ("core",      "extreme", "level_3"),
    "high":     ("important", "high",    "level_3"),
    "medium":   ("normal",    "medium",  "level_2"),
    "low":      ("auxiliary", "low",     "level_2"),
    "core":     ("core",      "extreme", "level_3"),  # 遗留值
    "normal":   ("normal",    "medium",  "level_2"),  # 遗留值
}


def upgrade() -> None:
    """升级：加 3 列 + CHECK 约束 + 数据回填 + 新字典 seed。"""
    bind = op.get_bind()

    # ------------------------------------------------------------------------
    # 1. soc_assets 加列 + CHECK 约束
    # ------------------------------------------------------------------------
    for col, default in [
        ("business_impact",  "normal"),
        ("data_sensitivity", "medium"),
        ("protection_level", "level_2"),
    ]:
        bind.execute(sa.text(
            f"ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS {col} VARCHAR(20) "
            f"NOT NULL DEFAULT '{default}'"
        ))
        bind.execute(sa.text(
            f"COMMENT ON COLUMN soc_assets.{col} IS '5 档字段，详见 app.core.criticality.py'"
        ))

    # CHECK 约束（5 档枚举）
    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_business_impact"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets ADD CONSTRAINT ck_soc_assets_business_impact "
        "CHECK (business_impact IN ('core','important','normal','auxiliary','ignorable'))"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_data_sensitivity"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets ADD CONSTRAINT ck_soc_assets_data_sensitivity "
        "CHECK (data_sensitivity IN ('extreme','high','medium','low','negligible'))"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_protection_level"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets ADD CONSTRAINT ck_soc_assets_protection_level "
        "CHECK (protection_level IN ('level_5','level_4','level_3','level_2','level_1'))"
    ))

    # ------------------------------------------------------------------------
    # 2. soc_business_systems 加列 + CHECK 约束
    # ------------------------------------------------------------------------
    for col, default in [
        ("business_impact",  "normal"),
        ("data_sensitivity", "medium"),
        ("protection_level", "level_2"),
    ]:
        bind.execute(sa.text(
            f"ALTER TABLE soc_business_systems ADD COLUMN IF NOT EXISTS {col} VARCHAR(20) "
            f"NOT NULL DEFAULT '{default}'"
        ))
        bind.execute(sa.text(
            f"COMMENT ON COLUMN soc_business_systems.{col} IS '5 档字段，详见 app.core.criticality.py'"
        ))

    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_business_impact"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems ADD CONSTRAINT ck_soc_biz_sys_business_impact "
        "CHECK (business_impact IN ('core','important','normal','auxiliary','ignorable'))"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_data_sensitivity"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems ADD CONSTRAINT ck_soc_biz_sys_data_sensitivity "
        "CHECK (data_sensitivity IN ('extreme','high','medium','low','negligible'))"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_protection_level"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems ADD CONSTRAINT ck_soc_biz_sys_protection_level "
        "CHECK (protection_level IN ('level_5','level_4','level_3','level_2','level_1'))"
    ))

    # ------------------------------------------------------------------------
    # 3. 数据回填：从旧 criticality 推导三维度
    # ------------------------------------------------------------------------
    # soc_assets 回填
    for legacy_val, (bia, cia, pl) in _BACKFILL_MAP.items():
        # CASE 表达式：legacy → 三维度；NULL criticality → 默认
        # 注意：先按 legacy 命中；非命中（NULL 或异常值）保留 DEFAULT 列值即可
        bind.execute(sa.text(
            f"""
            UPDATE soc_assets
            SET business_impact = CASE
                WHEN criticality = :legacy THEN :bia
                ELSE business_impact
            END,
            data_sensitivity = CASE
                WHEN criticality = :legacy THEN :cia
                ELSE data_sensitivity
            END,
            protection_level = CASE
                WHEN criticality = :legacy THEN :pl
                ELSE protection_level
            END
            WHERE criticality = :legacy
            """
        ), {"legacy": legacy_val, "bia": bia, "cia": cia, "pl": pl})

    # soc_business_systems 回填（同映射）
    for legacy_val, (bia, cia, pl) in _BACKFILL_MAP.items():
        bind.execute(sa.text(
            f"""
            UPDATE soc_business_systems
            SET business_impact = CASE
                WHEN criticality = :legacy THEN :bia
                ELSE business_impact
            END,
            data_sensitivity = CASE
                WHEN criticality = :legacy THEN :cia
                ELSE data_sensitivity
            END,
            protection_level = CASE
                WHEN criticality = :legacy THEN :pl
                ELSE protection_level
            END
            WHERE criticality = :legacy
            """
        ), {"legacy": legacy_val, "bia": bia, "cia": cia, "pl": pl})

    # ------------------------------------------------------------------------
    # 4. 新字典 seed（4 个 dict_type × 5 档 = 20 条）
    # ------------------------------------------------------------------------
    for dict_type, dict_code, dict_label, color, sort_order in _NEW_DICTS:
        bind.execute(sa.text(
            """
            INSERT INTO soc_dicts (
                dict_type, dict_code, dict_label, color, sort_order,
                is_active, is_default, created_at, updated_at
            )
            SELECT :dict_type, :dict_code, :dict_label, :color, :sort_order,
                   true, false, now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_dicts
                WHERE dict_type = :dict_type AND dict_code = :dict_code
            )
            """
        ), {
            "dict_type": dict_type,
            "dict_code": dict_code,
            "dict_label": dict_label,
            "color": color,
            "sort_order": sort_order,
        })


def downgrade() -> None:
    """降级：删新列 + CHECK 约束 + 新字典；保留 criticality 列。"""

    # 1. 删字典项（4 个新 dict_type 全删）
    for dict_type in (
        "asset_business_impact",
        "asset_data_sensitivity",
        "protection_level",
        "biz_system_business_impact",
    ):
        bind.execute(sa.text(
            "DELETE FROM soc_dicts WHERE dict_type = :dt"
        ), {"dt": dict_type})

    # 2. soc_assets 删列（顺序：CHECK 先，列后）
    for col in ("business_impact", "data_sensitivity", "protection_level"):
        bind.execute(sa.text(
            f"ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_{col}"
        ))
        bind.execute(sa.text(
            f"ALTER TABLE soc_assets DROP COLUMN IF EXISTS {col}"
        ))

    # 3. soc_business_systems 删列
    for col in ("business_impact", "data_sensitivity", "protection_level"):
        bind.execute(sa.text(
            f"ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_{col}"
        ))
        bind.execute(sa.text(
            f"ALTER TABLE soc_business_systems DROP COLUMN IF EXISTS {col}"
        ))
