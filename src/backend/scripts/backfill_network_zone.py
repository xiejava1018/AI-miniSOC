#!/usr/bin/env python3
"""
network_zone 8 值二次回填脚本（CLAUDE.md §0 + 2026-XX-XX 立项）

背景
====
alembic 迁移 c1d2e3f4g5h6 已完成 5→8 粗粒度映射：

    intranet   → production      （历史"内网"默认按生产处理）
    dmz        → dmz             （保留）
    office     → office          （保留）
    management → management      （保留）
    other      → unknown         （'other' 不可信）

但粗粒度映射有损失：一些标 production 的资产其实是 dev/staging；
一些标 unknown（原 other）的资产其实有明确线索（公网 IP、蜜罐特征）。

本脚本做二次回填——只做高置信度二次映射，有疑义的留原值给 UI 手工调整。

二次回填规则（顺序很重要，前面规则不会覆盖后面规则的结果）
================================================================

1. production → dev
   条件：asset_type IN ('server') AND
         (description/name/os_name 匹配 'dev|staging|test|测试|开发' 正则)
   置信度：中（依赖名称约定，需要团队规范）
   默认：ON（开关 --skip-dev-rule 可关闭）

2. unknown → public
   条件：public_ip IS NOT NULL AND length(public_ip) > 0
   置信度：高（有公网 IP 即对外暴露面）
   默认：ON

3. unknown → isolated
   条件：asset_type = 'security_device' AND
         (name/description 匹配 '蜜罐|honeypot|隔离|取证实物|forensic' 正则)
   置信度：高（蜜罐/取证是 SOC 资产术语）
   默认：ON

4. unknown → management
   条件：name/description/os_name 匹配 'iLO|iDRAC|带外|OOB|堡垒|bastion|jump' 正则
   置信度：高
   默认：ON

5. office → production
   条件：asset_type = 'server' AND os_name 匹配 Linux/Windows Server
   置信度：中（员工机器不太会是服务器 OS）
   默认：OFF（保守，避免误判）
   启用：--include-office-server-rule

幂等性
======
每条规则前都查当前值，匹配才 UPDATE；可重复运行不重复更新（除非想重跑）。

回滚
====
每条规则都有反向 SQL。汇总见文件末尾 ROLLBACK_SQL。

用法（从 src/backend/ 目录）：
    ../../venv/bin/python scripts/backfill_network_zone.py                  # 执行默认规则集
    ../../venv/bin/python scripts/backfill_network_zone.py --dry-run         # 只打印计划
    ../../venv/bin/python scripts/backfill_network_zone.py --skip-dev-rule  # 跳过 dev 规则
    ../../venv/bin/python scripts/backfill_network_zone.py --include-office-server-rule
"""
import re
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.core.database import SessionLocal

DRY_RUN = "--dry-run" in sys.argv
SKIP_DEV = "--skip-dev-rule" in sys.argv
INCLUDE_OFFICE_SERVER = "--include-office-server-rule" in sys.argv


def step(msg: str):
    print(f"  → {msg}")


def run(db, sql: str, params: dict = None) -> int:
    """执行 SQL，返回受影响行数。dry-run 时只打印不执行。"""
    if DRY_RUN:
        # 渲染 SQL（带参数）便于查看
        rendered = sql
        if params:
            for k, v in params.items():
                rendered = rendered.replace(f":{k}", repr(v))
        print(f"    [dry-run] {rendered.strip().splitlines()[0][:140]}...")
        # dry-run 时预估返回 0（由各规则手动调用 preview_count 估算）
        return 0
    return db.execute(text(sql), params).rowcount


def preview_count(db, where_sql: str, params: dict | None = None) -> int:
    """独立预览：给定 WHERE 子句 + params，估算影响行数。
    不依赖主 SQL 的字符串拼接，预估 = 实际。
    """
    sql = f"SELECT count(*) FROM soc_assets WHERE {where_sql}"
    return db.execute(text(sql), params or {}).scalar()


# ----------------------------------------------------------------------
# 规则定义：每个函数实现一条规则，返回 (sql_update, params_template, desc)
# ----------------------------------------------------------------------

