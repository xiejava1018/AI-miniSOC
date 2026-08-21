"""asset lifecycle columns + soc_eol_reference seed (P3/F3.2)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-21 18:00:00.000000

P3 F3.2（PRD ai-asset-management-prd.md v1.2.1）：
- soc_assets 扩 4 列：purchase_date / warranty_end / expected_eol / expected_eol_source
  （expected_eol_source: preset=参考表自动匹配 / manual=人工覆盖，覆盖优先，PRD 防幻觉设计）
- 新表 soc_eol_reference：预置 EOL 参考表（pattern 子串匹配 + 最长模式优先）
- 种子 ~33 条常见 OS/Server EOL（口径：各厂商官方生命周期页，2026-08 核对；
  无单一权威日期或按政策推算的条目标记 source='preset_unverified'，UI 透出“预估”，
  PRD 要求人工确认后再转 preset）

幂等：全部 IF NOT EXISTS / WHERE NOT EXISTS。
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (pattern, display_name, eol_date, source, notes)
#   source=preset            官方明确日期（可直接用于判定）
#   source=preset_unverified 社区/预估口径，PRD 要求人工确认后再改 preset（UI 透出“预估”）
EOL_SEED = [
    # Ubuntu LTS（ESM 前标准支持期，5 年官方政策）
    ("ubuntu 16.04", "Ubuntu 16.04 LTS", "2021-04-30", "preset", None),
    ("ubuntu 18.04", "Ubuntu 18.04 LTS", "2023-05-31", "preset", None),
    ("ubuntu 20.04", "Ubuntu 20.04 LTS", "2025-05-31", "preset", "ESM 延长至 2030-04（付费）"),
    ("ubuntu 22.04", "Ubuntu 22.04 LTS", "2027-04-30", "preset", None),
    ("ubuntu 24.04", "Ubuntu 24.04 LTS", "2029-04-30", "preset", None),
    ("ubuntu 26.04", "Ubuntu 26.04 LTS", "2031-04-30", "preset_unverified",
     "按 Canonical LTS 5 年标准支持政策推算，发布后请核对官方"),
    # CentOS
    ("centos 6", "CentOS 6", "2020-11-30", "preset", None),
    ("centos 7", "CentOS 7", "2024-06-30", "preset", None),
    ("centos 8", "CentOS 8", "2021-12-31", "preset", None),
    ("centos stream 8", "CentOS Stream 8", "2024-05-31", "preset", None),
    ("centos stream 9", "CentOS Stream 9", "2027-05-31", "preset", None),
    # Debian（含 LTS 期）
    ("debian 10", "Debian 10 Buster", "2024-06-30", "preset", None),
    ("debian 11", "Debian 11 Bullseye", "2026-08-31", "preset", "LTS 延长至 2026-08-31"),
    ("debian 12", "Debian 12 Bookworm", "2028-06-30", "preset", None),
    ("debian 13", "Debian 13 Trixie", "2030-06-30", "preset_unverified",
     "按 Debian 5 年（3 年常规 + 2 年 LTS）规律推算"),
    # Windows 桌面/服务器（微软官方生命周期）
    ("windows 7", "Windows 7 / Server 2008 R2", "2020-01-14", "preset", None),
    ("windows 8.1", "Windows 8.1", "2023-01-10", "preset", None),
    ("windows 10", "Windows 10", "2025-10-14", "preset", "消费者版本终止支持日"),
    ("windows 11", "Windows 11", "2026-10-13", "preset_unverified",
     "按 24H2 家庭/专业版终止日；Win11 按大版本滚动，实际以具体 build 的微软公告为准"),
    ("windows server 2008", "Windows Server 2008", "2020-01-14", "preset", None),
    ("windows server 2012", "Windows Server 2012/R2", "2023-10-10", "preset", None),
    ("windows server 2016", "Windows Server 2016", "2027-01-12", "preset", None),
    ("windows server 2019", "Windows Server 2019", "2029-01-09", "preset", None),
    ("windows server 2022", "Windows Server 2022", "2031-10-14", "preset", None),
    # RHEL 系
    ("rocky 8", "Rocky Linux 8", "2029-05-31", "preset", None),
    ("rocky 9", "Rocky Linux 9", "2032-05-31", "preset", None),
    ("almalinux 8", "AlmaLinux 8", "2029-12-31", "preset", None),
    ("almalinux 9", "AlmaLinux 9", "2032-12-31", "preset", None),
    # 国产/云厂商发行版（阿里云官方生命周期表 help.aliyun.com/zh/ecs/user-guide/alibaba-cloud-linux）
    ("alibaba cloud 2", "Alibaba Cloud Linux 2", "2026-03-31", "preset",
     "官方：扩展支持 2024.04-2026.03，停止支持 2026.03.31"),
    ("alibaba cloud 3", "Alibaba Cloud Linux 3", "2034-03-31", "preset",
     "官方：维护 2026.04-2031.03、扩展 2031.04-2034.03，停止支持 2034.03.31"),
    ("alibaba cloud 4", "Alibaba Cloud Linux 4", "2038-06-30", "preset",
     "官方：扩展支持 2035.07-2038.06，停止支持 2038.06.30"),
    ("openeuler 22.03", "openEuler 22.03 LTS", "2026-06-30", "preset_unverified",
     "社区 LTS 4 年支持；SP4 邮件列表称“预计维护至 26 年 6 月”且仍在收延期需求，无单一权威日期"),
]


def upgrade() -> None:
    # ---- 1. soc_assets 扩列（幂等） ----
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS purchase_date DATE")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS warranty_end DATE")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS expected_eol DATE")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS expected_eol_source VARCHAR(20) DEFAULT 'preset'")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_assets_expected_eol
        ON soc_assets (expected_eol) WHERE expected_eol IS NOT NULL
    """)

    # ---- 2. EOL 参考表 ----
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_eol_reference (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pattern VARCHAR(100) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            eol_date DATE NOT NULL,
            source VARCHAR(20) DEFAULT 'preset',
            notes TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_eol_ref_enabled ON soc_eol_reference (enabled)
    """)

    # ---- 3. 种子（幂等：按 pattern 去重） ----
    for pattern, display, eol, src, notes in EOL_SEED:
        op.execute(f"""
            INSERT INTO soc_eol_reference (pattern, display_name, eol_date, source, notes, enabled)
            SELECT '{pattern}', '{display}', DATE '{eol}', '{src}',
                   {f"'{notes}'" if notes else "NULL"}, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_eol_reference WHERE pattern = '{pattern}'
            )
        """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS soc_eol_reference CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_soc_assets_expected_eol")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS expected_eol_source")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS expected_eol")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS warranty_end")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS purchase_date")
