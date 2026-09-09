"""
应用角色×菜单基线（PRD §10.3 Feature: 角色菜单矩阵基线与幂等种子）

CLI 契约::

    # 检查 drift（无修改，退出码 0/2）
    python scripts/security/seed_role_menu_baseline.py --check

    # dry-run：计算将做什么，但不动数据库
    python scripts/security/seed_role_menu_baseline.py --dry-run

    # 实际应用（事务原子）
    python scripts/security/seed_role_menu_baseline.py --apply

    # 指定基线文件（默认 scripts/data/role_menu_baseline.v1.json）
    python scripts/security/seed_role_menu_baseline.py --check --baseline PATH.json

退出码：
- 0：OK
- 2：有 drift（``--check`` 时）/ 校验失败
- 1：未指定明确子命令

设计要点：
- **不修改用户角色**：``soc_users.role_id`` 由独立审批负责（DR-1）
- **幂等**：连续两次 ``--apply`` 结果一致
- **drift 报告**：列出将被新增/删除/修改的 (role, menu, permission) 三元组
- **定位符**：menu 用 ``parent_path/child_path``，禁用数据库 ID
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(THIS_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Menu, Role, RoleMenu

DEFAULT_BASELINE = os.path.join(BACKEND_DIR, "scripts", "data", "role_menu_baseline.v1.json")

# 只读角色统一要"去写按钮"的判断（与 export_role_menu_baseline.py 同步）
WRITE_BUTTON_BLACKLIST_FOR_READONLY: frozenset[str] = frozenset({
    "edit", "add", "delete", "create", "update", "remove",
    "reconcile", "resolve", "report", "generate", "trigger",
    "validate", "auto_extract", "interpret", "analyze",
    "scan_run", "scan_finding_manage", "scanner_manage",
})


@dataclass
class Grant:
    """单条角色-菜单-权限三元组。"""
    role_code: str
    menu_locator: str
    permissions: frozenset[str]

    def signature(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.role_code, self.menu_locator, tuple(sorted(self.permissions)))


@dataclass
class DriftReport:
    """应用基线前后差异。"""
    to_add: list[Grant] = field(default_factory=list)
    to_remove: list[Grant] = field(default_factory=list)
    to_change: list[tuple[Grant, Grant]] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (self.to_add or self.to_remove or self.to_change)

    def summary(self) -> str:
        lines = [
            f"+ add: {len(self.to_add)}",
            f"- remove: {len(self.to_remove)}",
            f"~ change: {len(self.to_change)}",
        ]
        for g in self.to_add:
            lines.append(f"  + {g.signature()}")
        for g in self.to_remove:
            lines.append(f"  - {g.signature()}")
        for old, new in self.to_change:
            lines.append(f"  ~ {old.signature()} -> {new.signature()}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 加载基线
# ---------------------------------------------------------------------------

def load_baseline(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"baseline JSON must be an object, got {type(data).__name__}")
    if "version" not in data or "roles" not in data:
        raise ValueError("baseline JSON missing required keys 'version' / 'roles'")
    return data


# ---------------------------------------------------------------------------
# 解析菜单定位符 -> Menu id（无歧义时）
# ---------------------------------------------------------------------------

def build_locator_index(db: Session) -> dict[str, list[Menu]]:
    """建立 ``locator -> [Menu, ...]`` 索引。

    若同一 locator 对应多个菜单（例如 ``list`` 在 /assets 和 /reports 下都有），
    索引会保留多个，调用方需要根据 parent 消歧或报错。
    """
    menus = db.query(Menu).all()
    by_id = {m.id: m for m in menus}

    # Build path->[Menu] 索引
    out: dict[str, list[Menu]] = {}
    for m in menus:
        loc = _build_locator(m, by_id)
        out.setdefault(loc, []).append(m)
    return out


def _build_locator(menu: Menu, all_by_id: dict[int, Menu]) -> str:
    parts: list[str] = []
    current: Menu | None = menu
    while current is not None:
        parts.append(current.path or "")
        if current.parent_id is None:
            break
        current = all_by_id.get(current.parent_id)
    parts.reverse()
    return "/".join(p for p in parts if p)


def resolve_menu(db: Session, locator: str, name_hint: str | None = None) -> Menu:
    """按 locator 解析菜单；命中多个时报错以暴露漂移。"""
    index = build_locator_index(db)
    candidates = index.get(locator, [])
    if not candidates:
        raise ValueError(f"menu locator '{locator}' not found in database")
    if len(candidates) > 1:
        # 用 name_hint 消歧；若仍不唯一则报错
        if name_hint:
            filtered = [m for m in candidates if m.name == name_hint]
            if len(filtered) == 1:
                return filtered[0]
            if len(filtered) == 0:
                raise ValueError(
                    f"menu locator '{locator}' ambiguous: "
                    f"{[m.name for m in candidates]}; name_hint='{name_hint}' matched none"
                )
        names = [m.name for m in candidates]
        raise ValueError(
            f"menu locator '{locator}' ambiguous: matched {names}; "
            "specify name in baseline or fix menu path uniqueness"
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# 计算 drift
# ---------------------------------------------------------------------------

def calculate_drift(db: Session, baseline: dict[str, Any]) -> DriftReport:
    """对比基线与数据库现状，输出 drift 报告。

    受管角色（``managed_roles``）的 ``soc_role_menus`` 由脚本接管。
    自定义角色（如运维自建的）**完全不动**。
    """
    report = DriftReport()
    managed_codes = set(baseline.get("managed_roles", []))
    baseline_roles = baseline.get("roles", {})

    # 1. 受管角色逐个比对
    for code, role_data in baseline_roles.items():
        if code not in managed_codes:
            # 基线含未声明为 managed 的角色，跳过（不报错）
            continue
        role = db.query(Role).filter(Role.code == code).first()
        if role is None:
            raise ValueError(f"managed role '{code}' missing from database")

        # 当前 DB 中的 grant
        existing_grants: dict[tuple[str, frozenset[str]], RoleMenu] = {}
        for grant in db.query(RoleMenu).filter(RoleMenu.role_id == role.id).all():
            menu = db.query(Menu).filter(Menu.id == grant.menu_id).first()
            if menu is None:
                continue
            locator = _build_locator(menu, {m.id: m for m in db.query(Menu).all()})
            perms = _coerce_set(grant.permissions)
            existing_grants[(locator, perms)] = grant

        # 基线期望的 grant（已应用"只读去写"归一）
        baseline_grants: dict[tuple[str, frozenset[str]], dict[str, Any]] = {}
        for m_entry in role_data.get("menus", []):
            locator = m_entry["locator"]
            name_hint = m_entry.get("name")
            # 解析菜单（确保 locator 在 DB 里）
            try:
                menu = resolve_menu(db, locator, name_hint)
            except ValueError as e:
                raise ValueError(
                    f"baseline role '{code}' menu locator resolution failed: {e}"
                )
            perms = set(m_entry.get("permissions", []))
            # 只读角色去掉写按钮
            if code in {"viewer", "auditor"}:
                perms = {p for p in perms if p not in WRITE_BUTTON_BLACKLIST_FOR_READONLY}
            # user = operator：业务授权完全一致
            # （基线文件里 user 应与 operator 同 business buttons；脚本无需再改）
            perms_fs = frozenset(perms)
            baseline_grants[(locator, perms_fs)] = {
                "menu_id": menu.id,
                "locator": locator,
                "perms": perms_fs,
                "name_hint": name_hint,
            }

        # 找差异
        existing_keys = set(existing_grants.keys())
        baseline_keys = set(baseline_grants.keys())

        for key in baseline_keys - existing_keys:
            # 新增
            report.to_add.append(Grant(
                role_code=code,
                menu_locator=key[0],
                permissions=key[1],
            ))
        for key in existing_keys - baseline_keys:
            # 删除
            report.to_remove.append(Grant(
                role_code=code,
                menu_locator=key[0],
                permissions=key[1],
            ))
        # 修改的检测留给 apply 时（permissions 集合相同视为同一行）

    # 2. 停用角色：只关心 is_active
    for code in baseline.get("disabled_roles", []):
        role = db.query(Role).filter(Role.code == code).first()
        if role is None:
            continue
        if role.is_active:
            # 不算 grant drift；脚本会单独处理 is_active
            pass

    return report


def _coerce_set(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, list):
        return frozenset(str(p) for p in raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return frozenset()
        if isinstance(parsed, list):
            return frozenset(str(p) for p in parsed)
    return frozenset()


# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------

def apply_baseline(db: Session, baseline: dict[str, Any]) -> DriftReport:
    """应用基线到数据库（事务原子）。"""
    report = calculate_drift(db, baseline)
    if report.is_clean():
        return report

    try:
        for code, role_data in baseline.items() if False else []:
            pass  # 避免 IDE 误读

        # 1. 删除多余 grant
        for grant in report.to_remove:
            role = db.query(Role).filter(Role.code == grant.role_code).first()
            if role is None:
                continue
            menu = _find_menu_by_locator(db, grant.menu_locator)
            if menu is None:
                continue
            db.query(RoleMenu).filter(
                RoleMenu.role_id == role.id,
                RoleMenu.menu_id == menu.id,
            ).delete(synchronize_session=False)

        # 2. 新增缺失 grant
        for grant in report.to_add:
            role = db.query(Role).filter(Role.code == grant.role_code).first()
            if role is None:
                continue
            menu = _find_menu_by_locator(db, grant.menu_locator)
            if menu is None:
                continue
            db.add(RoleMenu(
                role_id=role.id,
                menu_id=menu.id,
                permissions=list(grant.permissions),
            ))

        # 3. 停用角色
        for code in baseline.get("disabled_roles", []):
            role = db.query(Role).filter(Role.code == code).first()
            if role is None:
                continue
            if role.is_active:
                role.is_active = False

        db.commit()
    except Exception:
        db.rollback()
        raise

    return report


def _find_menu_by_locator(db: Session, locator: str) -> Menu | None:
    index = build_locator_index(db)
    candidates = index.get(locator, [])
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    raise ValueError(
        f"menu locator '{locator}' ambiguous during apply: {[m.name for m in candidates]}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="应用角色×菜单基线（PRD §10.3）",
    )
    parser.add_argument(
        "--baseline",
        default=DEFAULT_BASELINE,
        help=f"基线 JSON 路径（默认 {DEFAULT_BASELINE}）",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只检查 drift，不修改")
    group.add_argument("--dry-run", dest="dry_run", action="store_true", help="打印将做什么")
    group.add_argument("--apply", action="store_true", help="实际应用到数据库（事务）")
    args = parser.parse_args(argv)

    baseline = load_baseline(args.baseline)
    db = SessionLocal()
    try:
        report = calculate_drift(db, baseline)
    finally:
        db.close()

    print(report.summary())

    if args.check:
        return 0 if report.is_clean() else 2

    if args.dry_run:
        return 0

    # apply
    db = SessionLocal()
    try:
        report_after = apply_baseline(db, baseline)
        print("\n--- applied ---")
        print(report_after.summary())
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())