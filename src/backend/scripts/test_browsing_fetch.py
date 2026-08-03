#!/usr/bin/env python3
"""
M1 验证脚本：建表 + 初始化配置 + 从 Loki 拉取并解析日志

用法:
    cd src/backend
    ../../venv/bin/python scripts/test_browsing_fetch.py
"""
import sys
import os
from datetime import datetime, timedelta, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import engine, SessionLocal
from app.models.base import Base
# 导入模型确保被注册
import app.models  # noqa: F401
from app.services.browsing_detection.loki_client import LokiClient
from app.services.browsing_detection.log_parser import parse_loki_result


def ensure_tables():
    """建表（checkfirst，幂等）"""
    browsing_tables = [
        "soc_browsing_events",
        "soc_browsing_blacklist",
        "soc_browsing_baseline",
    ]
    Base.metadata.create_all(bind=engine, tables=[
        t for name, t in Base.metadata.tables.items() if name in browsing_tables
    ])
    print("✅ 表已就绪:", ", ".join(browsing_tables))


def init_config():
    """初始化配置（复用 init_browsing_config 逻辑）"""
    import importlib
    mod = importlib.import_module("scripts.init_browsing_config")
    mod.main()


def fetch_and_parse():
    """从 Loki 拉取最近 5 分钟日志并解析"""
    client = LokiClient()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(end.timestamp() * 1_000_000_000)

    print(f"\n拉取窗口: {start:%H:%M:%S} ~ {end:%H:%M:%S} (UTC)")
    streams = client.query_range(
        query='{exporter="OTLP"}',
        start_ns=start_ns,
        end_ns=end_ns,
        limit=5000,
    )

    total_values = sum(len(s.get("values", [])) for s in streams)
    print(f"Loki 返回 {len(streams)} 个流，原始行数 {total_values}")

    records = parse_loki_result(streams)
    print(f"解析后（去重后）记录数: {len(records)}")

    if not records:
        print("⚠️  窗口内无日志，请确认 Loki 数据正常或扩大窗口")
        return

    # 统计
    url_recs = [r for r in records if r.action == "url"]
    app_recs = [r for r in records if r.action == "app"]
    internal = [r for r in records if r.is_internal]
    print(f"  访问网址: {len(url_recs)} 条 | 使用应用: {len(app_recs)} 条")
    print(f"  内网IP: {len(internal)} 条 | 公网IP: {len(records) - len(internal)} 条")

    # IP 分布 top5
    from collections import Counter
    ip_counter = Counter(r.ip for r in records if r.is_internal)
    print("\n内网IP活跃度 top5:")
    for ip, n in ip_counter.most_common(5):
        print(f"   {ip:>16}: {n} 条")

    # 域名样例
    domains = Counter(r.domain for r in url_recs if r.domain)
    print("\n访问域名 top5:")
    for d, n in domains.most_common(5):
        print(f"   {d:>40}: {n} 次")

    print("\n记录样例:")
    for r in records[:3]:
        print(f"   [{r.ts:%H:%M:%S}] ip={r.ip} action={r.action} "
              f"{'domain=' + r.domain if r.domain else 'apptype=' + r.apptype}")

    client.close()


def main():
    print("=" * 60)
    print("M1 验证：建表 → 初始化配置 → Loki 拉取解析")
    print("=" * 60)
    ensure_tables()
    init_config()
    fetch_and_parse()
    print("\n✅ M1 验证通过")


if __name__ == "__main__":
    main()
