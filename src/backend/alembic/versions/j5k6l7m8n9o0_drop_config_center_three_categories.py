"""配置中心配置管理：删除 captcha / general / security 三个分类的 schema 注册

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-09-13

用户 2026-09-13 指定：
配置中心（/config/config-center）「配置管理」页面只保留 alert_governance /
browsing_detection / push_rules / risk_rules / reports / sync / frontend 几个分类，
去掉「登录验证码」(captcha)、「品牌信息」(general)、「安全策略」(security) 三个分类入口。

**只删 soc_config_schema 注册行（不再在配置中心页面渲染），保留 soc_system_config 实际值不变**：

1. 高级配置（/system/config，KV 表）按 category 直接读 soc_system_config，不依赖 schema，
   所以这三个 category 仍可在高级配置页正常编辑（用户在高级配置里改 system_name 仍生效）。
2. /api/v1/public/system-info 仍能从 DB 读到 system_name/logo/copyright/description，
   顶栏 / 登录页 / 关于弹窗的动态品牌信息保持工作。

降级恢复时执行 alembic downgrade j5k6l7m8n9o0 即可重新种回 schema 行
（值仍在 soc_system_config 里；schema 行补齐后立即在配置中心可见）。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 删除 3 个分类的全部 schema 注册行
    # NOT EXISTS 守卫防止 0 行环境（其实没必要，但和已有迁移风格一致）
    bind.execute(
        sa.text(
            """
            DELETE FROM soc_config_schema
            WHERE category IN ('captcha', 'general', 'security')
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 恢复 schema 行（与首次种入完全一致；值仍在 soc_system_config，schema 注册后立即可见）
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_config_schema
              (category, key, label, value_type, default_value, options,
               validation, effect_scope, sensitive, group_name, sort_order, help_text, editable)
            VALUES
              -- captcha / 登录安全
              ('captcha', 'captcha_enabled', '启用登录验证码', 'boolean', 'true',
               NULL, NULL, 'restart', false, '登录安全', 1,
               '关闭后登录接口不再校验验证码', true),
              ('captcha', 'captcha_expire_seconds', '验证码有效期（秒）', 'number', '300',
               NULL, '{"min": 60, "max": 3600}', 'restart', false, '登录安全', 2,
               NULL, true),

              -- general / 品牌信息
              ('general', 'system_name', '系统名称', 'string', 'AI-miniSOC',
               NULL, '{"max_length": 100}', 'restart', false, '品牌', 1,
               NULL, true),
              ('general', 'system_logo', '系统 Logo 地址', 'multiline', '',
               NULL, '{"max_length": 500}', 'restart', false, '品牌', 2,
               '支持 base64 / URL；为空则不显示 logo', true),
              ('general', 'system_copyright', '版权信息', 'string', '© 2026 AI-miniSOC',
               NULL, '{"max_length": 200}', 'restart', false, '品牌', 3,
               NULL, true),
              ('general', 'system_description', '系统描述', 'multiline',
               'AI-driven mini Security Operation Center',
               NULL, '{"max_length": 500}', 'restart', false, '品牌', 4,
               NULL, true),
              ('general', 'allowed_hosts', '允许访问的 Host', 'string', 'all',
               NULL, NULL, 'restart', false, '运行时事实', 5,
               '逗号分隔域名；all = 不限制', false),

              -- security / 密码策略
              ('security', 'password_min_length', '密码最小长度', 'number', '8',
               NULL, '{"min": 6, "max": 64}', 'restart', false, '密码策略', 1,
               NULL, true),
              ('security', 'password_require_uppercase', '密码需含大写字母', 'boolean', 'true',
               NULL, NULL, 'restart', false, '密码策略', 2,
               NULL, true),
              ('security', 'password_require_digit', '密码需含数字', 'boolean', 'true',
               NULL, NULL, 'restart', false, '密码策略', 3,
               NULL, true),

              -- security / 登录锁定
              ('security', 'max_login_attempts', '最大登录失败次数', 'number', '5',
               NULL, '{"min": 3, "max": 20}', 'restart', false, '登录锁定', 4,
               NULL, true),
              ('security', 'lockout_duration_minutes', '锁定时长（分钟）', 'number', '30',
               NULL, '{"min": 5, "max": 1440}', 'restart', false, '登录锁定', 5,
               NULL, true),

              -- security / 会话
              ('security', 'session_timeout_minutes', '会话超时（分钟）', 'number', '60',
               NULL, '{"min": 10, "max": 1440}', 'restart', false, '会话', 6,
               NULL, true)
            ON CONFLICT (category, key) DO NOTHING
            """
        )
    )
