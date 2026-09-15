"""业务系统责任人改自由文本 + 联系电话（v1.1，2026-09-14）

用户反馈：业务系统责任人可能不是 SOC 平台用户，owner_id FK 强约束不合适；
且安全应急要能联系到责任人，需新增联系电话。

变更（soc_business_systems）：
  - 新增 owner          VARCHAR(255)  责任人姓名（自由文本，可不填平台用户）
  - 新增 owner_contact  VARCHAR(50)   责任人联系电话

owner_id / department_id 列保留（FK 关联，可选），不再作为表单主推字段。
模型侧 owner relationship 已改名 owner_user，腾出 owner 给文本列（对齐 asset 模式）。

Revision ID: v7w8x9y0z1a2
Revises: u5v6w7x8y9z0
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v7w8x9y0z1a2"
down_revision: Union[str, Sequence[str], None] = "u5v6w7x8y9z0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # 幂等：仅当列不存在时新增
    bind.execute(sa.text("""
        ALTER TABLE soc_business_systems
        ADD COLUMN IF NOT EXISTS owner VARCHAR(255)
    """))
    bind.execute(sa.text("""
        ALTER TABLE soc_business_systems
        ADD COLUMN IF NOT EXISTS owner_contact VARCHAR(50)
    """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        ALTER TABLE soc_business_systems
        DROP COLUMN IF EXISTS owner_contact
    """))
    bind.execute(sa.text("""
        ALTER TABLE soc_business_systems
        DROP COLUMN IF EXISTS owner
    """))
