"""
回归测试：配置中心菜单种入不能再静默 0 行 (X1E-11 / e2f3g4h5i6j7)

历史教训
--------
d2e3f4g5h6i7_config_center_v1.py 的菜单种入 SQL 用 `WHERE path = '/system'`
定位父菜单「系统管理」，但 init_system_data.py / init_menus.sql 实际写入的
「系统管理」path 为 ''（空 Layout 容器约定）。结果：fresh DB 跑完迁移后
`SELECT * FROM soc_menus WHERE name IN ('dataSource','configCenter','configLogs')`
返回 0 行 —— 父解析不到，CROSS JOIN 产出空集合，INSERT ... SELECT 静默 0 行
且 alembic upgrade 仍返回成功。

修复
----
e2f3g4h5i6j7 用 (name='系统管理' AND parent_id IS NULL) 锁父菜单 + 兜底
把 '' 改成 '/system'。本测试在 db_session 上模拟 d2e3f4g5i6j7 跑前的状态
（系统管理 path=''），再走一遍菜单种入 SQL，断言三条菜单都进了库。

设计原则
--------
- 不依赖 alembic CLI，只跑纯 SQL（与迁移 SQL 100% 一致）。
- 同时验证两条修复路径：(A) parent 锁行按 name 而非 path；
  (B) 系统管理 path 兜底改写。
- admin 授权回填一并验证：菜单种入后 admin 应同时拿到三张菜单的按钮权限。
"""
import json

import pytest
from sqlalchemy import text


# 与 e2f3g4h5i6j7 一致的菜单 VALUES（防止漂移）
_MENU_VALUES = [
    ("dataSource", "数据源管理", "data-source", "ri:database-2-line",
     "/system/data-source", 10,
     [{"title": "查看", "authMark": "view"},
      {"title": "新增", "authMark": "add"},
      {"title": "编辑", "authMark": "edit"},
      {"title": "删除", "authMark": "delete"},
      {"title": "连接测试", "authMark": "test"}]),
    ("configCenter", "配置中心", "config-center", "ri:equalizer-line",
     "/system/config-center", 11,
     [{"title": "查看", "authMark": "view"},
      {"title": "编辑", "authMark": "edit"}]),
    ("configLogs", "配置审计", "config-logs", "ri:history-line",
     "/system/config-logs", 12,
     [{"title": "查看", "authMark": "view"}]),
]


@pytest.fixture
def fresh_system_empty_path(db_session):
    """模拟生产 init 后的状态：系统管理 path='' (历史 bug 触发条件)"""
    from app.models.menu import Menu
    # 清空现有菜单
    db_session.execute(text("DELETE FROM soc_role_menus"))
    db_session.execute(text("DELETE FROM soc_menus"))
    db_session.commit()

    # 写入系统管理，path='' —— 即触发 e2f3g4h5i6j7 的根因
    db_session.add(Menu(name="系统管理", path="", icon="ri:settings-3-line",
                        sort_order=6, is_visible=True, component="/index/index"))
    db_session.commit()
    return db_session


