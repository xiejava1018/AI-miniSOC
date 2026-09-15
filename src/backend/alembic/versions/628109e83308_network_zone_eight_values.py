"""network_zone 8 值改造（2026-XX-XX，CLAUDE.md §0 立项）

背景
====
原 5 值（intranet/dmz/office/management/other）有以下问题：

  - intranet 太粗，把生产核心 + 办公之外所有内网全压一起
  - other 是任意填的兜底，新形态资产（云、蜜罐）填到这里 = 分类失效
  - 缺公网维度：云服务器（ECS/CVM）该填什么没答案
  - 缺开发/测试维度：DevOps 资产混在生产会污染告警/风险评分
  - 缺隔离区维度：蜜罐/应急隔离区属 SOC 资产，应独立告警处理

业界参考：NIST SP800-53、Cisco 5 区模型、AWS/阿里云 VPC 安全域。

改造方案（8 值）
================

  public         公网区       直接面向互联网的入口（云 SLB/CDN/对外 API Gateway）
  dmz            DMZ          对外服务前置（Web 前置、反向代理前置、VPN 接入）
  production     生产内网     业务核心（生产 DB、应用服务器、微服务，带等保）
  office         办公网       员工办公终端（PC、笔记本、打印机）
  dev            开发测试网   开发/测试/Staging 环境（与生产严格隔离）
  management     管理网/带外  堡垒机/iLO/iDRAC/带外管理
  isolated       隔离区       蜜罐/应急隔离/取证区
  unknown        未分类       真兜底（≠'other'，触发人工复核）

旧值 → 新值 回填规则（在 upgrade 里直接 UPDATE，避免另写脚本）
====================================================================

  intranet  → production          （大多数历史"内网"都是生产；少量测试机 → dev 由后续脚本细化）
  dmz       → dmz                 （保留）
  office    → office              （保留）
  management → management           （保留）
  other     → unknown             （语义对齐：other 不可信，unknown 才是真兜底）

更精细的回填（按 asset_type/os_name 区分 dev 等）由 scripts/backfill_network_zone.py
提供 idempotent 二次回填（独立运行，可选）。

约束变更（CHECK）
==================
旧 CHECK: ('intranet', 'dmz', 'office', 'management', 'other')
新 CHECK: 8 个值（见上）

落地顺序（关键：先 DROP CHECK 再 UPDATE 再 ADD CHECK）
====================================================
PostgreSQL CHECK 约束默认为 IMMEDIATE——每行 UPDATE 立即检查。
老 CHECK 是 5 值，UPDATE 把 'intranet' → 'production' 在老 CHECK 下就会拒。
所以必须：
1. DROP 旧 CHECK
2. UPDATE 把所有现有行映射到新枚举（老值已不再受约束，不会报）
3. ADD 新 CHECK
4. UPDATE 列 COMMENT
5. 字典表 sys_dict 里 network_zone 由 scripts/init_system_data.py seed 时自动新增/去重

⚠️ 此顺序错了第一次跑会在 UPDATE 阶段报 CheckViolation（已踩坑修复）。

合并 alembic 双 head：down_revision = ('r4s5t6u7v8w9', 'v7w8x9y0z1a2')。
network_zone 是 schema 级公共改造，不属于任一条业务线分支。
原 head 数 2 → 1（CLAUDE.md §0 同步更新）。

Revision ID: 628109e83308
Revises: r4s5t6u7v8w9, v7w8x9y0z1a2
Create Date: 2026-XX-XX
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "628109e83308"
down_revision: Union[str, Sequence[str], None] = ("r4s5t6u7v8w9", "v7w8x9y0z1a2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 旧 → 新 映射
_OLD_TO_NEW = {
    "intranet":   "production",   # 历史"内网"默认按生产处理；dev 由 backfill 脚本二次细挖
    "dmz":        "dmz",
    "office":     "office",
    "management": "management",
    "other":      "unknown",      # 'other' 不可信，统一为 unknown 触发人工复核
}

# 新枚举全集
_NEW_ZEN = ("public", "dmz", "production", "office", "dev", "management", "isolated", "unknown")


def upgrade() -> None:
    """Upgrade schema.

    顺序关键：先 DROP 旧 CHECK → 再 UPDATE 数据 → 再 ADD 新 CHECK。
    PG CHECK 默认 IMMEDIATE，老约束拒绝新枚举值，先 UPDATE 会报 CheckViolation。
    """
    # === Step 1: DROP 旧 CHECK（先解放 UPDATE）===
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")

    # === Step 2: 数据迁移（老 5 全部映射到新 8 集合内）===
    # 用 CASE 而不是循环 UPDATE：单语句、原子、自动处理不在白名单的边缘值
    op.execute(
        f"""
        UPDATE soc_assets
        SET network_zone = CASE network_zone
            {' '.join(f"WHEN '{old}' THEN '{new}'" for old, new in _OLD_TO_NEW.items())}
            ELSE 'unknown'  -- 兜底：旧库里有奇怪值的，统一归 unknown
        END
        """
    )

    # === Step 3: ADD 新 CHECK（8 值）===
    # PG CHECK 表达式里枚举必须显式带引号（裸值会被当列名/类型名报错）
    _new_zen_sql = ", ".join(f"'{v}'" for v in _NEW_ZEN)
    op.execute(
        f"""
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_network_zone_check
        CHECK (network_zone IN ({_new_zen_sql}))
        """
    )

    # === Step 4: 更新列 COMMENT（与字典 seed 8 值保持一致）===
    op.execute(
        "COMMENT ON COLUMN soc_assets.network_zone IS "
        "'网络区域（public/dmz/production/office/dev/management/isolated/unknown），"
        "含义详见 docs/design/network-zone-redesign.md'"
    )

    # server_default 保持 'other' 的语义在新枚举里 = 'unknown'，但这里不动 server_default
    # （DDL 锁成本 + 模型层 model_validate 时 'unknown' 已是合法值），model 默认值已修正。
    # 如需 DB 层默认 unknown，可加：
    #   ALTER TABLE soc_assets ALTER COLUMN network_zone SET DEFAULT 'unknown';


def downgrade() -> None:
    """Downgrade schema.

    顺序与 upgrade 对称：DROP CHECK → 反向 UPDATE → ADD 旧 CHECK。
    PG CHECK IMMEDIATE 会拒新值，先 UPDATE 同样会报。

    有损：'production' 全退回 'intranet'（粗粒度），
    其他新值（public/dev/isolated/unknown）映射回 'other'。
    生产环境禁止使用 downgrade。
    """
    # === Step 1: DROP 新 CHECK ===
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")

    # === Step 2: 反向映射数据 ===
    op.execute(
        """
        UPDATE soc_assets
        SET network_zone = CASE network_zone
            WHEN 'production' THEN 'intranet'
            WHEN 'public'     THEN 'other'
            WHEN 'dev'        THEN 'other'
            WHEN 'isolated'   THEN 'other'
            WHEN 'unknown'    THEN 'other'
            ELSE network_zone  -- dmz/office/management 保持
        END
        """
    )

    # === Step 3: ADD 旧 CHECK ===
    op.execute(
        "ALTER TABLE soc_assets ADD CONSTRAINT soc_assets_network_zone_check "
        "CHECK (network_zone IN ('intranet', 'dmz', 'office', 'management', 'other'))"
    )

    # === Step 4: 列 COMMENT ===
    op.execute(
        "COMMENT ON COLUMN soc_assets.network_zone IS "
        "'网络区域（intranet/dmz/office/management/other）'"
    )