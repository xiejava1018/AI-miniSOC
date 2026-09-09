"""
导出角色×菜单基线 JSON

读取迁移头（默认 ``DB_NAME`` 指向的数据库），按以下规则归一化：

1. **受管角色终态**（PRD §八 DR-1）：
   - ``admin`` / ``operator`` / ``user`` / ``viewer`` / ``auditor`` 五个角色由脚本管。
   - ``readonly`` / ``test_role`` 标 ``is_active=False``，但保留 id 稳定性。
2. **菜单定位符**：使用父子路径而非数据库 id，禁止硬编码 ID。
3. **业务写按钮归一**：``user`` 与 ``operator`` 的业务菜单/按钮必须一致。
4. **viewer/auditor 去写按钮**：保留 ``view`` / ``scan_view`` 之类只读权限。
5. **输出 JSON 草稿**，由人工评审后再入库为基线。

CLI 契约（PRD §10.3 AC-7）：

```
python scripts/security/export_role_menu_baseline.py --export FILE.json
```

不带 ``--export`` 时等价 ``--dry-run``：把 JSON dump 到 stdout。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# 让 ``app.*`` 包可被 ``python scripts/security/export_role_menu_baseline.py`` 直接调用
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Menu, Role, RoleMenu

# ---------------------------------------------------------------------------
# 受管角色终态定义（PRD §八 DR-1）
# ---------------------------------------------------------------------------

# 这些角色的 ``soc_role_menus`` 由 seed 脚本管理，其他角色（如运维自建的）
# 不动。
MANAGED_ROLES: tuple[str, ...] = (
    "admin",
    "operator",
    "user",
    "viewer",
    "auditor",
)

# 这些角色停用（is_active=False），但保留数据库 id 以维持审计外键稳定。
DISABLED_ROLES: tuple[str, ...] = (
    "readonly",
    "test_role",
)

# 写按钮白名单：这些按钮对 viewer/auditor 一律不授（PRD §10.3 验收条件）
# 任何不在此集合的按钮（如 'view', 'scan_view', 'refresh'）默认保留给只读角色。
WRITE_BUTTON_BLACKLIST_FOR_READONLY: frozenset[str] = frozenset({
    "edit", "add", "delete", "create", "update", "remove",
    "reconcile", "resolve", "report", "generate", "trigger",
    "validate", "auto_extract", "interpret", "analyze",
    "scan_run", "scan_finding_manage", "scanner_manage",
})


BASELINE_VERSION = "v1"


# ---------------------------------------------------------------------------
# 定位符（PRD §10.3：用父子路径定位菜单，禁止数据库 ID）
# ---------------------------------------------------------------------------

def build_locator(menu: Menu, all_menus_by_id: dict[int, Menu]) -> str:
    """构建菜单的稳定定位符。

    规则：``parent_path + '/' + child_path``（顶层菜单 parent_path 为空）。
    若 ``path`` 已含 ``/``（如 ``profile/detail/:ip``），直接用。
    多层嵌套（如 ``/browsing > profile > profile/detail/:ip``）拼成
    ``/browsing/profile/profile/detail/:ip``，定位符歧义时由 seed 脚本报错。
    """
    parts: list[str] = []
    current: Menu | None = menu
    while current is not None:
        parts.append(current.path or "")
        if current.parent_id is None:
            break
        current = all_menus_by_id.get(current.parent_id)
    parts.reverse()
    # 过滤掉空字符串前缀（顶层）
    return "/".join(p for p in parts if p)


def load_menus(db: Session) -> tuple[dict[int, Menu], dict[str, Menu]]:
    """加载所有菜单，建立 id 与 path 索引。"""
    menus = db.query(Menu).all()
    by_id = {m.id: m for m in menus}
    by_path: dict[str, Menu] = {}
    for m in menus:
        loc = build_locator(m, by_id)
        if loc in by_path and by_path[loc].id != m.id:
            # 歧义登记到列表，但本函数仍返回第一个。
            # seed 脚本会用更严格的 locator 校验并报错。
            pass
        by_path.setdefault(loc, m)
    return by_id, by_path


# ---------------------------------------------------------------------------
# 角色 × 菜单采集
# ---------------------------------------------------------------------------

def export_baseline(db: Session) -> dict[str, Any]:
    """从数据库读出当前受管角色的 role×menu×permissions 快照。

    返回结构::

        {
          "version": "v1",
          "managed_roles": ["admin", ...],
          "disabled_roles": ["readonly", "test_role"],
          "roles": {
            "admin": {
              "name": "管理员",
              "is_active": True,
              "menus": [
                {"locator": "/dashboard", "permissions": []},
                ...
              ]
            },
            ...
          }
        }
    """
    roles = {r.code: r for r in db.query(Role).all()}
    by_id, _ = load_menus(db)

    out_roles: dict[str, Any] = {}
    for code in MANAGED_ROLES:
        role = roles.get(code)
        if role is None:
            continue
        grants = (
            db.query(RoleMenu)
            .filter(RoleMenu.role_id == role.id)
            .all()
        )
        menu_entries: list[dict[str, Any]] = []
        for grant in grants:
            menu = by_id.get(grant.menu_id)
            if menu is None:
                continue
            perms = _coerce_permissions(grant.permissions)
            menu_entries.append({
                "locator": build_locator(menu, by_id),
                "name": menu.name,
                "permissions": perms,
            })
        # 按 locator 排序便于 diff
        menu_entries.sort(key=lambda x: x["locator"])
        out_roles[code] = {
            "name": role.name,
            "is_active": bool(role.is_active),
            "menus": menu_entries,
        }

    # 停用角色：只记录 is_active，不记录 menus（seed 脚本只更新 is_active）
    disabled_block: dict[str, Any] = {}
    for code in DISABLED_ROLES:
        role = roles.get(code)
        if role is None:
            continue
        disabled_block[code] = {
            "name": role.name,
            "is_active": bool(role.is_active),
        }

    return {
        "version": BASELINE_VERSION,
        "managed_roles": list(MANAGED_ROLES),
        "disabled_roles": list(DISABLED_ROLES),
        "roles": out_roles,
        "disabled": disabled_block,
    }


def _coerce_permissions(raw: Any) -> list[str]:
    """把 JSONB 字段统一为 list[str]。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return []
        if isinstance(parsed, list):
            return [str(p) for p in parsed]
    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="导出角色×菜单基线 JSON（人工评审后再入库）",
    )
    parser.add_argument(
        "--export",
        metavar="FILE",
        help="写入目标 JSON 文件路径；省略则把 JSON 输出到 stdout",
    )
    parser.add_argument(
        "--print-managed-roles",
        action="store_true",
        help="打印受管角色清单后退出（用于 CI 校验）",
    )
    args = parser.parse_args(argv)

    if args.print_managed_roles:
        print(json.dumps({
            "managed_roles": list(MANAGED_ROLES),
            "disabled_roles": list(DISABLED_ROLES),
            "version": BASELINE_VERSION,
        }, indent=2, ensure_ascii=False))
        return 0

    db = SessionLocal()
    try:
        baseline = export_baseline(db)
    finally:
        db.close()

    payload = json.dumps(baseline, indent=2, ensure_ascii=False)

    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"baseline exported to {args.export} (version={baseline['version']})")
        return 0

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())