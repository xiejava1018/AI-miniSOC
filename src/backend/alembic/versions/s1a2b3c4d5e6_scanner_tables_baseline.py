"""scanner_tables_baseline — 补齐 4 张从未进迁移链的扫描器表

背景（GitHub issue #12）：
全新空库执行 `alembic upgrade head` 必挂，报错：

    relation "soc_scanner_tasks" does not exist
    [SQL: ALTER TABLE soc_scanner_tasks ADD COLUMN IF NOT EXISTS affected_ports ...]

根因：`soc_scanner_agents` / `soc_scanner_tasks` / `soc_scan_targets` /
`soc_scan_findings` 四张表只在 ORM（app/models/scanner_models.py）里定义，
生产库是手工建的，**从未进入迁移链**。于是：

- 链上 r1s2t3u4v5w6（给 soc_scanner_tasks 加 affected_ports 列）空库必炸；
- 即使绕过，扫描器/攻击面相关端点也会因表缺失而 500。

修法：
新增本迁移（挂在 q1r2s3t4u5v6 之后、r1s2t3u4v5w6 之前），
用 Base.metadata 局部 CreateTable(if_not_exists) 建这 4 张表，
与 ORM 定义永远一致，避免第三份 schema 漂移（沿用 ab9cd0e1f2a3 / x3y4z5a6b7c8 同款写法）。

幂等：
- IF NOT EXISTS —— 生产库已有这 4 张表时零副作用（不会 drop/recreate 丢数据）；
- 只建表，不插种子数据、不动其它表；
- 对已跑过 head 的库无影响（生产 alembic_version 已记录本 revision 的位置之后）。

注意：下游依赖本迁移的 revision：
- r1s2t3u4v5w6_scan_task_affected_items（soc_scanner_tasks 加列）
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.base import Base
import app.models  # noqa: F401  触发全部 model 注册

# revision identifiers, used by Alembic.
revision: str = "s1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 仅建这 4 张（其余表由链内既有迁移负责）
_TABLES = (
    "soc_scanner_agents",
    "soc_scanner_tasks",
    "soc_scan_targets",
    "soc_scan_findings",
)


def upgrade() -> None:
    for t in _TABLES:
        table = Base.metadata.tables[t]
        op.execute(
            str(CreateTable(table, if_not_exists=True)
                .compile(dialect=postgresql.dialect()))
            .replace("COMMIT", "")
        )


def downgrade() -> None:
    # 扫描任务明细先于任务表删（无硬 FK，仍按依赖顺序保证确定性）
    for t in (
        "soc_scan_findings",
        "soc_scan_targets",
        "soc_scanner_tasks",
        "soc_scanner_agents",
    ):
        op.execute('DROP TABLE IF EXISTS "%s" CASCADE' % t)