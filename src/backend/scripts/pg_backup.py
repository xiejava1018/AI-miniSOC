#!/usr/bin/env python3
"""
PG 备份脚本（P3-T5 数据可靠性）

基于 SQLAlchemy + psycopg2 的纯 Python 备份工具，跨平台可用（无 pg_dump 依赖）。
- **默认 schema-only**（仅导出表结构，不含数据）—— 这是 P1-T1 / P3-T5 计划的本意，
  也是防止数据 dump 误入 git 的关键。
- 全量（schema + data）备份通过 --full 显式开启；输出到 backups/ 目录（已 gitignore 覆盖）。
- 保留策略：保留最近 N 份
- 调用方式：python scripts/pg_backup.py [--full] [--keep N]

Loki / OpenSearch 的备份不在本脚本范围（各组件自带机制），文档另行说明。

环境：从 src/backend/ 启动以加载 .env。

回滚 / 恢复（手动）：
    psql -h $DB_HOST -U $DB_USER -d $DB_NAME < backups/AI-miniSOC_YYYYMMDD_HHMMSS.sql

⚠️ 教训（2026-08-16 dump 入库事故）：原版此脚本默认全量导出，与下游
`git add` 串联后曾导致 375MB 测试库完整数据进入 git 历史。现默认改为
schema-only，--full 必须显式开启。
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# 让脚本可独立运行
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
load_dotenv(BACKEND_ROOT / ".env")

import psycopg2

DEFAULT_BACKUP_DIR = BACKEND_ROOT / "backups"
DEFAULT_KEEP = 7  # 保留最近 7 份


def get_db_config() -> dict:
    return {
        "host": os.environ.get("DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ.get("DB_NAME", "AI-miniSOC"),
        "user": os.environ.get("DB_USER", "aisoc"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }


def dump_schema_and_data(conn, f, include_data: bool = False) -> None:
    """导出 schema（始终）+ 可选 data（仅当 include_data=True）到 f。

    默认 include_data=False 即 schema-only；这是 P1-T1 计划要求。
    """
    cur = conn.cursor()
    kind = "schema-only" if not include_data else "full (schema + data)"
    f.write(f"-- AI-miniSOC backup ({kind})\n")
    f.write(f"-- Host: {conn.info.host}:{conn.info.port}\n")
    f.write(f"-- DB: {conn.info.dbname}\n")
    f.write(f"-- Generated: {datetime.utcnow().isoformat()}Z\n\n")
    f.write("BEGIN;\n\n")

    # Tables (in dependency order would be ideal; pg_dump does this. For MVP dump by name)
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname='public' AND tablename NOT LIKE 'pg_%' AND tablename NOT LIKE 'sql_%'
        ORDER BY tablename
    """)
    tables = [r[0] for r in cur.fetchall()]

    for t in tables:
        f.write(f"-- Table: {t}\n")
        # CREATE TABLE（基于现有 schema）
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
        """, (t,))
        cols = cur.fetchall()
        if not cols:
            continue
        # 主键
        cur.execute("""
            SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
            WHERE i.indrelid=%s::regclass AND i.indisprimary
        """, (t,))
        pk = [r[0] for r in cur.fetchall()]

        col_defs = []
        for cname, ctype, nullable, default, cmaxlen, nprec, nscale in cols:
            d = ctype.upper()
            if cmaxlen and ctype in ("character varying", "character"):
                d += f"({cmaxlen})"
            elif nprec and ctype == "numeric":
                d += f"({nprec},{nscale})"
            if default:
                d += f" DEFAULT {default}"
            if nullable == "NO" and default is None:
                d += " NOT NULL"
            col_defs.append(f"  {cname} {d}")
        if pk:
            col_defs.append(f"  PRIMARY KEY ({', '.join(pk)})")
        f.write(f"CREATE TABLE IF NOT EXISTS {t} (\n" + ",\n".join(col_defs) + "\n);\n\n")

    # Data（仅当 include_data=True，即 --full）
    if not include_data:
        f.write("\n-- (data export skipped: schema-only mode)\n")
        f.write("\nCOMMIT;\n")
        return

    for t in tables:
        cur.execute(f'SELECT * FROM "{t}"')
        rows = cur.fetchall()
        if not rows:
            continue
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position
        """, (t,))
        col_names = [r[0] for r in cur.fetchall()]
        f.write(f"\n-- Data: {t}\n")
        for row in rows:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                elif isinstance(v, bool):
                    vals.append("true" if v else "false")
                else:
                    s = str(v).replace("'", "''")
                    vals.append(f"'{s}'")
            f.write(f'INSERT INTO "{t}" ({", ".join(col_names)}) VALUES ({", ".join(vals)});\n')

    f.write("\nCOMMIT;\n")


def rotate_backups(backup_dir: Path, keep: int) -> int:
    """按文件名时间戳排序，删除超过 keep 份的旧备份。"""
    files = sorted(backup_dir.glob("AI-miniSOC_*.sql"), reverse=True)
    removed = 0
    for old in files[keep:]:
        old.unlink()
        removed += 1
        print(f"[rotate] removed old backup: {old.name}")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AI-miniSOC PostgreSQL backup（默认 schema-only；--full 开启全量）",
    )
    parser.add_argument("--out", type=str, default=None, help="Output directory (default: ./backups)")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"Keep N recent backups (default: {DEFAULT_KEEP})")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--schema-only",
        action="store_true",
        default=True,
        help="[默认] 仅导出 schema（不含数据）",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="导出 schema + data（请确保输出文件不进入 git）",
    )
    args = parser.parse_args()

    include_data = bool(args.full)

    out_dir = Path(args.out) if args.out else DEFAULT_BACKUP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = get_db_config()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"AI-miniSOC_{ts}.sql"

    kind = "full (schema + data)" if include_data else "schema-only"
    print(f"[backup] connecting to {cfg['host']}:{cfg['port']}/{cfg['dbname']}  mode={kind}")
    conn = psycopg2.connect(**cfg)
    try:
        with open(out_path, "w") as f:
            dump_schema_and_data(conn, f, include_data=include_data)
    finally:
        conn.close()

    size = out_path.stat().st_size
    print(f"[backup] wrote {out_path} ({size} bytes)")

    removed = rotate_backups(out_dir, args.keep)
    print(f"[backup] rotated: {removed} old file(s) removed (keep={args.keep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())