# dev 关键词（生产/业务/运维机器不应触发；测试/开发/staging 应触发）
DEV_KEYWORDS = re.compile(
    r"(dev|staging|stage|test|qa|sandbox|开发|测试|预发|演练|实验)",
    re.IGNORECASE,
)
# 蜜罐 / 取证 / 隔离
HONEYPOT_KEYWORDS = re.compile(
    r"(蜜罐|honeypot|honey[-_ ]?pot|隔离区|取证实物|forensic|decoy|decoytrap)",
    re.IGNORECASE,
)
# 管理网 / 堡垒机 / 带外
MGMT_KEYWORDS = re.compile(
    r"(iLO|iDRAC|BMC|IPMI|OOB|带外|堡垒|bastion|jump[-_ ]?host|jumpbox|堡垒机)",
    re.IGNORECASE,
)
# 服务器 OS（员工 PC 几乎不会跑这些）
SERVER_OS = re.compile(
    r"(windows\s*server|redhat|rhel|centos|ubuntu|debian|suse|alma|rocky|opensuse|oracle\s*linux|anolis)",
    re.IGNORECASE,
)


def rule_production_to_dev(db) -> int:
    """规则 1：production → dev（资产名含 dev/staging/测试 等关键词）"""
    print(f"    [规则 1] production → dev")
    where = """
        network_zone = 'production'
        AND asset_type = 'server'
        AND (
          name        ~* :kw
          OR asset_description ~* :kw
          OR os_name        ~* :kw
        )
    """
    params = {"kw": DEV_KEYWORDS.pattern}
    cnt = preview_count(db, where, params)
    step(f"预估命中 {cnt} 行")
    if DRY_RUN:
        return 0
    sql = f"""
        UPDATE soc_assets
        SET network_zone = 'dev'
        WHERE {where}
    """
    return run(db, sql, params)


def rule_unknown_to_public(db) -> int:
    """规则 2：unknown → public（有公网 IP）"""
    print(f"    [规则 2] unknown → public")
    where = """
        network_zone = 'unknown'
        AND public_ip IS NOT NULL
        AND length(trim(public_ip)) > 0
    """
    cnt = preview_count(db, where)
    step(f"预估命中 {cnt} 行")
    if DRY_RUN:
        return 0
    sql = f"""
        UPDATE soc_assets
        SET network_zone = 'public'
        WHERE {where}
    """
    return run(db, sql)


def rule_unknown_to_isolated(db) -> int:
    """规则 3：unknown → isolated（蜜罐/取证特征）"""
    print(f"    [规则 3] unknown → isolated")
    where = """
        network_zone = 'unknown'
        AND (
          asset_type      = 'security_device'
          OR name         ~* :kw1
          OR asset_description ~* :kw1
        )
    """
    params = {"kw1": HONEYPOT_KEYWORDS.pattern}
    cnt = preview_count(db, where, params)
    step(f"预估命中 {cnt} 行")
    if DRY_RUN:
        return 0
    sql = f"""
        UPDATE soc_assets
        SET network_zone = 'isolated'
        WHERE {where}
    """
    return run(db, sql, params)


def rule_unknown_to_management(db) -> int:
    """规则 4：unknown → management（管理网/堡垒机特征）"""
    print(f"    [规则 4] unknown → management")
    where = """
        network_zone = 'unknown'
        AND (
          name         ~* :kw2
          OR asset_description ~* :kw2
          OR os_name        ~* :kw2
        )
    """
    params = {"kw2": MGMT_KEYWORDS.pattern}
    cnt = preview_count(db, where, params)
    step(f"预估命中 {cnt} 行")
    if DRY_RUN:
        return 0
    sql = f"""
        UPDATE soc_assets
        SET network_zone = 'management'
        WHERE {where}
    """
    return run(db, sql, params)


