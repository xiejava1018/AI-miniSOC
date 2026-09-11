"""修复配置中心菜单种入：父菜单 path 不一致导致 d2e3f4g5h6i7 静默 0 行 (X1E-11)

背景
----
d2e3f4g5h6i7_config_center_v1.py 的菜单种入 SQL 用
  `WHERE path = '/system' AND parent_id IS NULL`
定位父菜单「系统管理」，但 init_system_data.py / init_menus.sql 实际写入的
「系统管理」行 path 为 ''（早期空 Layout 容器约定）。

结果：fresh DB 跑完 d2e3f4g5h6i7 后，
  SELECT * FROM soc_menus WHERE name IN ('dataSource','configCenter','configLogs');
返回 0 行 —— 父解析不到，CROSS JOIN 产出空集合，INSERT ... SELECT 静默 0 行
且 alembic upgrade 仍返回成功。文档 §6.5 已显式提醒「执行后必须回读确认」，
本迁移即为修复 + 兜底。

修复点
----
1) 路径归一：把「系统管理」parent_id IS NULL 且 name='系统管理' 的行
   path 从 '' 改写为 '/system'（已是 '/system' 的保持不变）。
   仅修 path，不动 name/title/icon/sort_order。空字符串无任何代码引用，
   grep 全仓确认安全（src/backend/app/api/menus.py 走 parent_id/name 过滤）。
2) 菜单补种：按 d2e3f4g5h6i7 的同一份 VALUES 重新 INSERT，
   parent_id 子查询用 (name='系统管理' AND parent_id IS NULL) 锁行，
   不再依赖具体 path 值。两份 SQL 互为等价（NOT EXISTS 守卫使重复执行幂等），
   即使 d2e3f4g5h6i7 在某些库已经成功种入，本步也只会跳过。
3) 授权回填：admin 角色的 soc_role_menus 关联 + permissions JSONB
   补齐，逻辑与 d2e3f4g5h6i7 同源，幂等。

down_revision 挂 d2e3f4g5h6i7（当前 head），运行期修复，无破坏性变更。

Revision ID: e2f3g4h5i6j7
Revises: d2e3f4g5h6i7
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, Sequence[str], None] = "d2e3f4g5h6i7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- 1) 路径归一：系统管理 path '' → '/system' ----------------
    # 仅修顶级「系统管理」父菜单。空库（系统管理不存在）→ 0 行更新，无副作用。
    # 已经 path='/system' 的库 → 0 行更新，仍幂等。
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET path = '/system', updated_at = NOW()
            WHERE name = '系统管理' AND parent_id IS NULL AND path = ''
            """
        )
    )

    # ---------------- 2) 菜单补种（与 d2e3f4g5h6i7 同源，幂等守卫）----------------
    # parent_id 用 (name='系统管理' AND parent_id IS NULL) 取，不再依赖 path。
    # 即便 d2e3f4g5h6i7 之前在某些库已经种入，NOT EXISTS 守卫也保证不会重复。
    op.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions)
            SELECT p.id, v.name, v.title, v.path, v.icon, v.component,
                   v.sort_order, true, CAST(v.perms AS jsonb)
            FROM (SELECT id FROM soc_menus
                  WHERE name = '系统管理' AND parent_id IS NULL) p
            CROSS JOIN (VALUES
              ('dataSource',   '数据源管理', 'data-source',   'ri:database-2-line',
               '/system/data-source',   10,
               '[{"title":"查看","authMark":"view"},{"title":"新增","authMark":"add"},{"title":"编辑","authMark":"edit"},{"title":"删除","authMark":"delete"},{"title":"连接测试","authMark":"test"}]'),
              ('configCenter', '配置中心',   'config-center', 'ri:equalizer-line',
               '/system/config-center',  11,
               '[{"title":"查看","authMark":"view"},{"title":"编辑","authMark":"edit"}]'),
              ('configLogs',   '配置审计',   'config-logs',   'ri:history-line',
               '/system/config-logs',    12,
               '[{"title":"查看","authMark":"view"}]')
            ) AS v(name, title, path, icon, component, sort_order, perms)
            WHERE NOT EXISTS (
              SELECT 1 FROM soc_menus m WHERE m.name = v.name AND m.parent_id = p.id
            )
            """
        )
    )

    # ---------------- 3) admin 授权补全（幂等）----------------
    op.execute(
        sa.text(
            """
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
            """
        )
    )

    # 若已存在关联但 permissions 为空（旧数据 / 历史变更漏写），回填完整按钮权限
    op.execute(
        sa.text(
            """
            UPDATE soc_role_menus rm
            SET permissions = CAST(
                (SELECT jsonb_agg(e->>'authMark')
                 FROM jsonb_array_elements(m.permissions) e) AS jsonb
            )
            FROM soc_roles r, soc_menus m
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
              AND r.code = 'admin'
              AND m.name IN ('dataSource', 'configCenter', 'configLogs')
              AND (rm.permissions IS NULL OR rm.permissions::text = '[]')
            """
        )
    )


def downgrade() -> None:
    # 倒序：撤授权 → 删菜单 → 还原系统管理 path
    op.execute(
        sa.text(
            """
            DELETE FROM soc_role_menus rm
            USING soc_roles r, soc_menus m
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
              AND r.code = 'admin'
              AND m.name IN ('dataSource', 'configCenter', 'configLogs')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM soc_menus
            WHERE name IN ('dataSource', 'configCenter', 'configLogs')
            """
        )
    )
    # 仅当 path 仍是 '/system' 时还原为 ''（防止覆盖其他合法路径）
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET path = '', updated_at = NOW()
            WHERE name = '系统管理' AND parent_id IS NULL AND path = '/system'
            """
        )
    )