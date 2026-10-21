"""手动触发行为画像快照回补（运维工具）。

背景：snapshot_job 的 scheduler 每天 02:00 跑一次，只聚合「昨天一整天」。
当 Loki 数据刚恢复（或修完采集链路想立刻验证）时，需要手动补指定日期。

用法（在生产服务器 src/backend 目录下）：
    venv/bin/python -m scripts.run_behavior_snapshot 2026-10-21
    venv/bin/python -m scripts.run_behavior_snapshot            # 默认昨天

注意：
- 与 scheduler 跑在同一进程外，独立 Session，不影响 uvicorn 事件循环。
- run_snapshot 会推进 soc_behavior_profile_watermark 水位，重复执行同一日期
  是幂等的（start_day > end_day 时直接返回 up_to_date）。
- Loki 当天尚未结束也能跑（聚合到当前时刻），但当天数据会在次轮被重新覆盖。
"""
import datetime as dt
import sys
import logging

from app.core.database import SessionLocal
from app.services.behavior_profile.snapshot_job import run_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    target = dt.date.fromisoformat(arg) if arg else None
    if target:
        print(f"[manual] 触发快照回补: target_date={target}")
    else:
        print("[manual] 触发快照回补: target_date=昨天(默认)")

    db = SessionLocal()
    try:
        stats = run_snapshot(db, target_date=target)
        print("[manual] 完成:", stats)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())