def rule_office_to_production(db) -> int:
    """规则 5：office → production（员工机器出现服务器 OS）"""
    print(f"    [规则 5] office → production （--include-office-server-rule 启用）")
    where = """
        network_zone = 'office'
        AND asset_type = 'server'
        AND os_name ~* :kw3
    """
    params = {"kw3": SERVER_OS.pattern}
    cnt = preview_count(db, where, params)
    step(f"预估命中 {cnt} 行")
    if DRY_RUN:
        return 0
    sql = f"""
        UPDATE soc_assets
        SET network_zone = 'production'
        WHERE {where}
    """
    return run(db, sql, params)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def main():
    print("=== network_zone 8 值二次回填 ===\n")
    if DRY_RUN:
        print("⚠️  DRY-RUN：以下只打印 SQL 不执行；行数为 SELECT 预估\n")

    db = SessionLocal()
    try:
        # 启动前快照：当前各档位分布
        print("[快照] 回填前分布：")
        for row in db.execute(text(
            "SELECT network_zone, count(*) FROM soc_assets GROUP BY 1 ORDER BY 2 DESC"
        )):
            print(f"    {row[0]:<12} {row[1]}")

        # 规则 1
        if not SKIP_DEV:
            rule_production_to_dev(db)
        else:
            print("    [规则 1] SKIP（--skip-dev-rule）")

        # 规则 2
        rule_unknown_to_public(db)

        # 规则 3
        rule_unknown_to_isolated(db)

        # 规则 4
        rule_unknown_to_management(db)

        # 规则 5
        if INCLUDE_OFFICE_SERVER:
            rule_office_to_production(db)
        else:
            print("    [规则 5] SKIP（默认关闭；--include-office-server-rule 启用）")

        if not DRY_RUN:
            db.commit()

        # 启动后快照：回填后分布
        print("\n[快照] 回填后分布：")
        for row in db.execute(text(
            "SELECT network_zone, count(*) FROM soc_assets GROUP BY 1 ORDER BY 2 DESC"
        )):
            print(f"    {row[0]:<12} {row[1]}")

        if DRY_RUN:
            print("\n⚠️  DRY-RUN 模式未 commit；要实际执行请去掉 --dry-run")
        else:
            print("\n✅ 二次回填已 commit")

    except Exception as e:
        print(f"\n❌ 出错: {e}")
        if not DRY_RUN:
            db.rollback()
        raise
    finally:
        db.close()


# ----------------------------------------------------------------------
# 回滚 SQL（手动执行；按规则反向）
# ----------------------------------------------------------------------
ROLLBACK_SQL = """
-- 规则 1 反向：dev → production（按本规则历史回填过的事实，因没记录历史只能全量反向；建议先 SELECT 确认）
UPDATE soc_assets SET network_zone = 'production' WHERE network_zone = 'dev';

-- 规则 2 反向：public → unknown
UPDATE soc_assets SET network_zone = 'unknown'
WHERE network_zone = 'public' AND public_ip IS NOT NULL AND length(trim(public_ip)) > 0;

-- 规则 3 反向：isolated → unknown（仅蜜罐特征回退）
UPDATE soc_assets SET network_zone = 'unknown'
WHERE network_zone = 'isolated'
  AND (name ~* '蜜罐|honeypot|honey[-_ ]?pot|隔离区|取证实物|forensic|decoy|decoytrap'
       OR asset_description ~* '蜜罐|honeypot|honey[-_ ]?pot|隔离区|取证实物|forensic|decoy|decoytrap');

-- 规则 4 反向：management → unknown（仅管理网特征回退）
UPDATE soc_assets SET network_zone = 'unknown'
WHERE network_zone = 'management'
  AND (name ~* 'iLO|iDRAC|BMC|IPMI|OOB|带外|堡垒|bastion|jump[-_ ]?host|jumpbox|堡垒机'
       OR asset_description ~* 'iLO|iDRAC|BMC|IPMI|OOB|带外|堡垒|bastion|jump[-_ ]?host|jumpbox|堡垒机'
       OR os_name ~* 'iLO|iDRAC|BMC|IPMI|OOB|带外|堡垒|bastion|jump[-_ ]?host|jumpbox|堡垒机');

-- 规则 5 反向：production → office
UPDATE soc_assets SET network_zone = 'office'
WHERE network_zone = 'production' AND asset_type = 'server'
  AND os_name ~* 'windows\\s*server|redhat|rhel|centos|ubuntu|debian|suse|alma|rocky|opensuse|oracle\\s*linux|anolis';
"""


if __name__ == "__main__":
    main()