#!/usr/bin/env python3
"""
同步 URLhaus 威胁情报恶意域名到黑名单

用法:
    cd src/backend
    ../../venv/bin/python scripts/sync_threat_intel.py [--limit 5000]
"""
import sys
import os
import argparse

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.services.browsing_detection.threat_intel import ThreatIntelSync
from app.services.browsing_detection.config import config_cache


def main():
    parser = argparse.ArgumentParser(description="同步 URLhaus 威胁情报")
    parser.add_argument("--limit", type=int, default=5000, help="最多拉取域名数")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print(f"开始同步 URLhaus 威胁情报（limit={args.limit}）...")
        svc = ThreatIntelSync(db)
        result = svc.sync_urlhaus(limit=args.limit)
        config_cache.invalidate()
        if result.get("error"):
            print(f"⚠️  {result['error']}")
        print(f"✅ 源: {result['source']}")
        print(f"   拉取域名: {result['fetched']}")
        print(f"   新增黑名单: {result['new']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
