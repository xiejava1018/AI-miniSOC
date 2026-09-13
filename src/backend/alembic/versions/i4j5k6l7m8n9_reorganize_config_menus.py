"""菜单重组：/scan 上移到 /reports 后、/config 新顶级 + /system 子菜单重排

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-09-13

用户 2026-09-13 指定：
- 顶级菜单顺序调整：/scan 从 sort=10 移到 /reports(7) 与 /ops 之间
- 顶级菜单 sort 重排：/scan=8、/config=9(新建)、/ops=10、/system=11
- 新建顶级菜单「配置中心」(path=/config, component=/index/index 容器布局)
- /config 下 3 个子菜单：配置管理（config-center 改名）/ 数据源管理 / AI 模型管理
  原挂在 /system 下，移过来时同步调整 sort_order=1/2/3
- /system 子菜单按用户指定顺序重排：
  user(1) → role(2) → department(3) → menu(4) → dict(5) → 高级配置(KV)=6 → 审计日志=7

容器菜单 component 必须是 /index/index（与 /system /assets 同款），写 /config/index 会 404。
配置中心父菜单 permissions=[]（无按钮，是容器不是页面）。

注意：soc_menus.name 字段对老菜单是中文（用户管理/角色管理等），对配置中心相关菜单是英文驼峰
（configCenter/dataSource/aiProvider），历史不统一。WHERE 条件用 path 而非 name 更稳。

迁移策略：拆原子、纯 SQL、NOT EXISTS 守卫，每个块都幂等，downgrade 与 upgrade 镜像。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # =========================================================
    # 1. 顶级菜单 sort 重排
    # =========================================================
    # /scan: 10 → 8（移到 /reports 后）
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 8, updated_at = NOW()
            WHERE path = '/scan' AND parent_id IS NULL
            """
        )
    )
    # /ops: 8 → 10
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 10, updated_at = NOW()
            WHERE path = '/ops' AND parent_id IS NULL
            """
        )
    )
    # /system: 9 → 11
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 11, updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )

    # =========================================================
    # 2. 新建顶级菜单「配置中心」(path=/config, sort=9)
    # =========================================================
    # component 必须 /index/index（容器布局）；permissions=[]（无按钮）
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component, sort_order, is_visible, permissions)
            SELECT NULL, '配置中心', '配置中心', '/config', 'ri:settings-2-line',
                   '/index/index', 9, true, CAST('[]' AS jsonb)
            WHERE NOT EXISTS (
              SELECT 1 FROM soc_menus WHERE path = '/config' AND parent_id IS NULL
            )
            """
        )
    )

    # =========================================================
    # 3. 移 3 个子菜单：/system → /config，同时改 sort_order
    # =========================================================
    # 配置管理（原 config-center，sort=11 → 1，title "配置中心" → "配置管理"）
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL),
                sort_order = 1,
                title = '配置管理',
                updated_at = NOW()
            WHERE path = 'config-center'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # 数据源管理（data-source，sort=10 → 2）
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL),
                sort_order = 2,
                updated_at = NOW()
            WHERE path = 'data-source'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # AI 模型管理（ai-provider，sort=13 → 3）
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL),
                sort_order = 3,
                updated_at = NOW()
            WHERE path = 'ai-provider'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )

    # =========================================================
    # 4. /system 子菜单重排
    #    新顺序：用户管理(1) 角色管理(2) 部门管理(3) 菜单管理(4) 字典管理(5) 高级配置KV(6) 审计日志(7)
    #    用 path 定位（path 不变）
    # =========================================================
    # department: 5 → 3
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 3, updated_at = NOW()
            WHERE path = 'department'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # menu: 3 → 4
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 4, updated_at = NOW()
            WHERE path = 'menu'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # dict: 6 → 5
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 5, updated_at = NOW()
            WHERE path = 'dict'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # system-config（高级配置KV）: 99 → 6
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 6, updated_at = NOW()
            WHERE path = 'system-config'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    # audit-log: 4 → 7
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 7, updated_at = NOW()
            WHERE path = 'audit-log'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    # =========================================================
    # 1. /system 子菜单 sort 恢复
    # =========================================================
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 4, updated_at = NOW()
            WHERE path = 'audit-log'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 99, updated_at = NOW()
            WHERE path = 'system-config'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 6, updated_at = NOW()
            WHERE path = 'dict'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 3, updated_at = NOW()
            WHERE path = 'menu'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 5, updated_at = NOW()
            WHERE path = 'department'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )

    # =========================================================
    # 2. 3 个子菜单移回 /system + sort 恢复 + config-center 标题恢复
    # =========================================================
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL),
                sort_order = 13,
                updated_at = NOW()
            WHERE path = 'ai-provider'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL),
                sort_order = 10,
                updated_at = NOW()
            WHERE path = 'data-source'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL),
                sort_order = 11,
                title = '配置中心',
                updated_at = NOW()
            WHERE path = 'config-center'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/config' AND parent_id IS NULL)
            """
        )
    )

    # =========================================================
    # 3. 删顶级菜单 /config
    # =========================================================
    bind.execute(
        sa.text(
            "DELETE FROM soc_menus WHERE path = '/config' AND parent_id IS NULL"
        )
    )

    # =========================================================
    # 4. 顶级 sort 恢复
    # =========================================================
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 9, updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 8, updated_at = NOW()
            WHERE path = '/ops' AND parent_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 10, updated_at = NOW()
            WHERE path = '/scan' AND parent_id IS NULL
            """
        )
    )
