"""占位迁移：连接 dev testdb 独有 head (i5d6e7f8a9b0) 到 102 prod head (4d5e6f7a8b9c)

背景
----
本迁移**仅在生产 102 (AI-miniSOC-db) 上执行**，目的：

1. dev testdb 在 2026-10-05 跑过多个 agent commit（OH-5.x / OH-UI.10 / OH-2.8），
   这些 commit 在 dev 上 alembic head 是 i5d6e7f8a9b0。
2. 但是 102 prod DB 从 2026-09 之后没自动部署过这些 commit（self-hosted runner
   CD 异常导致 master 与 102 偏离 17 个 commit）。
3. admin 菜单授权补齐迁移 j6a7b8c9d0e1_admin_menu_backfill 的 down_revision
   写的是 dev 的 i5d6e7f8a9b0，102 上文件系统中没这个迁移，导致 alembic 报错
   KeyError: 'i5d6e7f8a9b0'，102 上无法升级。
4. 本迁移是**无操作 (no-op)** —— 它把 102 的迁移链接到 dev 的 i5d6e7f8a9b0，
   让 alembic 后续能从 4d5e6f7a8b9c 沿状态推进到 j6a7b8c9d0e1。
5. **生产 102 不需要重做 dev 的 14 个迁移的副作用** —— dev 的迁移改的表 / 字段
   在 102 上不存在或不同，我们只关心 admin menu_backfill 这个无害 INSERT
   (CLAUDE.md §4.3 红线：NOT EXISTS 守卫幂等)。

这是临时桥接迁移，**在 dev 上不应执行**（dev 已经有 i5d6e7f8a9b0 这个真实迁移
且通过 alembic heads 能解析）。

退场方案：当 102 prod 跑一次 master 全量 alembic upgrade head 后（即 102 的迁移
链追上 dev 的链），这个 dummy 迁移在生产 DB 上的 alembic_version 就被跳过；
后续 dev 上有新的迁移 head，再 cherry-pick 上来时，本迁移就废弃（因为新的
迁移 down_revision 会指向 dev 链最新 head）。届时删除本迁移文件。

Revision ID: 2026_xx_dev_branch_marker
Revises: 4d5e6f7a8b9c
Create Date: 2026-10-06 00:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "2026_xx_dev_branch_marker"
down_revision: Union[str, Sequence[str], None] = "4d5e6f7a8b9c"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    # no-op: 仅给 alembic 一个 dummy revision 让 chain 不断
    pass


def downgrade() -> None:
    # no-op
    pass