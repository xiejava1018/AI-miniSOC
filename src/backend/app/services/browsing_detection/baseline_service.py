"""
基线服务

维护 soc_browsing_baseline 表，用于 R3「基线偏离」检测。
提供批量预加载（避免逐条查询）和滚动清理。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Set

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.browsing_baseline import BrowsingBaseline

logger = logging.getLogger(__name__)


class BaselineService:
    """IP×域名 基线读写"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── 批量预加载（用于规则引擎判断"新域名"） ─────────

    def get_known_domains(self, ip: str) -> Set[str]:
        """获取某 IP 历史上访问过的所有域名集合（内存判断用）"""
        rows = (
            self.db.query(BrowsingBaseline.domain)
            .filter(BrowsingBaseline.ip == ip)
            .all()
        )
        return {r[0] for r in rows}

    def get_known_domains_bulk(self, ips: Iterable[str]) -> dict[str, Set[str]]:
        """批量获取多个 IP 的已知域名集合"""
        result: dict[str, Set[str]] = {}
        ip_list = [ip for ip in ips if ip]
        if not ip_list:
            return result
        rows = (
            self.db.query(BrowsingBaseline.ip, BrowsingBaseline.domain)
            .filter(BrowsingBaseline.ip.in_(ip_list))
            .all()
        )
        for ip, domain in rows:
            result.setdefault(ip, set()).add(domain)
        return result

    # ── 批量 upsert（每轮检测后更新基线） ──────────────

    def upsert_many(self, records: Iterable) -> int:
        """
        批量 upsert 基线记录（ip, domain）。

        records: BrowsingRecord 可迭代对象（仅 url 类型有意义）
        返回 upsert 的条数。
        """
        now = datetime.now(timezone.utc)
        # 按 (ip, domain) 聚合真实访问次数：total_count 口径修复（2026-09-05）
        # 原实现同键去重后每键只 +1，累计的是"检测轮次数"而非真实访问次数
        items: dict[tuple[str, str], list] = {}  # key -> [count, last_ts]
        for r in records:
            if not r.is_internal or not r.domain:
                continue
            entry = items.setdefault((r.ip, r.domain), [0, r.ts])
            entry[0] += 1
            if r.ts > entry[1]:
                entry[1] = r.ts

        if not items:
            return 0

        for (ip, domain), (count, ts) in items.items():
            stmt = pg_insert(BrowsingBaseline).values(
                ip=ip,
                domain=domain,
                first_seen=ts,
                last_seen=ts,
                total_count=count,
            )
            # 冲突时更新 last_seen / 累加真实访问次数
            stmt = stmt.on_conflict_do_update(
                constraint="uq_browsing_baseline_ip_domain",
                set_={
                    "last_seen": stmt.excluded.last_seen,
                    "total_count": BrowsingBaseline.total_count + stmt.excluded.total_count,
                },
            )
            self.db.execute(stmt)

        self.db.commit()
        return len(items)

    # ── 清理过期基线 ──────────────────────────────────

    def cleanup_old(self, baseline_days: int = 7) -> int:
        """清理超过 baseline_days 未访问的基线记录"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=baseline_days)
        result = self.db.execute(
            text("DELETE FROM soc_browsing_baseline WHERE last_seen < :cutoff"),
            {"cutoff": cutoff},
        )
        self.db.commit()
        deleted = result.rowcount or 0
        if deleted:
            logger.info("清理过期基线 %d 条（>%d天）", deleted, baseline_days)
        return deleted
