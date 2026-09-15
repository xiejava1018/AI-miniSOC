"""
修复字典表 is_default NULL（q9r8s7t6u5v4 seed 遗漏列）

背景：q9r8s7t6u5v4_criticality_three_dimensions.py 在 seed 新字典项时只显式
给了 is_active，没给 is_default，导致 20 条新字典 is_default 为 NULL。

触发：soc_dicts.is_default 列 nullable=True，DictBase schema 声明 is_default: bool（非 Optional），
DB 层 NULL 在 model_validate 时报「Input should be a valid boolean」，
前端 dictStore 取不到 /dicts/{type}/items，菜单树渲染挂掉。

修复：
1. UPDATE 把现有 NULL 补为 false（DB 层）
2. ALTER COLUMN 设置 NOT NULL DEFAULT false（schema 层，杜绝后患）

幂等：WHERE IS NULL 守卫。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r4s5t6u7v8w9"
down_revision: Union[str, None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 补 NULL（防已有数据报 bool_type）
    bind.execute(sa.text(
        "UPDATE soc_dicts SET is_default = false WHERE is_default IS NULL"
    ))
    bind.execute(sa.text(
        "UPDATE soc_dicts SET is_active = true WHERE is_active IS NULL"
    ))

    # 2. 列改为 NOT NULL DEFAULT（schema 层杜绝后患）
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_default SET DEFAULT false"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_active SET DEFAULT true"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_default SET NOT NULL"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_active SET NOT NULL"
    ))


def downgrade() -> None:
    bind = op.get_bind()

    # 恢复 NULLABLE（反向兼容）
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_default DROP NOT NULL"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_active DROP NOT NULL"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_default DROP DEFAULT"
    ))
    bind.execute(sa.text(
        "ALTER TABLE soc_dicts ALTER COLUMN is_active DROP DEFAULT"
    ))
