#!/usr/bin/env python3
"""
network_segment 回填脚本（2026-XX-XX，配合 network_zone 8 值改造）

背景
====
76 台资产 network_segment 全是 'default'，多网段环境（内网 + 多云）下
唯一约束 (network_segment, asset_ip) 的区分能力完全没用上。

命名规范（与用户确认，2026-XX-XX）：
  hq-lan                内网主段 192.168.0.0/24（TP-Link 主网）
  hq-lan-199            内网次段 192.168.199.0/24（独立广播域，访客/次 SSID）
  aliyun-172.18         阿里云 VPC 172.18.x（两台 ECS 确认同 VPC）
  volc-172.16           火山引擎 VPC 172.16.x（lavm 前缀命名规则）
  vps-202.189.23.82     自建 VPS（私网 172.16.0.51 与火山引擎撞段，按公网 IP 区分）
  vps-154.219.98.59     自建 VPS（asset_ip 即公网 IP）

不动：
  127.0.0.1 / 0.0.0.0   数据质量问题（wazuh agent 上报错误 / tplink 无效 IP），
                        保持 default，后续走资产稽核流程清理。

幂等：WHERE 条件限定 network_segment != 目标值，重复跑 0 影响。
唯一约束安全：asset_ip 全局唯一（已核实 76 台无重复 IP），改 segment 不会
产生 (segment, ip) 撞车。

用法（在 src/backend 下）：
    ./venv/bin/python scripts/backfill_network_segment.py --dry-run
    ./venv/bin/python scripts/backfill_network_segment.py
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.network_segment import infer_segment

DRY_RUN = "--dry-run" in sys.argv

# (规则名, 目标 segment, WHERE 条件, params)
# 规则必须与 app/services/network_segment.py 的 _EXACT/_PREFIX 保持一致——
# 那里是唯一规则来源（sync handler 增量同步也用它），本脚本只做存量批量回填。
RULES = [
    ("内网主段 192.168.0.0/24", "hq-lan",
     "asset_ip LIKE '192.168.0.%' AND network_segment != 'hq-lan'", {}),
    ("内网次段 192.168.199.0/24", "hq-lan-199",
     "asset_ip LIKE '192.168.199.%' AND network_segment != 'hq-lan-199'", {}),
    ("阿里云 VPC 172.18.x", "aliyun-172.18",
     "asset_ip LIKE '172.18.%' AND network_segment != 'aliyun-172.18'", {}),
    ("火山引擎 VPC 172.16.0.10", "volc-172.16",
     "asset_ip = '172.16.0.10' AND network_segment != 'volc-172.16'", {}),
    ("自建 VPS 172.16.0.51", "vps-202.189.23.82",
     "asset_ip = '172.16.0.51' AND network_segment != 'vps-202.189.23.82'", {}),
    ("自建 VPS 154.219.98.59", "vps-154.219.98.59",
     "asset_ip = '154.219.98.59' AND network_segment != 'vps-154.219.98.59'", {}),
]


def main():
    print("=== network_segment 回填 ===")
    if DRY_RUN:
        print("⚠️  DRY-RUN：只打印计划不执行\n")

    db = SessionLocal()
    try:
        print("[回填前] segment 分布:")
        for r in db.execute(text(
            "SELECT network_segment, count(*) FROM soc_assets GROUP BY 1 ORDER BY 2 DESC"
        )):
            print(f"  {r[0]:<20} {r[1]}")
        print()

        total = 0
        for name, seg, where, params in RULES:
            # 预估
            est = db.execute(text(
                f"SELECT count(*) FROM soc_assets WHERE {where}"
            ), params).scalar()
            # 明细（便于人工核对）
            detail = db.execute(text(
                f"SELECT asset_ip, name FROM soc_assets WHERE {where} ORDER BY asset_ip"
            ), params).fetchall()

            print(f"[{name}] → '{seg}'  预估 {est} 台")
            for ip, nm in detail:
                print(f"    {ip:<18} {str(nm)[:40]}")
            total += est

            if not DRY_RUN and est > 0:
                db.execute(text(
                    f"UPDATE soc_assets SET network_segment = :seg WHERE {where}"
                ), {"seg": seg, **params})

        if not DRY_RUN:
            db.commit()
            print(f"\n✅ 已 commit，共更新 {total} 台")
        else:
            print(f"\n⚠️  DRY-RUN 未执行；共影响 {total} 台")

        if not DRY_RUN:
            print("\n[回填后] segment 分布:")
            for r in db.execute(text(
                "SELECT network_segment, count(*) FROM soc_assets GROUP BY 1 ORDER BY 2 DESC"
            )):
                print(f"  {r[0]:<20} {r[1]}")
            # 剩余 default 的应为 127.0.0.1 / 0.0.0.0（数据质量问题）
            leftovers = db.execute(text(
                "SELECT asset_ip, name FROM soc_assets WHERE network_segment = 'default'"
            )).fetchall()
            if leftovers:
                print("\n[保留 default 的例外资产（数据质量问题，待稽核清理）]:")
                for ip, nm in leftovers:
                    print(f"  {ip:<18} {str(nm)[:40]}")

            # 收尾自校验：用唯一规则来源 infer_segment 全表扫，
            # 凡是 segment 与推断值不一致且不是保留 default 的，说明 RULES 有漏网。
            mismatches = db.execute(text(
                "SELECT asset_ip, name, network_segment FROM soc_assets"
            )).fetchall()
            bad = [
                (ip, nm, seg) for ip, nm, seg in mismatches
                if seg != "default" and seg != infer_segment(ip)
            ]
            if bad:
                print("\n[⚠️ 与 infer_segment 不一致的资产（RULES 漏网或事实表未登记）]:")
                for ip, nm, seg in bad:
                    print(f"  {ip:<18} seg={seg:<20} 推断={infer_segment(ip):<20} {str(nm)[:30]}")
            else:
                print("\n[自校验] 全部资产 segment 与 infer_segment 一致 ✓")

    except Exception as e:
        print(f"\n❌ 出错: {e}")
        if not DRY_RUN:
            db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()