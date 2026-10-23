"""menu_dedupe — 清除同 (parent_id, path) 的重复菜单行

背景（GitHub issue #12）：
菜单基线 k0m1n2o3p4q5 一次性种入完整 61 行菜单树，随后链上各迁移继续
重命名 / 重排 / 搬移子菜单。其中若干迁移的写法是「无脑搬」或「无脑种」，
不检查目标父菜单下是否已存在同名 path，于是产生重复行：

  - j1k2l3m4n5o6  把 task-center 从 /system 搬到 /ops，而基线已在 /ops 下种了一份
  - i4j5k6l7m8n9 在 /config 下种 config-center / ai-provider / data-source，
                而基线同样已种

重复行的危害不是「多一行数据」，而是前端按菜单生成动态路由：
同 (parent, path) 出现两次 → 注册出两条一模一样的路由 → 路由匹配歧义，
表现就是「点菜单进不去 / 跳 500」。

修法：
在本迁移（链尾，紧跟所有菜单搬运迁移之后）统一去重：
同 (parent_id, path) 只保留 id 最小（最早插入、生产库原生的那一行），
其余连同其 soc_role_menus 授权一并删除。

为什么放在链尾而不是逐个改上游迁移：
  - 上游迁移共 90+ 个，逐个改风险高、易漏；
  - 去重是幂等且与业务语义无关的「收口」动作，放链尾一次做干净最稳；
  - 保留 min(id) 意味着优先保留生产库原生行，管理员在「菜单管理」页
    对较新那行的调整会丢失 —— 但这在生产上不会发生，因为生产早已跑完
    这些迁移（alembic_version 已过本 revision 之前的位置），
    本迁移对生产是零行可删的 no-op。

Revision ID: n0b1c2d3e4f5
Revises: g3h4i5j6k7l8
Create Date: 2026-10-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "g3h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 先删重复行的授权（soc_role_menus 无级联，手动清，避免留孤儿授权）
    bind.execute(sa.text("""
        DELETE FROM soc_role_menus
        WHERE menu_id IN (
            SELECT id FROM soc_menus
            WHERE id NOT IN (
                SELECT min(id) FROM soc_menus
                GROUP BY parent_id, path
            )
        )
    """))

    # 2) 再删重复的菜单行本身
    bind.execute(sa.text("""
        DELETE FROM soc_menus
        WHERE id NOT IN (
            SELECT min(id) FROM soc_menus
            GROUP BY parent_id, path
        )
    """))


def downgrade() -> None:
    # 去重不可逆（行内容已丢失），保持 no-op。
    pass