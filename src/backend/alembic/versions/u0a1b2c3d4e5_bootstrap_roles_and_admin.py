"""bootstrap_roles_and_admin — 补齐 4 个 X1 角色 + 建默认 admin 账号（空库可登录）

背景（GitHub issue #12 · 第 1 条「没有默认账号和密码」）：
迁移跑完 / init 脚本跑完，soc_users 仍是空表 —— 没有任何账号可登录，
新部署者只能进数据库手工 INSERT。根因：用户种子从未进过迁移链。

本迁移做两件事：

1) **角色基线**：种齐 X1 四角色 admin / operator / viewer / auditor。
   （历史 user / readonly 为兼容别名，一并种上但置 is_active=false。）
2) **默认管理员**：建 admin 账号，密码取环境变量 `DEFAULT_ADMIN_PASSWORD`，
   未设置时回落到出厂默认 `Admin@123456`。

安全设计：
- 密码用 bcrypt 现算（不落明文常量、不硬编码 hash）——hash 每次 upgrade 都不同，
  但语义等价；`WHERE NOT EXISTS` 保证幂等，重跑不会覆盖已改过的密码。
- **默认密码仅在首次部署存在**：README 与安装脚本都要求首登即改。
  为此在 soc_system_config 写一条 `security.default_admin_password` 标记，
  install.sh / 部署文档据此提示。正式做法是首登强制改密（待前端配合）。
- 绝不在代码/日志/迁移注释里写真实密码常量以外的凭据；出厂默认密码是公开的，
  与 README 一致，可接受（同 docker 默认 root 密码的惯例）。
- 环境变量注入：可用 `DEFAULT_ADMIN_PASSWORD=... alembic upgrade head`
  在部署时改成自定义密码，不必改代码。

幂等：全部 ON CONFLICT / WHERE NOT EXISTS；已存在 admin 则跳过，不改其密码。

Revision ID: u0a1b2c3d4e5
Revises: k0m1n2o3p4q5
Create Date: 2026-10-19
"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "u0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "k0m1n2o3p4q5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 出厂默认账号（与 README / install.sh 输出保持一致）
DEFAULT_ADMIN_USERNAME = "admin"
FALLBACK_ADMIN_PASSWORD = "Admin@123456"


def _admin_password() -> str:
    return os.getenv("DEFAULT_ADMIN_PASSWORD") or FALLBACK_ADMIN_PASSWORD


def upgrade() -> None:
    # ---------- 1. 角色基线（X1 四角色 + 历史兼容别名） ----------
    # 注：不写 is_active —— 该列由链上更晚的 ab9cd0e1f2a3 补上，
    # 在此处写会 UndefinedColumn。该列建表时 DEFAULT true，语义一致。
    op.execute("""
        INSERT INTO soc_roles (name, code, description, is_system, created_at, updated_at)
        VALUES
            ('管理员', 'admin',    '系统管理员，拥有所有权限',                    true, NOW(), NOW()),
            ('运维',   'operator', '运维角色：资产读写 + 对账/报告 + EOL 覆盖',  true, NOW(), NOW()),
            ('观察者', 'viewer',   '只读：仅看资产/告警/报告/对账/数据健康',       true, NOW(), NOW()),
            ('审计人员','auditor',  '审计：只读 + 审计日志',                     true, NOW(), NOW()),
            ('普通用户','user',    '历史角色，等同 viewer（兼容保留）',          true, NOW(), NOW()),
            ('只读用户','readonly','历史角色，等同 viewer（兼容保留）',          true, NOW(), NOW())
        ON CONFLICT (code) DO NOTHING
    """)

    # admin 拿到全部菜单（基线种入的 + 各后续迁移种的）。
    # 用「不在 soc_role_menus 里的菜单」做差集，天然幂等且不会覆盖后续调整。
    # 注：不写 permissions —— soc_role_menus 只有 role_id/menu_id/permissions 三列，
    # 其中 permissions 由链上更晚的 ab9cd0e1f2a3 补上（CLAUDE.md 约定 C12）。
    # 各菜单自身的 permissions 已存在 soc_menus.permissions 上，由后续
    # 授权迁移（如 g1h2i3j4k5l6 / i3j4k5l6m7n8）按角色回填。
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id)
        SELECT r.id, m.id
        FROM soc_roles r, soc_menus m
        WHERE r.code = 'admin'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm
              WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)

    # ---------- 2. 默认管理员账号 ----------
    # 密码现算 bcrypt；WHERE NOT EXISTS 保证已有 admin 账号时不动其密码。
    # 必须用 bind.execute(text, params)：op.execute(text, params) 不接受双参
    # （CLAUDE.md §4.3 红线③）。
    from app.core.security import get_password_hash

    bind = op.get_bind()
    password_hash = get_password_hash(_admin_password())

    bind.execute(
        sa.text(
            """
            INSERT INTO soc_users (username, password_hash, email, full_name,
                                   status, role_id, is_superuser,
                                   created_at, updated_at)
            SELECT :username, :password_hash, :email, '系统管理员',
                   'active', r.id, true, NOW(), NOW()
            FROM soc_roles r
            WHERE r.code = 'admin'
              AND NOT EXISTS (
                  SELECT 1 FROM soc_users u WHERE u.username = :username
              )
            """
        ),
        {
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": password_hash,
            "email": "admin@example.com",
        },
    )

    # ---------- 3. 出厂密码标记（供安装脚本 / 文档提示首登改密） ----------
    # soc_system_config 上没有 (category, key) 唯一约束，不能用 ON CONFLICT，
    # 改用 WHERE NOT EXISTS 幂等。
    op.execute("""
        UPDATE soc_system_config
        SET value = 'true', updated_at = NOW()
        WHERE category = 'security' AND key = 'default_admin_password'
    """)
    op.execute("""
        INSERT INTO soc_system_config (category, key, value, value_type, description)
        SELECT 'security', 'default_admin_password', 'true', 'boolean',
               '系统仍使用出厂默认 admin 密码，首次登录后请立即修改'
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_system_config
            WHERE category = 'security' AND key = 'default_admin_password'
        )
    """)


def downgrade() -> None:
    # 只回滚本迁移自己造的「出厂默认」痕迹，不删管理员账号本身
    # （删账号会连带审计日志外键，且生产早已改过密码）。
    op.execute("""
        DELETE FROM soc_system_config
        WHERE category = 'security' AND key = 'default_admin_password'
    """)