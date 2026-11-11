"""空库安装修复：soc_alert_group_analyses 列集与 ORM 模型对齐

事故背景
--------
CLAUDE.md §4.3 红线 6 要求「空库 `upgrade head` 必须能跑通」。2026-11-10
按此要求在真·空库上验证时，发现 `alembic upgrade head` 失败：

    sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn)
    column "linked_asset_id" referenced in foreign key constraint does not exist
    [SQL: ALTER TABLE soc_alert_group_analyses
          ADD CONSTRAINT soc_alert_group_analyses_linked_asset_id_fkey
          FOREIGN KEY (linked_asset_id) REFERENCES soc_assets(id) ON DELETE SET NULL]

根因
----
两张表用了两套不同的列定义：

1. ``e2f3a4b5c6d7_create_alert_and_browsing_tables`` 用裸 SQL 建表：

       CREATE TABLE IF NOT EXISTS soc_alert_group_analyses (
           id, fingerprint, priority, is_noise, suggest_incident,
           verdict_at, ai_model, explanation, created_at
       )

   —— 只有 9 列，**缺 linked_asset_id**，而且多出 verdict_at / ai_model /
   explanation 三个 ORM 模型里根本不存在的列。

2. ORM 模型 ``app/models/alert_group_analysis.py`` 定义的是另一套 17 列。

因为建表语句带 ``IF NOT EXISTS``：

- **老库**（本地 dev testdb、生产 102）：表早已被 ``metadata.create_all()``
  按 ORM 模型建好 → 迁移的 CREATE 被跳过 → 列集正确 → 一切正常。
- **空库**：表还不存在 → 迁移的 CREATE 生效 → 列集缺 linked_asset_id →
  后续 ``e3f4a5b6c7d8``（重建 linked_asset_id 外键为 ON DELETE SET NULL）
  直接报 UndefinedColumn → **整条 upgrade 链在第 73 步断掉**。

这正是 CLAUDE.md §4.3 红线 6 说的「生产库能用只因 schema 是手工建的，
不代表迁移链完整」的另一个变体 —— 老库掩盖了迁移链的缺陷。

本迁移做什么
------------
把 ``soc_alert_group_analyses`` 的列集补齐到 **ORM 模型的定义**：

- 缺失列 → ``ADD COLUMN IF NOT EXISTS``（幂等）
- ORM 里不存在的遗留列（verdict_at / ai_model / explanation）→ 保留不动
  （可能有生产数据，且 DROP COLUMN 属破坏性操作；用注释标注为遗留列）
- 补列后加 FK（ON DELETE SET NULL）+ 索引

这样空库和老库的列集都能满足 ORM 模型，且 ``e3f4a5b6c7d8`` 能正常跑完。

为什么不改 e2f3a4b5c6d7
--------------------
已发布的迁移文件不可修改（会破坏迁移链的不可变性，且对已 stamp 的生产库
无效 —— 生产库不会重跑它）。新迁移挂在 head 下游是唯一安全的补齐方式。

顺序说明
--------
本迁移挂在 ``m1n2o3p4q5r7`` 之后，而 ``e3f4a5b6c7d8`` 在链上更早 —— 这
意味着**空库跑到 e3f4a5b6c7d8 时仍会失败**。

因此本迁移必须同时做两件事：
  1. 补列（让**已经跑过 e3f4a5b6c7d8** 的库——本地/生产——保持正确）
  2. **并且**修正 e3f4a5b6c7d8 的失败点

修正方式：把「补列」逻辑做成一个可被 e3f4a5b6c7d8 之前调用的形式是不现实的
（不能改历史迁移）。因此正确做法是 —— **本迁移的 revision 必须排在
e3f4a5b6c7d8 之前**。

但链上 e3f4a5b6c7d8 的位置由历史决定，不能移动。

最终方案：新增一个**独立于主链位置**的修复迁移，并把它的 down_revision
挂在 e3f4a5b6c7d8 的**上游**是不可能的 —— 所以退而求其次：
让本迁移**在 e3f4a5b6c7d8 之前生效**的唯一办法是修改 e3f4a5b6c7d8 使其在
列不存在时**先补列再重建 FK**。

由于 e3f4a5b6c7d8 在**所有已部署的库**上都已经跑过（alembic_version 已过该
节点），修改它的 upgrade() 只会影响**空库**（唯一还会执行它的场景）。
这是安全的、且正是问题所在。因此本迁移采用：
  - **主迁移**（本文件，挂在 head 下游）：补列 + 加 FK + 幂等
  - 同时**修改 e3f4a5b6c7d8**：在其 ALTER 前加「列不存在则先 ADD COLUMN」，
    使空库能顺利跑过该步

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r7
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n2o3p4q5r6s7"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "soc_alert_group_analyses"

# ORM 模型 app/models/alert_group_analysis.py 的完整列集。
# 格式：(列名, DDL 类型, 是否 NOT NULL, 默认值 SQL 或 None)
# 注意：NOT NULL 列必须带默认值，否则已有数据行会因 NOT NULL 校验失败。
_MODEL_COLUMNS: list[tuple[str, str, bool, str | None]] = [
    ("rule_id", "VARCHAR(64)", False, None),
    ("agent_id", "VARCHAR(64)", False, None),
    ("rule_description", "TEXT", False, None),
    ("confidence", "DOUBLE PRECISION", True, "0"),
    ("rationale", "TEXT", False, None),
    ("recommended_action", "TEXT", False, None),
    ("source", "VARCHAR(16)", True, "'heuristic'"),
    ("model_name", "VARCHAR(50)", False, None),
    ("window_hours", "INTEGER", False, None),
    ("linked_asset_id", "UUID", False, None),
    ("expires_at", "TIMESTAMPTZ", False, None),
]


def _table_exists(bind) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :t LIMIT 1"
        ),
        {"t": _TABLE},
    ).fetchone()
    return row is not None


def _column_exists(bind, column: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "  AND table_name = :t AND column_name = :c LIMIT 1"
        ),
        {"t": _TABLE, "c": column},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind):
        # 表都不存在说明整条链没跑到这，正常情况下 e2f3a4b5c6d7 已建好。
        # 这里显式建一张与 ORM 完全一致的表，避免后续迁移再踩空。
        bind.execute(
            sa.text(
                """
                CREATE TABLE IF NOT EXISTS soc_alert_group_analyses (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    fingerprint VARCHAR(255) NOT NULL UNIQUE,
                    rule_id VARCHAR(64),
                    agent_id VARCHAR(64),
                    rule_description TEXT,
                    priority VARCHAR(4) NOT NULL DEFAULT 'P3',
                    is_noise BOOLEAN NOT NULL DEFAULT FALSE,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                    rationale TEXT,
                    recommended_action TEXT,
                    suggest_incident BOOLEAN NOT NULL DEFAULT FALSE,
                    source VARCHAR(16) NOT NULL DEFAULT 'heuristic',
                    model_name VARCHAR(50),
                    window_hours INTEGER,
                    linked_asset_id UUID REFERENCES soc_assets(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ
                )
                """
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_soc_alert_group_analyses_fingerprint "
                "ON soc_alert_group_analyses (fingerprint)"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_soc_alert_group_analyses_linked_asset_id "
                "ON soc_alert_group_analyses (linked_asset_id)"
            )
        )
        return

    # 表存在 —— 逐列比对 ORM 模型，缺哪补哪
    for column, ddl_type, not_null, default in _MODEL_COLUMNS:
        if _column_exists(bind, column):
            continue
        default_clause = f" DEFAULT {default}" if default is not None else ""
        null_clause = " NOT NULL" if not_null else ""
        bind.execute(
            sa.text(
                f"ALTER TABLE {_TABLE} "
                f"ADD COLUMN IF NOT EXISTS {column} {ddl_type}{null_clause}{default_clause}"
            )
        )

    # linked_asset_id 的 FK（ON DELETE SET NULL）+ 索引
    bind.execute(
        sa.text(
            "DO $$ BEGIN "
            "  IF NOT EXISTS ("
            "    SELECT 1 FROM pg_constraint "
            "    WHERE conname = 'soc_alert_group_analyses_linked_asset_id_fkey'"
            "  ) THEN "
            "    ALTER TABLE soc_alert_group_analyses "
            "    ADD CONSTRAINT soc_alert_group_analyses_linked_asset_id_fkey "
            "    FOREIGN KEY (linked_asset_id) REFERENCES soc_assets(id) ON DELETE SET NULL; "
            "  END IF; "
            "END $$;"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_soc_alert_group_analyses_linked_asset_id "
            "ON soc_alert_group_analyses (linked_asset_id)"
        )
    )


def downgrade() -> None:
    """回滚只删本迁移新增的列。

    ⚠️ 遗留列 verdict_at / ai_model / explanation 是 e2f3a4b5c6d7 建的，
    本迁移不负责删它们（老库可能有生产数据）。
    """
    bind = op.get_bind()
    if not _table_exists(bind):
        return

    for column in (
        "expires_at", "linked_asset_id", "window_hours", "model_name",
        "source", "recommended_action", "rationale", "confidence",
        "rule_description", "agent_id", "rule_id",
    ):
        # NOT NULL 且无默认值的列不能直接 DROP（有数据时会失败）→ 跳过
        if column in ("confidence", "source"):
            continue
        bind.execute(
            sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS {column}")
        )
