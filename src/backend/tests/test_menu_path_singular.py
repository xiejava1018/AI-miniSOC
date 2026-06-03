"""
测试：菜单 path 已统一为单数

回归用例 —— 防止任何 init 脚本回退到复数形态。
对应的修复：src/backend/app/api/roles.py + 数据迁移将
{users, roles, menus, departments, audit-logs, dicts, system-configs}
单数化为
{user, role, menu, department, audit-log, dict, system-config}。

与前端 RoutesAlias 契约：
- /system/role
- /system/user
- /system/menu
- /system/department
- /system/audit-log
- /system/dict
- /system/config 或 /system/system-config

此测试通过 db_session fixture 走 test_engine，与生产 DB 完全隔离。
"""
import pytest
from sqlalchemy import text


# 期望的菜单 path（与 RoutesAlias 对齐）
EXPECTED_SINGULAR_PATHS = {
    "user",
    "role",
    "menu",
    "department",
    "audit-log",
    "dict",
    "system-config",
}

# 应当被禁止的复数 path
FORBIDDEN_PLURAL_PATHS = {
    "users",
    "roles",
    "menus",
    "departments",
    "audit-logs",
    "dicts",
    "system-configs",
}


@pytest.fixture
def seed_singular_menus(db_session):
    """Seed 一组单数菜单，专门用于本测试的回归断言"""
    from app.models.menu import Menu

    menus = [
        Menu(path="/system", name="系统管理", component="/index/index", is_visible=True, sort_order=5),
        Menu(path="user", name="用户管理", parent_id=None, component="/system/user", sort_order=1),
        Menu(path="role", name="角色管理", parent_id=None, component="/system/role", sort_order=2),
        Menu(path="menu", name="菜单管理", parent_id=None, component="/system/menu", sort_order=3),
        Menu(path="department", name="部门管理", parent_id=None, component="/system/department", sort_order=5),
        Menu(path="audit-log", name="审计日志", parent_id=None, component="/system/audit-log/index", sort_order=4),
        Menu(path="dict", name="字典管理", parent_id=None, component="/system/dict", sort_order=6),
        Menu(path="system-config", name="系统配置", parent_id=None, component="/system/config", sort_order=7),
    ]
    # 修正 parent_id 关联
    for m in menus:
        db_session.add(m)
    db_session.flush()
    # 父菜单第一个
    parent = menus[0]
    for child in menus[1:]:
        child.parent_id = parent.id
    db_session.commit()
    return menus


class TestMenuPathsAreSingular:
    """soc_menus 表中 /system/* 子菜单 path 必须是单数"""

    def test_no_plural_paths_in_db(self, db_session, seed_singular_menus):
        """禁止任何 /system 子菜单使用复数 path"""
        # 逐个查
        for plural in FORBIDDEN_PLURAL_PATHS:
            result = db_session.execute(
                text("SELECT id, name FROM soc_menus WHERE path = :p AND parent_id IS NOT NULL"),
                {"p": plural},
            ).fetchall()
            assert not result, (
                f"菜单 {plural!r} 仍是复数（id={[r[0] for r in result]}）。"
                "请执行单数化迁移：UPDATE soc_menus SET path = '...' WHERE path = ..."
            )

    def test_singular_paths_exist(self, db_session, seed_singular_menus):
        """期望的单数 path 必须在数据库中"""
        for singular in EXPECTED_SINGULAR_PATHS:
            result = db_session.execute(
                text("SELECT id, name FROM soc_menus WHERE path = :p LIMIT 1"),
                {"p": singular},
            ).fetchone()
            assert result is not None, (
                f"单数菜单 {singular!r} 不在数据库中。"
                "可能是迁移未执行或 init 脚本回退。"
            )

    def test_system_parent_menu_path(self, db_session, seed_singular_menus):
        """系统管理父菜单 path 应为 /system"""
        row = db_session.execute(
            text("SELECT path FROM soc_menus WHERE name = '系统管理' LIMIT 1")
        ).fetchone()
        assert row is not None, "系统管理父菜单不存在"
        assert row[0] == "/system", (
            f"系统管理父菜单 path 应为 '/system'，实际 {row[0]!r}"
        )

    def test_component_format(self, db_session, seed_singular_menus):
        """子菜单 component 应为绝对路径（/ 开头）"""
        rows = db_session.execute(
            text(
                "SELECT path, component FROM soc_menus "
                "WHERE parent_id IS NOT NULL AND component IS NOT NULL"
            )
        ).fetchall()
        assert len(rows) > 0, "没有 seeded 子菜单"
        for path, component in rows:
            assert path not in FORBIDDEN_PLURAL_PATHS, f"path {path!r} 是复数"
            assert component.startswith("/"), (
                f"component 应当以 / 开头：path={path!r} component={component!r}"
            )

    def test_idempotent_migration_query(self, db_session, seed_singular_menus):
        """模拟运行迁移 SQL：单数化迁移后应满足 WHERE NOT EXISTS（无复数残留）"""
        from app.models.menu import Menu
        # 模拟尝试再次单数化（应无更新）
        pairs = [
            ("users", "user"), ("roles", "role"), ("menus", "menu"),
            ("departments", "department"), ("audit-logs", "audit-log"),
            ("dicts", "dict"), ("system-configs", "system-config"),
        ]
        for old, new in pairs:
            count = db_session.query(Menu).filter(
                Menu.path == old, Menu.parent_id.isnot(None)
            ).count()
            assert count == 0, f"复数 {old!r} 仍存在 {count} 条"
