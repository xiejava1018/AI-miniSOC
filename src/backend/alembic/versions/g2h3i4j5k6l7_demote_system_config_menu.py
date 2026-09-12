"""系统配置降级为高级配置(KV)

Revision ID: g2h3i4j5k6l7
Revises: f3g4h5i6j7k8
Create Date: 2026-09-12

路线 C 第三步：配置中心已全量覆盖（37/37 schema 注册 + 兜底区），
「系统配置」通用 KV 编辑器降级为高级入口——菜单改名 + 移到系统管理末尾。
页面代码保留（不删），前端页内另有警示横幅。
"""
from alembic import op
import sqlalchemy as sa

revision = "g2h3i4j5k6l7"
down_revision = "f3g4h5i6j7k8"
branch_labels = None
depends_on = None

# 匹配条件用 name + component 双重定位（path 存中文的旧数据形态下 name 才是稳定键）
_MENU_WHERE = "name = '系统配置' AND component = '/system/config/index'"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"UPDATE soc_menus SET name = '高级配置KV', title = '高级配置(KV)', "
            f"sort_order = 99 WHERE {_MENU_WHERE}"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"UPDATE soc_menus SET name = '系统配置', title = NULL, "
            f"sort_order = 7 WHERE name = '高级配置KV' AND component = '/system/config/index'"
        )
    )
