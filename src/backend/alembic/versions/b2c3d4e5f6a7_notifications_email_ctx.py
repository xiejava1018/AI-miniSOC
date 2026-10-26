"""notifications_email_ctx — soc_notifications 加 email_type / email_ctx 两列

背景（2026-10-25 邮件通道接线后续）：
push 推送已改走 create_multi() 触发邮件，但邮件模板只能拿到通用上下文
（user/notification/unsubscribe_url）。4 个场景模板（push:source_down /
push:risk_spike / push:eol_warning / push:shadow_asset）需要各自的 ctx 键
（source_code/down_hours、asset_count/asset_list、count/shadow_list 等），
这些值在 worker 异步投递时（60s tick）必须从库里读——进程内参数传不过去。

因此给 soc_notifications 加两个可空列：
- email_type VARCHAR(40)  邮件模板键（如 'push:shadow_asset'；NULL=按 notif.type 通用模板）
- email_ctx  JSONB        模板渲染的额外上下文（NULL=无）

幂等：ADD COLUMN IF NOT EXISTS —— 生产表已有数据，纯加列零风险。
downgrade：DROP COLUMN IF EXISTS（两列仅邮件渲染用，删了不影响业务数据）。

Revision ID: b2c3d4e5f6a7
Revises: n0b1c2d3e4f5
Create Date: 2026-10-25
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "n0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE soc_notifications "
        "ADD COLUMN IF NOT EXISTS email_type VARCHAR(40)"
    )
    op.execute(
        "ALTER TABLE soc_notifications "
        "ADD COLUMN IF NOT EXISTS email_ctx JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE soc_notifications DROP COLUMN IF EXISTS email_ctx")
    op.execute("ALTER TABLE soc_notifications DROP COLUMN IF EXISTS email_type")