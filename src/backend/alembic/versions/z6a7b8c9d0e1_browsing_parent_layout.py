"""fix /browsing parent menu component (2026-09-06, 入口跳转修复配套)

现象：资产管理-列表点 IP 跳 /browsing/profile/index 报「访问的页面不存在」。
根因：id=22「上网行为」父菜单 component=NULL，导致子路由没被 Layout 包裹。
其它父菜单（/assets / /system / /ops 等）component='/index/index'，本菜单漏配。

修法（沿用 /assets 同款 UPDATE … WHERE）：把 component 改成 /index/index。

幂等：WHERE id=22 AND component IS NULL → 已修过的库跳过。

不改：
  - parent name='行为检测' → '上网行为'（CLAUDE.md 既有遗留；UI 标题走 meta.title='上网行为'）
  - 子菜单 7 项保持不变
  - 父菜单 sort_order/icon/path 不动

Revision ID: z6a7b8c9d0e1
Revises: y4z5a6b7c8d9
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # 沿用 /assets / /system 同款：父菜单 component = /index/index（Layout 包裹）
    bind.execute(sa.text(
        "UPDATE soc_menus SET component = '/index/index', updated_at = NOW() "
        "WHERE id = 22 AND component IS NULL"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE soc_menus SET component = NULL, updated_at = NOW() "
        "WHERE id = 22 AND component = '/index/index'"
    ))