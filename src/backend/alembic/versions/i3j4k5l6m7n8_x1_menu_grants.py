"""X1 权限矩阵收尾：operator/viewer/auditor 全菜单授权回填

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-08-22

按 PRD §6.5 X1 权限矩阵补齐菜单可见性（此前仅 4-5 个菜单）：
- operator：仪表板/资产根/详情/概览/知识库(编辑+验证)/合规(巡检+解读)/
  报告根/告警树 —— 对账、报告、影响分析已有
- viewer：只读集合（仪表板/资产树/概览/知识库只读/合规只读/报告只读/
  告警树）；**移除对账菜单**（矩阵：viewer 对账 ❌，此前误授）
- auditor：viewer 同款只读 + /system + 审计日志 + 保留对账只读

按钮权限仅授矩阵允许项：operator 得 knowledge(view,edit,validate) 与
compliance(view,check,interpret)；auto_extract（AI 抽取，烧 token）留 admin。
"""
from alembic import op

revision = "i3j4k5l6m7n8"
down_revision = "h2i3j4k5l6m7"
branch_labels = None
depends_on = None

# (role_code, menu_id, permissions JSONB or NULL)
# NULL = 菜单可见即可（页面自身无按钮，或按钮由其它机制控制）
_GRANTS = [
    # ---------- operator ----------
    ("operator", 1, None),                       # 仪表板
    ("operator", 2, None),                       # /assets 根
    ("operator", 16, None),                      # 资产详情（EOL 覆盖端点走 require_role）
    ("operator", 19, None),                      # 资产概览
    ("operator", 35, '["view", "edit", "validate"]'),   # 知识库（矩阵：编辑/验证 ✅；auto_extract 留 admin）
    ("operator", 36, '["view", "check", "interpret"]'), # 合规（巡检 + AI 解读）
    ("operator", 39, None),                      # /reports 根（#40 generate/trigger 已有）
    ("operator", 4, None),                       # /alerts 根
    ("operator", 20, None),                      # 告警列表
    # ---------- viewer（只读；对账 ❌ 由下方 DELETE 处理）----------
    ("viewer", 1, None),
    ("viewer", 2, None),
    ("viewer", 16, None),
    ("viewer", 19, None),
    ("viewer", 35, '["view"]'),                  # 知识库只读
    ("viewer", 36, '["view"]'),                  # 合规只读
    ("viewer", 39, None),
    ("viewer", 4, None),
    ("viewer", 20, None),
    # ---------- auditor（只读 + 审计日志 + 对账只读保留）----------
    ("auditor", 1, None),
    ("auditor", 2, None),
    ("auditor", 5, None),                        # /system 根（仅为挂 audit-log 子菜单）
    ("auditor", 9, '["view"]'),                  # 审计日志
    ("auditor", 16, None),
    ("auditor", 19, None),
    ("auditor", 35, '["view"]'),
    ("auditor", 36, '["view"]'),
    ("auditor", 39, None),
    ("auditor", 4, None),
    ("auditor", 20, None),
]


def upgrade() -> None:
    for role_code, menu_id, perms in _GRANTS:
        perms_sql = f"'{perms}'::jsonb" if perms else "NULL"
        # JOIN soc_menus 而非硬编码 menu_id：空库（无业务种子菜单行）时
        # SELECT 无行 → 静默跳过，不撞外键。对生产（菜单行存在）行为不变。
        # 注：同 path 菜单在不同父下可能多行（如 'list'），OR 全匹配是故意的
        # ——与 has_button_access 的同名 path 合并语义一致。
        op.execute(f"""
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id, {perms_sql}
            FROM soc_roles r
            JOIN soc_menus m ON m.id = {menu_id}
            WHERE r.code = '{role_code}'
              AND NOT EXISTS (
                SELECT 1 FROM soc_role_menus rm
                WHERE rm.role_id = r.id AND rm.menu_id = {menu_id}
              )
        """)
    # 矩阵修正：viewer 对账 ❌（此前迁移误授），auditor 只读保留
    op.execute("""
        DELETE FROM soc_role_menus rm
        USING soc_roles r, soc_menus m
        WHERE rm.role_id = r.id AND rm.menu_id = m.id
          AND r.code = 'viewer' AND m.path = 'reconciliation'
    """)


def downgrade() -> None:
    # 回滚本迁移新增的授权（NOT EXISTS 保证幂等语义的逆操作：仅删本清单内组合）
    for role_code, menu_id, perms in _GRANTS:
        op.execute(f"""
            DELETE FROM soc_role_menus rm
            USING soc_roles r
            WHERE rm.role_id = r.id AND rm.menu_id = {menu_id}
              AND r.code = '{role_code}'
        """)
    # 恢复 viewer 对账只读（g1h2i3j4k5l6 的原始状态）
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view"]'::jsonb
        FROM soc_roles r, soc_menus m
        WHERE r.code = 'viewer' AND m.path = 'reconciliation'
          AND NOT EXISTS (
            SELECT 1 FROM soc_role_menus rm
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)
