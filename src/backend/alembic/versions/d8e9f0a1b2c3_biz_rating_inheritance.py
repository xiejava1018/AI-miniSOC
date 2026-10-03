"""biz rating inheritance (设计 §4，T5 · OH-4.14 前置)

业务系统 × 资产管理 × 定级备案模型完善：
  1. soc_assets.protection_level_source        等级来源标记 inherited/manual
  2. soc_business_systems 定级字段 ×5：
       suggested_protection_level / suggestion_basis / rating_status /
       rating_confirmed_by / rating_confirmed_at
  3. backfill：已人工设定非默认等级的系统 → rating_status='confirmed'
  4. asset_business_role 字典种子 8 行（role 枚举化，D8）

设计依据：docs/design/2026-10-03-业务系统资产模型与定级继承设计.md
幂等：全部 IF NOT EXISTS / WHERE NOT EXISTS，可重跑。

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f10a2b
Create Date: 2026-10-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f10a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PL_VALUES = "('level_5','level_4','level_3','level_2','level_1')"

# asset_business_role 字典种子（D8）：值与 schemas/business_system.py 枚举一致
_ROLE_DICT_ROWS = [
    ("asset_business_role", "web",     "Web 层",   "info",    1),
    ("asset_business_role", "app",     "应用层",   "primary", 2),
    ("asset_business_role", "db",      "数据层",   "warning", 3),
    ("asset_business_role", "mq",      "消息队列", "info",    4),
    ("asset_business_role", "cache",   "缓存层",   "info",    5),
    ("asset_business_role", "gateway", "网关接入", "danger",  6),
    ("asset_business_role", "lb",      "负载均衡", "info",    7),
    ("asset_business_role", "other",   "其他",     "info",    8),
]


def upgrade() -> None:
    bind = op.get_bind()

    # --- ① soc_assets.protection_level_source ---
    bind.execute(sa.text(
        """
        ALTER TABLE soc_assets
          ADD COLUMN IF NOT EXISTS protection_level_source VARCHAR(12)
          NOT NULL DEFAULT 'manual'
        """
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_pl_source"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets ADD CONSTRAINT ck_soc_assets_pl_source "
        "CHECK (protection_level_source IN ('inherited','manual'))"
    ))

    # --- ② soc_business_systems 定级字段 ×5 ---
    bind.execute(sa.text(
        """
        ALTER TABLE soc_business_systems
          ADD COLUMN IF NOT EXISTS suggested_protection_level VARCHAR(20),
          ADD COLUMN IF NOT EXISTS suggestion_basis JSONB,
          ADD COLUMN IF NOT EXISTS rating_status VARCHAR(20) NOT NULL DEFAULT 'unrated',
          ADD COLUMN IF NOT EXISTS rating_confirmed_by VARCHAR(100),
          ADD COLUMN IF NOT EXISTS rating_confirmed_at TIMESTAMPTZ
        """
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_suggested_pl"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems ADD CONSTRAINT ck_soc_biz_sys_suggested_pl "
        "CHECK (suggested_protection_level IS NULL "
        f"OR suggested_protection_level IN {_PL_VALUES})"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_rating_status"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems ADD CONSTRAINT ck_soc_biz_sys_rating_status "
        "CHECK (rating_status IN ('unrated','suggested','confirmed'))"
    ))

    # --- ③ backfill：非默认等级 = 有人工决策痕迹 → confirmed（诚实方向：默认值无人决策过） ---
    bind.execute(sa.text(
        """
        UPDATE soc_business_systems
        SET rating_status = 'confirmed',
            rating_confirmed_at = updated_at
        WHERE protection_level <> 'level_2'
          AND rating_status = 'unrated'
        """
    ))

    # --- ④ asset_business_role 字典种子（幂等，禁硬编码 id——按 (dict_type, dict_code) 判存） ---
    # 列名对齐 soc_dicts 实际 schema：dict_code / color / is_active（无 dict_value/dict_color/status）
    for dict_code, value, label, color, sort in _ROLE_DICT_ROWS:
        bind.execute(sa.text(
            """
            INSERT INTO soc_dicts (dict_type, dict_code, dict_label, color, sort_order, is_active)
            SELECT :dtype, :dcode, :dlabel, :dcolor, :dsort, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_dicts WHERE dict_type = :dtype AND dict_code = :dcode
            )
            """
        ), {"dtype": dict_code, "dcode": value, "dlabel": label,
            "dcolor": color, "dsort": sort})


def downgrade() -> None:
    bind = op.get_bind()

    # 字典行（先于列删除，downgrade 对称）
    for _, value, *_ in _ROLE_DICT_ROWS:
        bind.execute(sa.text(
            "DELETE FROM soc_dicts WHERE dict_type = 'asset_business_role' AND dict_code = :v"
        ), {"v": value})

    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_rating_status"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_business_systems DROP CONSTRAINT IF EXISTS ck_soc_biz_sys_suggested_pl"
    ))
    bind.execute(sa.text(
        """
        ALTER TABLE soc_business_systems
          DROP COLUMN IF EXISTS rating_confirmed_at,
          DROP COLUMN IF EXISTS rating_confirmed_by,
          DROP COLUMN IF EXISTS rating_status,
          DROP COLUMN IF EXISTS suggestion_basis,
          DROP COLUMN IF EXISTS suggested_protection_level
        """
    ))
    # 注意：backfill 的 rating_status 值变更不还原（数据变更不可逆，downgrade 只回滚 schema）

    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS ck_soc_assets_pl_source"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_assets DROP COLUMN IF EXISTS protection_level_source"
    ))
