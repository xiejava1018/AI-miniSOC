#!/usr/bin/env python3
"""
初始化行为检测的默认配置项（写入 soc_system_config, category=browsing_detection)

用法:
    cd src/backend
    ../../venv/bin/python scripts/init_browsing_config.py
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.system_config import SystemConfig
from app.services.browsing_detection.config import CONFIG_CATEGORY, _DEFAULTS

DEFAULTS = {
    "enabled": ("true", "bool", "检测总开关"),
    "interval_seconds": ("300", "int", "轮询间隔(秒)"),
    "window_minutes": ("5", "int", "检测窗口(分钟)"),
    "score_threshold": ("50", "int", "触发阈值"),
    "severity_high": ("80", "int", "high 分界"),
    "severity_critical": ("100", "int", "critical 分界"),
    "burst_threshold": ("30", "int", "R2 高频阈值(次/窗口)"),
    "night_start_hour": ("2", "int", "R5 凌晨起始"),
    "night_end_hour": ("5", "int", "R5 凌晨结束"),
    "night_count_threshold": ("5", "int", "R5 凌晨条数阈值"),
    "tunnel_keywords": (
        "easytier|stun|frp|fatedier|zerotier|tailscale|n2n|wireguard|tinc|nebula",
        "str",
        "R4 隧道关键词正则",
    ),
    "blacklist_domains": ("", "str", "R1 手动黑名单(逗号分隔)"),
    "whitelist_domains": ("", "str", "全局白名单域名(逗号分隔)"),
    "whitelist_ips": ("", "str", "免检IP(逗号分隔)"),
    "suppress_minutes": ("30", "int", "事件抑制期(分钟)"),
    "notify_user_ids": ("", "str", "通知目标用户ID(逗号分隔,空=管理员)"),
    "baseline_days": ("7", "int", "基线保留天数"),
    "rules_enabled": ("R1,R2,R3,R4,R5,R6", "str", "启用的规则集合"),
}


def main():
    db = SessionLocal()
    try:
        existing = {
            r.key for r in db.query(SystemConfig).filter(SystemConfig.category == CONFIG_CATEGORY).all()
        }
        created = 0
        for key, (value, vtype, desc) in DEFAULTS.items():
            if key in existing:
                continue
            cfg = SystemConfig(
                category=CONFIG_CATEGORY,
                key=key,
                value=value,
                value_type=vtype,
                description=desc,
            )
            db.add(cfg)
            created += 1
        db.commit()
        total = db.query(SystemConfig).filter(SystemConfig.category == CONFIG_CATEGORY).count()
        print(f"✅ 新增 {created} 条配置，当前 {CONFIG_CATEGORY} 共 {total} 条")
        for r in db.query(SystemConfig).filter(SystemConfig.category == CONFIG_CATEGORY).order_by(SystemConfig.key).all():
            print(f"   {r.key:.<28} = {r.value}  [{r.value_type}]")
    finally:
        db.close()


if __name__ == "__main__":
    main()
