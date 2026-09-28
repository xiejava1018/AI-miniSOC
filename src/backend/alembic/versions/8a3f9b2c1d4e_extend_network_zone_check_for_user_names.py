"""extend network_zone CHECK to accept user-defined lan-main / lan-199

背景（2026-XX-XX）
=================
alembic 迁移 628109e83308 把 soc_assets.network_zone CHECK 从 5 值
（intranet/dmz/office/management/other）改为 8 值
（public/dmz/production/office/dev/management/isolated/unknown）。
迁移执行过程中 DROP 旧 CHECK 后再 UPDATE 现有行的步骤，恰好让
192.168.199.x 网段（11 行）的 network_zone 被设成了用户命名的
lan-199（用户后续明确表示希望保留这个命名——lan-199 对应"独立广播域"
如访客网络）。

但 8 值 CHECK 严格拒写 lan-199 / lan-main：
  - 用户在资产编辑页改 network_segment 时，CHECK 拒；
  - 后续 alembic 回填脚本/scripts/backfill_network_zone.py 的 UPDATE
    也被拒。

为什么不让用户"顺手改回 8 值"？
  - lan-199 是有意为之的网络分段命名（独立广播域），丢失 = 丢失用户语义。

修复
=====
把 CHECK 改成接受 8 值 + 用户已明确命名的两个自定义值：
  - lan-main   （用户对内网主段的命名，11 行 lan-199 同源来自这次重命名）
  - lan-199    （192.168.199.0/24 段独立广播域，11 行）

NOT VALID / VALID 选择：
  - CHECK IMMEDIATE 且对 ADD CONSTRAINT 时的存量行也会校验（PG 默认）；
  - 现存 lan-199 / lan-main 行当前已存在但 CHECK 会拒写它们（5 行 lan-main
    + 11 行 lan-199 = 16 行），ADD CHECK 直接报错；
  - 必须先 DROP 旧 CHECK → ADD 新 CHECK（PG 不会校验已有行，只需新写满足）；
    现有 16 行仍在 8 值之外（lan-199/lan-main），但 ADD 时不报错，
    后续 UPDATE 也满足。
  - 或者用 NOT VALID + VALIDATE 单独步骤：
      ALTER TABLE ... ADD CONSTRAINT ... CHECK (...) NOT VALID;
      ALTER TABLE ... VALIDATE CONSTRAINT ...;
    这种方式在 VALIDATE 阶段会扫存量行，如果现有 16 行不在新枚举里会失败。
    不适合本场景。

本迁移采用：直接 DROP + ADD，不带 NOT VALID。
  - 安全性：CHECK IMMEDIATE 只对未来 INSERT/UPDATE 生效，不重写存量；
  - 现有 16 行（lan-main/lan-199）在 ADD CHECK 步骤里不被校验（PG 行为）；
  - 后续任何 INSERT/UPDATE 都要满足新 CHECK。

顺序（避免 CHECK 拖选1 冲突）：
  1. DROP 旧 CHECK（先释放约束）
  2. ADD 新 CHECK（10 个值，比原 8 值多 lan-main / lan-199）
  3. UPDATE 列 COMMENT（提及新值）

为什么是这 10 个值？
  - 8 值是设计枚举（public/dmz/production/office/dev/management/isolated/unknown）
  - lan-main / lan-199 是用户当前实际在用的命名
  - 未将 lan-199 改为 production 是因为：192.168.199.0/24 是独立广播域，
    与 production（业务核心）语义不同——不能合并。

Revision ID: 8a3f9b2c1d4e
Revises: 628109e83308
Create Date: 2026-XX-XX
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8a3f9b2c1d4e"
down_revision: Union[str, Sequence[str], None] = "628109e83308"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 新 CHECK 接受的 10 个 network_zone 值
# 顺序无影响，但写成 list 让 SQL IN (...) 顺序可读
_NEW_ZONES_SQL = "('public', 'dmz', 'production', 'office', 'dev', 'management', 'isolated', 'unknown', 'lan-main', 'lan-199')"


def upgrade() -> None:
    """扩展 CHECK 接受 lan-main / lan-199。"""
    # Step 1: DROP 旧 CHECK
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")

    # Step 2: ADD 新 CHECK（10 个值）
    # 现有 16 行（5 行 lan-main + 11 行 lan-199）在 DROP 状态下不受约束；
    # ADD CHECK 时 PG 不会校验存量（CHECK IMMEDIATE 只对未来 INSERT/UPDATE 生效）。
    op.execute(
        f"""
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_network_zone_check
        CHECK (network_zone IN {_NEW_ZONES_SQL})
        """
    )

    # Step 3: 列 COMMENT 更新（与 docs/design/network-zone-redesign.md + 本迁移同步）
    op.execute(
        "COMMENT ON COLUMN soc_assets.network_zone IS "
        "'网络区域 8 值设计枚举 + 用户自定义（lan-main/lan-199），"
        "详见 docs/design/network-zone-redesign.md 和 alembic 迁移 8a3f9b2c1d4e'"
    )


def downgrade() -> None:
    """回退：CHECK 退回 8 值严格枚举。

    注意：现有 lan-main / lan-199 行将违反新 CHECK，但 downgrade 不强制
    数据校验——那些行会留在 DB 里直到被人工 UPDATE 回 8 值。
    """
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")
    op.execute(
        "ALTER TABLE soc_assets ADD CONSTRAINT soc_assets_network_zone_check "
        "CHECK (network_zone IN ('public', 'dmz', 'production', 'office', 'dev', 'management', 'isolated', 'unknown'))"
    )
    op.execute(
        "COMMENT ON COLUMN soc_assets.network_zone IS "
        "'网络区域（public/dmz/production/office/dev/management/isolated/unknown），"
        "详见 docs/design/network-zone-redesign.md'"
    )