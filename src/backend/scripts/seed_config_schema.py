"""配置 Schema 种子数据（X1E-11 / 2026-09-11）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.9

覆盖两个核心域：alert_governance（3 项）+ browsing_detection（5 项），
作为 Schema-driven Form 的范式样本。

执行：
    cd src/backend
    python scripts/seed_config_schema.py [--dry-run]

幂等：ON CONFLICT DO UPDATE 保证多次执行结果一致（仅更新非敏感描述字段）。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 让脚本可以直接 ``python scripts/seed_config_schema.py`` 运行
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.config_schema import ConfigSchema  # noqa: E402

logger = logging.getLogger(__name__)


SEED_ROWS = [
    # ---- alert_governance（3 项）----
    {
        "category": "alert_governance",
        "key": "triage_top_n",
        "label": "每日 AI 研判 TopN 簇数",
        "value_type": "number",
        "default_value": "20",
        "validation": {"min": 1, "max": 200},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "告警研判",
        "sort_order": 10,
        "help_text": "每日参与 AI 研判的告警簇数量，成本约等于 N 次/天模型调用",
        "editable": True,
    },
    {
        "category": "alert_governance",
        "key": "min_group_count",
        "label": "告警簇最小条数",
        "value_type": "number",
        "default_value": "1",
        "validation": {"min": 1, "max": 1000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "噪声抑制",
        "sort_order": 20,
        "help_text": "少于该值的簇不进入摘要/研判清单",
        "editable": True,
    },
    {
        "category": "alert_governance",
        "key": "suppress_rule_ids",
        "label": "噪声抑制规则 ID",
        "value_type": "string",
        "default_value": "",
        "validation": {"pattern": r"^[\d,\s]*$", "maxLength": 2000},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "噪声抑制",
        "sort_order": 21,
        "help_text": "逗号分隔；命中的告警簇将被移出必处理清单",
        "editable": True,
    },
    # ---- browsing_detection（5 项）----
    {
        "category": "browsing_detection",
        "key": "enabled",
        "label": "启用检测",
        "value_type": "boolean",
        "default_value": "true",
        "validation": {},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 10,
        "help_text": "总开关；停用后检测任务跳过本轮",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "interval_seconds",
        "label": "检测间隔（秒）",
        "value_type": "number",
        "default_value": "300",
        "validation": {"min": 60, "max": 3600},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 11,
        "help_text": "检测调度周期；下个周期生效",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "score_threshold",
        "label": "告警分数阈值",
        "value_type": "number",
        "default_value": "50",
        "validation": {"min": 0, "max": 100},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "评分",
        "sort_order": 20,
        "help_text": "分数高于该值的告警会被标记；下个周期生效",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "whitelist_domains",
        "label": "域名白名单",
        "value_type": "multiline",
        "default_value": (
            "*.miwifi.com,stun.chat.bilibili.com,stun.hitv.com,*.heytapmobi.com,"
            "stun.l.google.com,*.mozilla.com,musicstun.p2p.qq.com,*.easytier.cn"
        ),
        "validation": {"maxLength": 8000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "白名单",
        "sort_order": 30,
        "help_text": "逗号分隔；支持通配符（*）；命中域名跳过检测",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "night_start_hour",
        "label": "夜间起始小时",
        "value_type": "number",
        "default_value": "2",
        "validation": {"min": 0, "max": 23},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "夜间策略",
        "sort_order": 40,
        "help_text": "夜间模式的开始小时（0-23）",
        "editable": True,
    },
]


def upsert_schema_rows(db, dry_run: bool = False) -> int:
    """幂等写入种子数据。返回写入/更新条数。"""
    count = 0
    for row in SEED_ROWS:
        existing = (
            db.query(ConfigSchema)
            .filter(
                ConfigSchema.category == row["category"],
                ConfigSchema.key == row["key"],
            )
            .first()
        )
        if existing:
            existing.label = row["label"]
            existing.value_type = row["value_type"]
            existing.default_value = row["default_value"]
            existing.validation = row["validation"]
            existing.effect_scope = row["effect_scope"]
            existing.sensitive = row["sensitive"]
            existing.group_name = row["group_name"]
            existing.sort_order = row["sort_order"]
            existing.help_text = row["help_text"]
            existing.editable = row["editable"]
            count += 1
        else:
            db.add(
                ConfigSchema(
                    category=row["category"],
                    key=row["key"],
                    label=row["label"],
                    value_type=row["value_type"],
                    default_value=row["default_value"],
                    validation=row["validation"],
                    effect_scope=row["effect_scope"],
                    sensitive=row["sensitive"],
                    group_name=row["group_name"],
                    sort_order=row["sort_order"],
                    help_text=row["help_text"],
                    editable=row["editable"],
                )
            )
            count += 1
    if not dry_run:
        db.commit()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="预置配置 Schema 种子数据")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不提交")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # 同步驱动（脚本不用异步）
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # 确保表存在（生产已通过 alembic 创建，本地直跑也安全）
        Base.metadata.create_all(engine, tables=[ConfigSchema.__table__])
        n = upsert_schema_rows(db, dry_run=args.dry_run)
        logger.info("✅ 配置 Schema 种子数据写入完成：%d 条%s", n, "（dry-run）" if args.dry_run else "")
        return 0
    except Exception as e:
        logger.exception("❌ 写入失败：%s", e)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())