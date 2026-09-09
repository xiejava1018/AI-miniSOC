#!/usr/bin/env python3
"""
清理单条测试残留事件（幂等）

背景
----
2026-09-09 权限体系调研期间，为验证"匿名是否可写"，调用过
``POST /api/v1/alerts/{id}/create-incident``，由此在 ``soc_incidents``
产生了一条非业务数据。incidents 模块无 DELETE 路由，故需走数据库清理。

目标记录
--------
id          938a9a37-cdd5-4a70-9359-25e35b1df4cd
title       [告警] Host Blocked by firewall-drop Active Response
created_by  system
created_at  2026-09-09 16:32:45.183491+08:00

连带影响
--------
``soc_asset_incidents.incident_id`` 外键为 ON DELETE CASCADE，
删除该事件会同时删除 1 行资产-事件关联。

安全特性
--------
* **默认 dry-run**：不指定 ``--commit`` 时只勘察，绝不写库
* **删除前自动备份**：JSON 快照 + 可执行的回滚 SQL
* **事务保护**：核验未通过自动 ROLLBACK
* **幂等**：重复执行无副作用

用法
----
::

    cd src/backend
    ../../venv/bin/python3 scripts/cleanup_test_incident.py              # 只勘察
    ../../venv/bin/python3 scripts/cleanup_test_incident.py --commit     # 实际删除

注意
----
必须从 ``src/backend`` 目录运行，否则加载不到 ``.env``（与后端服务同样约定）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from app.core.config import settings  # noqa: E402

TARGET_ID = "938a9a37-cdd5-4a70-9359-25e35b1df4cd"
EXPECTED_TITLE = "[告警] Host Blocked by firewall-drop Active Response"


def build_engine():
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        client_encoding="utf8",
        connect_args={"connect_timeout": 10},
    )


def probe(conn):
    """返回 (事件是否存在, 关联行数, 事件总数, 标题)"""
    row = conn.execute(
        text("SELECT title FROM soc_incidents WHERE id = CAST(:t AS uuid)"),
        {"t": TARGET_ID},
    ).mappings().first()
    assoc = conn.execute(
        text("SELECT count(*) FROM soc_asset_incidents WHERE incident_id = CAST(:t AS uuid)"),
        {"t": TARGET_ID},
    ).scalar()
    total = conn.execute(text("SELECT count(*) FROM soc_incidents")).scalar()
    return (row is not None), assoc, total, (row["title"] if row else None)


def rows_to_dicts(conn, sql, target):
    return [
        dict(r)
        for r in conn.execute(text(sql), {"t": target}).mappings().all()
    ]


def backup(conn, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    inc = rows_to_dicts(conn, "SELECT * FROM soc_incidents WHERE id = CAST(:t AS uuid)", TARGET_ID)
    assoc = rows_to_dicts(
        conn, "SELECT * FROM soc_asset_incidents WHERE incident_id = CAST(:t AS uuid)", TARGET_ID
    )

    json_path = os.path.join(out_dir, f"deleted_incident_{ts}.json")
    payload = {
        "reason": "2026-09-09 权限调研期间 create-incident 产生的测试残留",
        "incident_id": TARGET_ID,
        "backup_at": ts,
        "soc_incidents": [{k: str(v) if v is not None else None for k, v in r.items()} for r in inc],
        "soc_asset_incidents": [
            {k: str(v) if v is not None else None for k, v in r.items()} for r in assoc
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"   备份 JSON  : {json_path}")

    sql_path = os.path.join(out_dir, f"deleted_incident_{ts}_restore.sql")
    lines = [
        "-- 回滚脚本：恢复被清理的测试残留事件",
        f"-- 生成时间：{ts}",
        "-- 用法：psql -h <host> -p <port> -U <user> -d <db> -f <本文件>",
        "BEGIN;",
    ]

    def insert_stmt(table, row):
        cols = ", ".join(row.keys())
        vals = ", ".join(
            "NULL" if v is None else "'" + str(v).replace("'", "''") + "'" for v in row.values()
        )
        conflict = " (id) DO NOTHING" if table == "soc_incidents" else " DO NOTHING"
        return f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT{conflict};"

    for r in inc:
        lines.append(insert_stmt("soc_incidents", r))
    for r in assoc:
        lines.append(insert_stmt("soc_asset_incidents", r))
    lines.append("COMMIT;")

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"   回滚 SQL  : {sql_path}")
    return json_path


def main() -> int:
    ap = argparse.ArgumentParser(description="清理单条测试残留事件")
    ap.add_argument("--commit", action="store_true", help="实际执行删除（缺省为 dry-run）")
    ap.add_argument("--backup-dir", default="/tmp", help="备份输出目录，默认 /tmp")
    args = ap.parse_args()

    engine = build_engine()
    try:
        with engine.connect() as conn:
            exists, assoc, total, title = probe(conn)
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法连接数据库：{type(e).__name__}: {str(e)[:200]}")
        print("   提示：本脚本必须在 src/backend 目录下运行，以便加载 .env")
        return 1

    print("=== 勘察 ===")
    print(f"   目标 ID      : {TARGET_ID}")
    print(f"   是否存在     : {'是' if exists else '否'}")
    if exists:
        print(f"   标题         : {title}")
        if title != EXPECTED_TITLE:
            print(f"   ⚠️ 标题与预期不符（预期：{EXPECTED_TITLE}）")
            print("      请人工确认后再决定是否删除")
    print(f"   关联行数     : {assoc}（soc_asset_incidents，ON DELETE CASCADE）")
    print(f"   事件总数     : {total}")

    if not exists and assoc == 0:
        print("\n✅ 无残留，无需清理")
        return 0

    if not args.commit:
        print("\n[dry-run] 未执行任何写操作。确认无误后加 --commit 执行删除。")
        return 0

    print("\n=== 执行删除 ===")
    conn = engine.connect()
    try:
        conn.execute(text("SET statement_timeout = '20s'"))
        conn.execute(text("SET lock_timeout = '15s'"))

        backup(conn, args.backup_dir)

        deleted = conn.execute(
            text("DELETE FROM soc_incidents WHERE id = CAST(:t AS uuid) RETURNING id, title"),
            {"t": TARGET_ID},
        ).mappings().all()
        print(f"   DELETE RETURNING {len(deleted)} 行")

        still, assoc_left, total_now, _ = probe(conn)
        if still or assoc_left:
            conn.rollback()
            print(f"   ⚠️ 核验未通过（残留 inc={still} assoc={assoc_left}），已 ROLLBACK")
            return 1

        conn.commit()
        print(f"   ✅ COMMIT：soc_incidents {total} → {total_now}")
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print(f"   ❌ 异常回滚：{type(e).__name__}: {str(e)[:200]}")
        return 1
    finally:
        conn.close()

    print("\n=== 提交后复查 ===")
    with engine.connect() as conn:
        exists, assoc, total_now, _ = probe(conn)
        orphans = conn.execute(
            text("SELECT count(*) FROM soc_asset_incidents ai "
                 "LEFT JOIN soc_incidents i ON i.id = ai.incident_id WHERE i.id IS NULL")
        ).scalar()
    print(f"   目标记录残留     : {1 if exists else 0}  ({'❌ 仍存在' if exists else '✅ 已清除'})")
    print(f"   关联行残留       : {assoc}  ({'❌ 仍存在' if assoc else '✅ 已清除'})")
    print(f"   soc_incidents 总数: {total_now}")
    print(f"   关联表孤儿行     : {orphans}")
    return 0 if not exists and assoc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
