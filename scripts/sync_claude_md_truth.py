#!/usr/bin/env python3
"""
sync_claude_md_truth.py — 自动同步项目硬事实快照

按第一性原理：CLAUDE.md 不应记录任何能机器验证的事实，
而是引用本脚本输出的快照。本脚本从代码/DB/.env 真读，
杜绝手抄过期。

用法：
    cd src/backend && ../../venv/bin/python ../scripts/sync_claude_md_truth.py

输出：
    docs/project-truth/snapshot.md（自动生成，git 跟踪，CI 可校验）

为什么是 .md 不是 .json/yaml：
    - 人能直接读懂
    - diff 在 PR review 里清晰可见
    - 新 CLAUDE.md 用 Markdown 引用块嵌进来，渲染一致
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "src" / "backend"
OUTPUT_PATH = REPO_ROOT / "docs" / "project-truth" / "snapshot.md"


def get_table_count() -> tuple[int, list[str]]:
    """从 SQLAlchemy Base.metadata 真读表数 + 列出非 soc_ 前缀的（如有）"""
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        # 触发所有模型注册到 Base.metadata
        import app.models  # noqa: F401  # 显式 import 让包级 __init__ 执行
        from app.core.database import SessionLocal  # noqa: E402
        from app.models.base import Base  # noqa: E402

        all_tables = sorted(Base.metadata.tables.keys())
        non_soc = [t for t in all_tables if not t.startswith("soc_")]

        # 顺手验证下 DB 真连得上
        try:
            db = SessionLocal()
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            db.close()
            db_ok = True
        except Exception as e:  # noqa: BLE001
            db_ok = False
            print(f"  [warn] DB unreachable: {e}", file=sys.stderr)

        return len(all_tables), non_soc
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] failed to read metadata: {e}", file=sys.stderr)
        return -1, []


def get_alembic_heads() -> list[str]:
    """从 alembic heads 真读 head 列表（多 head 是重要信号）"""
    try:
        result = subprocess.run(
            [
                str(REPO_ROOT / "venv" / "bin" / "python"),
                "-m",
                "alembic",
                "-c",
                "alembic.ini",
                "heads",
            ],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        heads = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # 类似 "r4s5t6u7v8w9 (head)"
            m = re.match(r"^([a-z0-9]+)\s*\(head\)", line)
            if m:
                heads.append(m.group(1))
        return heads
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] alembic heads failed: {e}", file=sys.stderr)
        return []


def get_migration_count() -> int:
    """alembic/versions 下实际迁移文件数（排除 __pycache__）"""
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    if not versions_dir.exists():
        return 0
    return sum(
        1
        for f in versions_dir.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
    )


def get_top_menus() -> list[dict]:
    """从 soc_menus 真读顶级菜单（按 sort_order）"""
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.core.database import SessionLocal  # noqa: E402
        from sqlalchemy import text  # noqa: E402

        db = SessionLocal()
        try:
            rows = db.execute(
                text(
                    "SELECT id, path, component, title, sort_order, is_visible "
                    "FROM soc_menus WHERE parent_id IS NULL ORDER BY sort_order"
                )
            ).fetchall()
        finally:
            db.close()

        return [
            {
                "sort": r[4],
                "path": r[1] or "(无 path)",
                "component": r[2] or "(容器)",
                "title": r[3] or "(无 title)",
                "visible": r[5],
            }
            for r in rows
        ]
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] top menus read failed: {e}", file=sys.stderr)
        return []


def get_x1_roles() -> list[dict]:
    """从 soc_roles 真读角色（含 X1 4 角色）"""
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.core.database import SessionLocal  # noqa: E402
        from sqlalchemy import text  # noqa: E402

        db = SessionLocal()
        try:
            rows = db.execute(
                text(
                    "SELECT id, code, name, is_active FROM soc_roles ORDER BY id"
                )
            ).fetchall()
        finally:
            db.close()

        return [{"id": r[0], "code": r[1], "name": r[2], "active": r[3]} for r in rows]
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] roles read failed: {e}", file=sys.stderr)
        return []


def read_env_keys() -> dict[str, str]:
    """从 src/backend/.env 真读关键键值（不做敏感字段过滤——脚本本身能跑就能读）"""
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return {}

    keys_of_interest = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "WAZUH_API_URL",
        "OPENSEARCH_URL",
        "LOKI_API_URL",
        "BACKEND_PORT",
        "BACKEND_CORS_ORIGINS",
        "GLM_MODEL",
    ]
    result: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for k in keys_of_interest:
            if line.startswith(f"{k}="):
                result[k] = line.split("=", 1)[1].strip()
                break
    return result


def render_snapshot(
    tables: int,
    non_soc_tables: list[str],
    heads: list[str],
    migration_count: int,
    top_menus: list[dict],
    roles: list[dict],
    env_keys: dict[str, str],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# 项目硬事实快照",
        "",
        f"> **自动生成于 {now}** by `scripts/sync_claude_md_truth.py`",
        "> 不要手改——下次跑脚本会被覆盖。发现过期请修脚本或修源数据。",
        "",
        "## 数据库",
        "",
        f"- **业务表总数**: `{tables}`（全部 `soc_` 前缀）",
    ]
    if non_soc_tables:
        lines.append(f"- **非 soc_ 前缀的表**: {', '.join(f'`{t}`' for t in non_soc_tables)}")
    else:
        lines.append("- **非 soc_ 前缀的表**: 无")
    lines.append(f"- **alembic 迁移文件数**: `{migration_count}`")

    lines.append("")
    lines.append("## Alembic heads")
    lines.append("")
    if len(heads) == 0:
        lines.append("- ⚠️  读不到 head（DB 可能未连通）")
    elif len(heads) == 1:
        lines.append(f"- 单 head: `{heads[0]}`（线性 OK）")
    else:
        lines.append(f"- ⚠️  **多 head ({len(heads)})**: " + ", ".join(f"`{h}`" for h in heads))
        lines.append("- 多 head 意味着有未合并的迁移线——升级前必须 merge 或显式选 base")

    lines.append("")
    lines.append("## 顶级菜单（按 sort_order）")
    lines.append("")
    lines.append("| sort | path | component | title | 可见 |")
    lines.append("|---:|---|---|---|:-:|")
    for m in top_menus:
        vis = "✅" if m["visible"] else "❌"
        lines.append(f"| {m['sort']} | `{m['path']}` | `{m['component']}` | {m['title']} | {vis} |")

    lines.append("")
    lines.append("## 角色（X1 权限矩阵）")
    lines.append("")
    lines.append("| id | code | name | 启用 |")
    lines.append("|---:|---|---|:-:|")
    for r in roles:
        active = "✅" if r["active"] else "❌"
        lines.append(f"| {r['id']} | `{r['code']}` | {r['name']} | {active} |")

    lines.append("")
    lines.append("## 部署拓扑（本地 .env 视角）")
    lines.append("")
    if not env_keys:
        lines.append("- ⚠️  .env 不存在或无关键键")
    else:
        for k, v in env_keys.items():
            # password 类敏感字段这里不会出现（keys_of_interest 不包含）
            lines.append(f"- **{k}**: `{v}`")

    lines.append("")
    lines.append("## 生成命令")
    lines.append("")
    lines.append("```bash")
    lines.append("venv/bin/python scripts/sync_claude_md_truth.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"[sync] reading project truth...")

    tables, non_soc = get_table_count()
    print(f"  tables: {tables}, non_soc: {len(non_soc)}")

    heads = get_alembic_heads()
    print(f"  alembic heads: {heads}")

    migration_count = get_migration_count()
    print(f"  migration files: {migration_count}")

    top_menus = get_top_menus()
    print(f"  top menus: {len(top_menus)}")

    roles = get_x1_roles()
    print(f"  roles: {len(roles)}")

    env_keys = read_env_keys()
    print(f"  env keys: {len(env_keys)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = render_snapshot(
        tables, non_soc, heads, migration_count, top_menus, roles, env_keys
    )
    OUTPUT_PATH.write_text(snapshot, encoding="utf-8")
    print(f"\n[sync] wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
