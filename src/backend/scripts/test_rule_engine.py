#!/usr/bin/env python3
"""
规则引擎验证脚本：用低阈值单独验证 6 条规则（R1~R6）都能正确触发

用法:
    cd src/backend
    ../../venv/bin/python scripts/test_rule_engine.py
"""
import sys
import os
from datetime import datetime, timedelta, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal, engine
from app.models.base import Base
import app.models  # noqa
from app.models.browsing_blacklist import BrowsingBlacklist
from app.services.browsing_detection.config import DetectionConfig
from app.services.browsing_detection.rule_engine import RuleEngine
from app.services.browsing_detection.log_parser import BrowsingRecord


def ensure_tables():
    names = {"soc_browsing_events", "soc_browsing_blacklist", "soc_browsing_baseline"}
    Base.metadata.create_all(bind=engine, tables=[t for n, t in Base.metadata.tables.items() if n in names])


def make_rec(ip, domain="", apptype="", minutes_ago=0, hour=None):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    if hour is not None:
        # hour 传北京时间，转 UTC
        ts = ts.replace(hour=(hour - 8) % 24, minute=10, second=0)
    return BrowsingRecord(ip=ip, domain=domain.lower(), apptype=apptype,
                          action="url" if domain else "app", ts=ts)


def make_test_config():
    """低阈值配置，便于单独验证每条规则"""
    return DetectionConfig(
        score_threshold=10,          # 低阈值，单规则即可触发
        severity_high=30,
        severity_critical=90,
        burst_threshold=5,
        night_start_hour=2,
        night_end_hour=5,
        night_count_threshold=3,
        tunnel_keywords="easytier|stun|frp|zerotier|tailscale",
        rules_enabled="R1,R2,R3,R4,R5,R6",
    )


def check(label, findings, expect_rule):
    ok = False
    for f in findings:
        rules = [h["rule"] for h in f.rule_hits]
        if expect_rule in rules:
            print(f"  ✅ {label}: score={f.score} rules={rules}")
            ok = True
            break
    if not ok:
        rules = [h["rule"] for h in findings[0].rule_hits] if findings else []
        print(f"  ❌ {label}: 未命中 {expect_rule}，实际 rules={rules}")


def main():
    ensure_tables()
    db = SessionLocal()
    try:
        # 预置黑名单
        bl = db.query(BrowsingBlacklist).filter(BrowsingBlacklist.domain == "evil-malware.example.com").first()
        if not bl:
            db.add(BrowsingBlacklist(domain="evil-malware.example.com", source="manual", reason="测试"))
            db.commit()

        cfg = make_test_config()
        now = datetime.now(timezone.utc)
        win_start, win_end = now - timedelta(minutes=5), now

        print("=" * 60)
        print("规则引擎验证（低阈值，单独验证每条规则）")
        print("=" * 60)

        # R1 恶意域名（黑名单命中，known_map 含该域名避免R3干扰）
        print("\n[R1 恶意域名]")
        e = RuleEngine(db, cfg)
        f = e.evaluate([make_rec("10.0.0.1", "evil-malware.example.com")],
                       {"10.0.0.1": {"evil-malware.example.com"}}, win_start, win_end)
        check("R1", f, "R1")

        # R2 突发高频（8条 > 阈值5，known_map 含域名避免R3）
        print("\n[R2 突发高频]")
        e = RuleEngine(db, cfg)
        recs = [make_rec("10.0.0.2", "burst.test", minutes_ago=i) for i in range(8)]
        f = e.evaluate(recs, {"10.0.0.2": {"burst.test"}}, win_start, win_end)
        check("R2", f, "R2")

        # R3 基线偏离（新域名，known_map 空）
        print("\n[R3 基线偏离]")
        e = RuleEngine(db, cfg)
        f = e.evaluate([make_rec("10.0.0.3", "totally-new.test")], {"10.0.0.3": set()}, win_start, win_end)
        check("R3", f, "R3")

        # R4 隧道/穿透（known_map 含域名避免R3）
        print("\n[R4 隧道/穿透]")
        e = RuleEngine(db, cfg)
        f = e.evaluate([make_rec("10.0.0.4", "relay.easytier.cn")],
                       {"10.0.0.4": {"relay.easytier.cn"}}, win_start, win_end)
        check("R4", f, "R4")

        # R5 凌晨活跃（北京时间3点，6条 > 阈值3）
        print("\n[R5 凌晨活跃]")
        e = RuleEngine(db, cfg)
        recs = [make_rec("10.0.0.5", "night.test", hour=3) for _ in range(6)]
        f = e.evaluate(recs, {"10.0.0.5": {"night.test"}}, win_start, win_end)
        check("R5", f, "R5")

        # R6 可疑域名特征 - IP直连（known_map 含避免R3）
        print("\n[R6 可疑域名-IP直连]")
        e = RuleEngine(db, cfg)
        f = e.evaluate([make_rec("10.0.0.6", "203.119.206.10")],
                       {"10.0.0.6": {"203.119.206.10"}}, win_start, win_end)
        check("R6-IP", f, "R6")

        # R6 可疑域名特征 - 超长随机
        print("\n[R6 可疑域名-超长随机]")
        e = RuleEngine(db, cfg)
        long_domain = "x" * 70 + ".example.com"
        f = e.evaluate([make_rec("10.0.0.7", long_domain)], {"10.0.0.7": {long_domain}}, win_start, win_end)
        check("R6-Long", f, "R6")

        print("\n✅ 规则引擎验证完成")
    finally:
        db.close()


if __name__ == "__main__":
    main()