def _run_fix_migration(db_session):
    """复刻 e2f3g4h5i6j7 upgrade() 的三段 SQL（纯 SQL，不走 alembic）。"""
    # 1) 路径归一：'' → '/system'
    db_session.execute(text(
        "UPDATE soc_menus "
        "SET path = '/system', updated_at = NOW() "
        "WHERE name = '系统管理' AND parent_id IS NULL AND path = ''"
    ))
    db_session.commit()

    # 2) 菜单种入（与迁移 SQL 同源）
    values_sql = ",".join(
        f"({name!r}, {title!r}, {path!r}, {icon!r}, {comp!r}, {sort}, {perms!r})"
        for (name, title, path, icon, comp, sort, perms_list) in _MENU_VALUES
        for perms in [json.dumps(perms_list, ensure_ascii=False)]
    )
    db_session.execute(text(f"""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions)
        SELECT p.id, v.name, v.title, v.path, v.icon, v.component,
               v.sort_order, true, CAST(v.perms AS jsonb)
        FROM (SELECT id FROM soc_menus
              WHERE name = '系统管理' AND parent_id IS NULL) p
        CROSS JOIN (VALUES {values_sql}) AS v(name, title, path, icon, component, sort_order, perms)
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_menus m WHERE m.name = v.name AND m.parent_id = p.id
        )
    """))
    db_session.commit()

    # 3) admin 授权回填
    db_session.execute(text("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id,
               CAST((SELECT jsonb_agg(e->>'authMark')
                     FROM jsonb_array_elements(m.permissions) e) AS jsonb)
        FROM soc_roles r
        CROSS JOIN soc_menus m
        WHERE r.code = 'admin'
          AND m.name IN ('dataSource', 'configCenter', 'configLogs')
          AND m.parent_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM soc_role_menus rm
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """))
    db_session.commit()


class TestConfigCenterMenuSeed:
    """e2f3g4h5i6j7 配置中心菜单种入的回归保护"""

    def test_three_menus_seeded_after_fix(self, fresh_system_empty_path):
        """fresh DB + 系统管理 path='' + 跑修复 SQL → 必须出现 3 条菜单"""
        _run_fix_migration(fresh_system_empty_path)

        rows = fresh_system_empty_path.execute(text(
            "SELECT name, path, component FROM soc_menus "
            "WHERE name IN ('dataSource','configCenter','configLogs') "
            "ORDER BY sort_order"
        )).fetchall()
        assert len(rows) == 3, (
            f"期望 3 条配置中心菜单，实际 {len(rows)}：{rows}。"
            "e2f3g4h5i6j7 修复失效或 SQL 漂移。"
        )
        # 三条菜单都挂在「系统管理」下
        sys_id = fresh_system_empty_path.execute(text(
            "SELECT id FROM soc_menus WHERE name='系统管理' AND parent_id IS NULL"
        )).scalar()
        parents = fresh_system_empty_path.execute(text(
            "SELECT parent_id FROM soc_menus "
            "WHERE name IN ('dataSource','configCenter','configLogs')"
        )).fetchall()
        assert all(p[0] == sys_id for p in parents), (
            f"菜单未挂在系统管理下：parents={parents}"
        )

    def test_system_parent_path_normalized(self, fresh_system_empty_path):
        """修复 SQL 必须把系统管理 path 改成 '/system'"""
        _run_fix_migration(fresh_system_empty_path)
        row = fresh_system_empty_path.execute(text(
            "SELECT path FROM soc_menus WHERE name='系统管理' AND parent_id IS NULL"
        )).fetchone()
        assert row[0] == "/system", (
            f"系统管理 path 未归一：实际 {row[0]!r}。"
            "e2f3g4h5i6j7 步骤 1 失效。"
        )

    def test_admin_role_grants_seeded(self, fresh_system_empty_path):
        """admin 角色必须拿到三个菜单 + 完整按钮权限"""
        # 创建 admin 角色
        fresh_system_empty_path.execute(text(
            "INSERT INTO soc_roles (code, name, is_system, is_active) "
            "VALUES ('admin', '管理员', true, true) "
            "ON CONFLICT (code) DO NOTHING"
        ))
        fresh_system_empty_path.commit()
        _run_fix_migration(fresh_system_empty_path)

        rows = fresh_system_empty_path.execute(text("""
            SELECT m.name, rm.permissions
            FROM soc_role_menus rm
            JOIN soc_roles r ON r.id = rm.role_id
            JOIN soc_menus m ON m.id = rm.menu_id
            WHERE r.code = 'admin'
              AND m.name IN ('dataSource','configCenter','configLogs')
            ORDER BY m.name
        """)).fetchall()
        assert len(rows) == 3, (
            f"admin 应有 3 条菜单授权，实际 {len(rows)}：{rows}。"
            "e2f3g4h5i6j7 步骤 3 失效。"
        )
        # 按钮权限非空
        for name, perms in rows:
            assert perms and len(perms) > 0, (
                f"{name} 授权 permissions 为空：{perms!r}"
            )

    def test_d2e3f4g5h6i7_old_query_would_silently_zero_rows(self, fresh_system_empty_path):
        """反向证明：旧 d2e3f4g5h6i7 用 `WHERE path='/system'` 在 path='' 下真的 0 行"""
        # 模拟 d2e3f4g5h6i7 原 SQL 的父查询
        parent_id = fresh_system_empty_path.execute(text(
            "SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL"
        )).scalar()
        assert parent_id is None, (
            "本测试需要在 系统管理 path='' 的状态下跑（父解析不到）。"
            f"实际 parent_id={parent_id}，fixture 配置异常。"
        )
        # 旧 INSERT ... SELECT 在父解析不到时为 0 行（CROSS JOIN 退化）
        # 此处不重跑整段 SQL 验证，只需要父解析为 None 就够了 —— 上面的断言保证。

    def test_fix_migration_idempotent(self, fresh_system_empty_path):
        """修复 SQL 重复执行不会出错 / 不会重复插入"""
        _run_fix_migration(fresh_system_empty_path)
        _run_fix_migration(fresh_system_empty_path)  # 第二次

        rows = fresh_system_empty_path.execute(text(
            "SELECT name FROM soc_menus "
            "WHERE name IN ('dataSource','configCenter','configLogs')"
        )).fetchall()
        names = sorted(r[0] for r in rows)
        assert names == ['configCenter', 'configLogs', 'dataSource'], (
            f"重复跑修复 SQL 后菜单行数异常：{names}"
        )