"""配置 Schema 种子数据（X1E-11 / 2026-09-11）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.9

覆盖两个核心域：alert_governance（3 项）+ browsing_detection（5 项），
作为 Schema-driven Form 的范式样本。

执行：
    cd src/backend
    python scripts/seed_config_schema.py [--dry-run]

幂等：ON CONFLICT DO UPDATE 保证多次执行结果一致（仅更新非敏感描述字段）。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 让脚本可以直接 ``python scripts/seed_config_schema.py`` 运行
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.config_schema import ConfigSchema  # noqa: E402

logger = logging.getLogger(__name__)


SEED_ROWS = [
    # ---- alert_governance（3 项）----
    {
        "category": "alert_governance",
        "key": "triage_top_n",
        "label": "每日 AI 研判 TopN 簇数",
        "value_type": "number",
        "default_value": "20",
        "validation": {"min": 1, "max": 200},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "告警研判",
        "sort_order": 10,
        "help_text": "每日参与 AI 研判的告警簇数量，成本约等于 N 次/天模型调用",
        "editable": True,
    },
    {
        "category": "alert_governance",
        "key": "min_group_count",
        "label": "告警簇最小条数",
        "value_type": "number",
        "default_value": "1",
        "validation": {"min": 1, "max": 1000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "噪声抑制",
        "sort_order": 20,
        "help_text": "少于该值的簇不进入摘要/研判清单",
        "editable": True,
    },
    {
        "category": "alert_governance",
        "key": "suppress_rule_ids",
        "label": "噪声抑制规则 ID",
        "value_type": "string",
        "default_value": "",
        "validation": {"pattern": r"^[\d,\s]*$", "maxLength": 2000},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "噪声抑制",
        "sort_order": 21,
        "help_text": "逗号分隔；命中的告警簇将被移出必处理清单",
        "editable": True,
    },
    # ---- browsing_detection（5 项）----
    {
        "category": "browsing_detection",
        "key": "enabled",
        "label": "启用检测",
        "value_type": "boolean",
        "default_value": "true",
        "validation": {},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 10,
        "help_text": "总开关；停用后检测任务跳过本轮",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "interval_seconds",
        "label": "检测间隔（秒）",
        "value_type": "number",
        "default_value": "300",
        "validation": {"min": 60, "max": 3600},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 11,
        "help_text": "检测调度周期；下个周期生效",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "score_threshold",
        "label": "告警分数阈值",
        "value_type": "number",
        "default_value": "50",
        "validation": {"min": 0, "max": 100},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "评分",
        "sort_order": 20,
        "help_text": "分数高于该值的告警会被标记；下个周期生效",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "whitelist_domains",
        "label": "域名白名单",
        "value_type": "multiline",
        "default_value": (
            "*.miwifi.com,stun.chat.bilibili.com,stun.hitv.com,*.heytapmobi.com,"
            "stun.l.google.com,*.mozilla.com,musicstun.p2p.qq.com,*.easytier.cn"
        ),
        "validation": {"maxLength": 8000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "白名单",
        "sort_order": 30,
        "help_text": "逗号分隔；支持通配符（*）；命中域名跳过检测",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "night_start_hour",
        "label": "夜间起始小时",
        "value_type": "number",
        "default_value": "2",
        "validation": {"min": 0, "max": 23},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "夜间策略",
        "sort_order": 40,
        "help_text": "夜间模式的开始小时（0-23）",
        "editable": True,
    },
    # ---- browsing_detection 补齐（13 项，2026-09-12 路线 C 第一步）----
    # 默认值与 app/services/browsing_detection/config.py 的 _DEFAULTS 一致
    {
        "category": "browsing_detection",
        "key": "night_end_hour",
        "label": "夜间结束小时",
        "value_type": "number",
        "default_value": "5",
        "validation": {"min": 0, "max": 23},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "夜间策略",
        "sort_order": 41,
        "help_text": "夜间模式的结束小时（0-23）",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "night_count_threshold",
        "label": "夜间告警阈值",
        "value_type": "number",
        "default_value": "5",
        "validation": {"min": 1, "max": 1000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "夜间策略",
        "sort_order": 42,
        "help_text": "夜间时段内命中次数达到该值才告警",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "window_minutes",
        "label": "检测窗口（分钟）",
        "value_type": "number",
        "default_value": "5",
        "validation": {"min": 1, "max": 60},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 12,
        "help_text": "行为检测的滑动窗口长度",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "burst_threshold",
        "label": "突发阈值",
        "value_type": "number",
        "default_value": "30",
        "validation": {"min": 1, "max": 10000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "检测规则",
        "sort_order": 50,
        "help_text": "窗口内访问次数超过该值判定为突发访问（R2 突发规则）",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "severity_high",
        "label": "高风险分数线",
        "value_type": "number",
        "default_value": "80",
        "validation": {"min": 1, "max": 100},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "检测规则",
        "sort_order": 51,
        "help_text": "行为分超过该值判为高风险",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "severity_critical",
        "label": "严重风险分数线",
        "value_type": "number",
        "default_value": "100",
        "validation": {"min": 1, "max": 100},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "检测规则",
        "sort_order": 52,
        "help_text": "行为分超过该值判为严重风险",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "baseline_days",
        "label": "基线天数",
        "value_type": "number",
        "default_value": "7",
        "validation": {"min": 1, "max": 90},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基线",
        "sort_order": 60,
        "help_text": "行为基线计算使用的历史天数（受 Loki 保留 7 天限制）",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "tunnel_keywords",
        "label": "隧道/远控关键词",
        "value_type": "string",
        "default_value": r"easytier|frp|fatedier|zerotier|tailscale|n2n|wireguard|tinc|nebula|stun\.[a-z0-9-]+\.(xyz|top|cc|tk|buzz)",
        "validation": {"maxLength": 2000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "检测规则",
        "sort_order": 53,
        "help_text": "正则表达式；命中则触发 R5 隧道检测",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "blacklist_domains",
        "label": "域名黑名单",
        "value_type": "multiline",
        "default_value": "",
        "validation": {"maxLength": 8000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "名单",
        "sort_order": 31,
        "help_text": "逗号分隔；命中即记违规（R4 黑名单规则）",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "whitelist_ips",
        "label": "IP 白名单",
        "value_type": "multiline",
        "default_value": "",
        "validation": {"maxLength": 8000},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "白名单",
        "sort_order": 32,
        "help_text": "逗号分隔的内网 IP；名单内 IP 不检测",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "suppress_minutes",
        "label": "告警抑制（分钟）",
        "value_type": "number",
        "default_value": "30",
        "validation": {"min": 0, "max": 1440},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 13,
        "help_text": "同一 IP 同类告警的抑制窗口",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "notify_user_ids",
        "label": "通知用户 ID",
        "value_type": "string",
        "default_value": "",
        "validation": {"pattern": r"^[\d,\s]*$", "maxLength": 500},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "基本",
        "sort_order": 14,
        "help_text": "逗号分隔的用户 ID；检测到事件时推送站内通知，留空不推送",
        "editable": True,
    },
    {
        "category": "browsing_detection",
        "key": "rules_enabled",
        "label": "启用规则集",
        "value_type": "string",
        "default_value": "R1,R2,R3,R4,R5,R6",
        "validation": {"pattern": r"^(R[1-9](,R[1-9])*)?$", "maxLength": 100},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "检测规则",
        "sort_order": 54,
        "help_text": "逗号分隔的规则 ID（R1-R6）；留空全部停用",
        "editable": True,
    },
    # ---- captcha（2 项）----
    {
        "category": "captcha",
        "key": "captcha_enabled",
        "label": "启用登录验证码",
        "value_type": "boolean",
        "default_value": "true",
        "validation": {},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "登录安全",
        "sort_order": 10,
        "help_text": "启用后登录需输入图形验证码",
        "editable": True,
    },
    {
        "category": "captcha",
        "key": "captcha_expire_seconds",
        "label": "验证码有效期（秒）",
        "value_type": "number",
        "default_value": "300",
        "validation": {"min": 60, "max": 3600},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "登录安全",
        "sort_order": 11,
        "help_text": "验证码过期时间",
        "editable": True,
    },
    # ---- general（5 项，品牌/平台信息）----
    {
        "category": "general",
        "key": "system_name",
        "label": "系统名称",
        "value_type": "string",
        "default_value": "AI-miniSOC",
        "validation": {"maxLength": 100},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "品牌",
        "sort_order": 10,
        "help_text": "登录页/侧边栏/浏览器标题显示的系统名",
        "editable": True,
    },
    {
        "category": "general",
        "key": "system_logo",
        "label": "系统 Logo 地址",
        "value_type": "multiline",
        "default_value": "",
        "validation": {"maxLength": 100000},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "品牌",
        "sort_order": 11,
        "help_text": "图片 URL 或 data:image base64；留空用默认 Logo",
        "editable": True,
    },
    {
        "category": "general",
        "key": "system_copyright",
        "label": "版权信息",
        "value_type": "string",
        "default_value": "© 2026 AI-miniSOC",
        "validation": {"maxLength": 200},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "品牌",
        "sort_order": 12,
        "help_text": "登录页底部版权文字",
        "editable": True,
    },
    {
        "category": "general",
        "key": "system_description",
        "label": "系统描述",
        "value_type": "multiline",
        "default_value": "AI-driven mini Security Operation Center",
        "validation": {"maxLength": 500},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "品牌",
        "sort_order": 13,
        "help_text": "关于页/登录页展示的系统简介",
        "editable": True,
    },
    {
        "category": "general",
        "key": "allowed_hosts",
        "label": "允许访问的 Host",
        "value_type": "string",
        "default_value": "all",
        "validation": {"maxLength": 500},
        "effect_scope": "restart",
        "sensitive": False,
        "group_name": "运行时事实",
        "sort_order": 20,
        "help_text": "系统运行事实（只读）；配错会锁死前端访问，不提供界面修改",
        "editable": False,
    },
    # ---- security（6 项，认证与密码策略）----
    {
        "category": "security",
        "key": "password_min_length",
        "label": "密码最小长度",
        "value_type": "number",
        "default_value": "8",
        "validation": {"min": 6, "max": 64},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "密码策略",
        "sort_order": 10,
        "help_text": "新建/修改密码时强制的最小长度",
        "editable": True,
    },
    {
        "category": "security",
        "key": "password_require_uppercase",
        "label": "密码需含大写字母",
        "value_type": "boolean",
        "default_value": "true",
        "validation": {},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "密码策略",
        "sort_order": 11,
        "help_text": "密码必须包含至少一个大写字母",
        "editable": True,
    },
    {
        "category": "security",
        "key": "password_require_digit",
        "label": "密码需含数字",
        "value_type": "boolean",
        "default_value": "true",
        "validation": {},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "密码策略",
        "sort_order": 12,
        "help_text": "密码必须包含至少一个数字",
        "editable": True,
    },
    {
        "category": "security",
        "key": "max_login_attempts",
        "label": "最大登录失败次数",
        "value_type": "number",
        "default_value": "5",
        "validation": {"min": 1, "max": 20},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "登录锁定",
        "sort_order": 20,
        "help_text": "连续失败达到该次数后锁定账号",
        "editable": True,
    },
    {
        "category": "security",
        "key": "lockout_duration_minutes",
        "label": "锁定时长（分钟）",
        "value_type": "number",
        "default_value": "30",
        "validation": {"min": 1, "max": 1440},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "登录锁定",
        "sort_order": 21,
        "help_text": "账号触发锁定后的自动解锁时间",
        "editable": True,
    },
    {
        "category": "security",
        "key": "session_timeout_minutes",
        "label": "会话超时（分钟）",
        "value_type": "number",
        "default_value": "60",
        "validation": {"min": 5, "max": 1440},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "会话",
        "sort_order": 30,
        "help_text": "登录会话空闲超时时间",
        "editable": True,
    },
    # ---- sync（2 项）----
    {
        "category": "sync",
        "key": "sync_interval_minutes",
        "label": "同步间隔（分钟）",
        "value_type": "number",
        "default_value": "30",
        "validation": {"min": 5, "max": 1440},
        "effect_scope": "next_cycle",
        "sensitive": False,
        "group_name": "调度",
        "sort_order": 10,
        "help_text": "资产同步任务的调度间隔（下个调度周期生效）",
        "editable": True,
    },
    {
        "category": "sync",
        "key": "wazuh_api_url",
        "label": "Wazuh API 地址（已废弃）",
        "value_type": "string",
        "default_value": "",
        "validation": {"maxLength": 500},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "已废弃",
        "sort_order": 20,
        "help_text": "已废弃：Wazuh 地址已迁移到「数据源管理」（soc_data_sources）；本项保留仅作历史参考，修改无效",
        "editable": False,
    },
    # ---- push_rules（1 项）----
    {
        "category": "push_rules",
        "key": "rules",
        "label": "推送规则",
        "value_type": "json",
        "default_value": "{}",
        "validation": {},
        "effect_scope": "immediate",
        "sensitive": False,
        "group_name": "推送",
        "sort_order": 10,
        "help_text": "主动推送规则 JSON（60s 缓存）；通常由「通知推送」模块维护，也可在此手工调整",
        "editable": True,
    },
]


def upsert_schema_rows(db, dry_run: bool = False) -> int:
    """幂等写入种子数据。返回写入/更新条数。"""
    count = 0
    for row in SEED_ROWS:
        existing = (
            db.query(ConfigSchema)
            .filter(
                ConfigSchema.category == row["category"],
                ConfigSchema.key == row["key"],
            )
            .first()
        )
        if existing:
            existing.label = row["label"]
            existing.value_type = row["value_type"]
            existing.default_value = row["default_value"]
            existing.validation = row["validation"]
            existing.effect_scope = row["effect_scope"]
            existing.sensitive = row["sensitive"]
            existing.group_name = row["group_name"]
            existing.sort_order = row["sort_order"]
            existing.help_text = row["help_text"]
            existing.editable = row["editable"]
            count += 1
        else:
            db.add(
                ConfigSchema(
                    category=row["category"],
                    key=row["key"],
                    label=row["label"],
                    value_type=row["value_type"],
                    default_value=row["default_value"],
                    validation=row["validation"],
                    effect_scope=row["effect_scope"],
                    sensitive=row["sensitive"],
                    group_name=row["group_name"],
                    sort_order=row["sort_order"],
                    help_text=row["help_text"],
                    editable=row["editable"],
                )
            )
            count += 1
    if not dry_run:
        db.commit()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="预置配置 Schema 种子数据")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不提交")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # 同步驱动（脚本不用异步）
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # 确保表存在（生产已通过 alembic 创建，本地直跑也安全）
        Base.metadata.create_all(engine, tables=[ConfigSchema.__table__])
        n = upsert_schema_rows(db, dry_run=args.dry_run)
        logger.info("✅ 配置 Schema 种子数据写入完成：%d 条%s", n, "（dry-run）" if args.dry_run else "")
        return 0
    except Exception as e:
        logger.exception("❌ 写入失败：%s", e)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())