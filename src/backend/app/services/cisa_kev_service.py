"""
CISA KEV 服务 + 24h 调度器（T6，§12.2 决策2：本期实现 has_exploit）

数据流：
  https://www.cisa.gov/.../known_exploited_vulnerabilities.json
    →（24h 定时 / POST /vulnerabilities/sync/kev 手动）
  soc_cisa_kev 表（本地 upsert）
    → load_kev_set()（10 分钟 TTL 内存缓存）
    → OpenSearchSCAPSyncService 落库时富化 has_exploit + 存量 enrich_has_exploit()

兜底：外网不可达且表为空时，用仓库内离线快照 data/cisa_kev_snapshot.json 初始化
（T12 已验证本环境外网可达；快照仅为断网兜底）。
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Set

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.cisa_kev import CisaKev
from app.models.vulnerability import Vulnerability
from app.services.task_observability import track_task

logger = logging.getLogger(__name__)

# 离线快照（随仓库提供的最小兜底集；外网恢复后自动被全量目录覆盖）
_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "cisa_kev_snapshot.json",
)

# 内存缓存（进程级，TTL 10 分钟，避免每次落库都全表扫）
_cache: Dict[str, Set[str]] = {"set": set(), "loaded_at": None}
_CACHE_TTL = timedelta(minutes=10)


class CisaKevService:
    """CISA KEV 目录同步与查询"""

    @staticmethod
    def fetch_catalog() -> Dict:
        """拉取 KEV 目录 JSON（失败抛异常，由调用方决定是否走快照兜底）"""
        resp = httpx.get(settings.CISA_KEV_URL, timeout=30.0)
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def _load_snapshot(cls) -> Dict:
        """加载仓库离线快照（T12 兜底）"""
        if not os.path.exists(_SNAPSHOT_PATH):
            return {"vulnerabilities": []}
        with open(_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def sync_kev(cls, db: Session, allow_snapshot: bool = True) -> Dict[str, int]:
        """
        拉取并 upsert KEV 目录。

        Returns:
            {"total": 目录条数, "upserted": 实际写入数, "source": "online"|"snapshot"}
        """
        source = "online"
        try:
            catalog = cls.fetch_catalog()
        except Exception as e:
            logger.warning("CISA KEV 在线拉取失败: %s", e)
            existing = db.query(CisaKev).count()
            if not allow_snapshot or existing:
                # 已有数据（旧数据可继续用）或明确不允许快照 → 直接返回现状
                return {"total": existing, "upserted": 0, "source": "offline-kept"}
            catalog = cls._load_snapshot()
            source = "snapshot"
            logger.info("使用离线快照初始化 KEV：%s 条", len(catalog.get("vulnerabilities", [])))

        now = datetime.utcnow()
        # 批量优化（2026-08-15 二次）：PostgreSQL 原生 INSERT ... ON CONFLICT DO UPDATE，
        # 分块 executemany，将 1665 行 upsert 压到几次网络往返（原逐行 ORM update ≈ 60s+）
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        items = []
        for item in catalog.get("vulnerabilities", []):
            cve_id = (item.get("cveID") or "").strip().upper()
            if not cve_id:
                continue
            items.append({
                "cve_id": cve_id,
                "date_added": cls._parse_date(item.get("dateAdded")),
                "short_description": cls._compose_description(item),
                "required_action": item.get("requiredAction"),
                "due_date": cls._parse_date(item.get("dueDate")),
                "known_ransomware": str(
                    item.get("knownRansomwareCampaignUse", "Unknown")
                ).lower() == "known",
                "notes": item.get("notes"),
                "synced_at": now,
            })

        upserted = 0
        CHUNK = 300
        total_items = len(items)
        # Phase 2.4：分块上报进度（节流在 update_progress 内部）
        try:
            from app.services.task_observability import update_progress
            update_progress(processed=0, total=total_items, stats={"stage": "upsert", "source": source})
        except Exception:
            update_progress = None  # type: ignore
        for i in range(0, total_items, CHUNK):
            chunk = items[i:i + CHUNK]
            stmt = pg_insert(CisaKev).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["cve_id"],
                set_={
                    c.key: stmt.excluded[c.key]
                    for c in CisaKev.__table__.columns
                    if c.key != "cve_id"
                },
            )
            db.execute(stmt)
            upserted += len(chunk)
            if update_progress:
                update_progress(
                    processed=upserted,
                    total=total_items,
                    stats={"stage": "upsert", "source": source},
                )

        db.commit()
        _invalidate_cache()
        logger.info("CISA KEV 同步完成: source=%s total=%s upserted=%s",
                    source, catalog.get("count", "-"), upserted)
        return {"total": upserted, "upserted": upserted, "source": source}

    @staticmethod
    def _parse_date(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _compose_description(item: Dict) -> str:
        parts = []
        if item.get("vulnerabilityName"):
            parts.append(str(item["vulnerabilityName"]))
        if item.get("vendorProject") and item.get("product"):
            parts.append(f"（{item['vendorProject']} / {item['product']}）")
        return "".join(parts) or None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @classmethod
    def load_kev_set(cls, db: Session) -> Set[str]:
        """加载 CVE 集合（10 分钟 TTL 进程缓存）"""
        if (
            _cache["loaded_at"] is not None
            and datetime.utcnow() - _cache["loaded_at"] < _CACHE_TTL
        ):
            return _cache["set"]

        rows = db.query(CisaKev.cve_id).all()
        _cache["set"] = {r[0].upper() for r in rows}
        _cache["loaded_at"] = datetime.utcnow()
        return _cache["set"]

    @classmethod
    def is_known_exploit(cls, db: Session, cve_id: str) -> bool:
        """检查 CVE 是否在 KEV 目录（命中在野利用）"""
        if not cve_id:
            return False
        return cve_id.strip().upper() in cls.load_kev_set(db)

    @classmethod
    def enrich_has_exploit(cls, db: Session) -> int:
        """
        存量富化：将命中 KEV 的漏洞 has_exploit 置 True（只加不减，
        保留可能的人工标注；KEV 移除条目属罕见边界，不回撤）。
        """
        kev_set = cls.load_kev_set(db)
        if not kev_set:
            return 0
        from sqlalchemy import func as sa_func
        affected = db.query(Vulnerability).filter(
            Vulnerability.has_exploit.is_(False),
            sa_func.upper(Vulnerability.cve_id).in_(kev_set),
        ).all()
        for v in affected:
            v.has_exploit = True
        if affected:
            db.commit()
        logger.info("KEV 存量富化: %d 条漏洞标记 has_exploit=True", len(affected))
        return len(affected)


def _invalidate_cache():
    _cache["loaded_at"] = None


# ---------------------------------------------------------------------------
# 24h 调度器（复用 alert_digest_scheduler 范式，§12.2-4）
# ---------------------------------------------------------------------------

_task = None
_FIRST_RUN_DELAY = 120  # 启动后稍等，避开与其他后台任务的启动高峰


@track_task(
    task_key="cisa_kev_sync",
    task_name="CISA KEV 漏洞情报同步",
    task_type="scheduled",
    schedule_expr="@every 24h",
    expected_interval_s=86400,
    timeout_s=1800,
)
async def run_kev_sync_once() -> dict:
    """手动/调度触发一轮 KEV 同步 + 存量富化。失败 raise 让装饰器记录。"""
    from app.services.task_observability import update_progress_stage
    db = SessionLocal()
    try:
        update_progress_stage("sync_kev", processed=0, total=2)
        result = CisaKevService.sync_kev(db)
        update_progress_stage("enrich", processed=1, total=2, extra={"upserted": result.get("upserted", 0)})
        enriched = CisaKevService.enrich_has_exploit(db)
        result["enriched"] = enriched
        update_progress_stage("done", processed=2, total=2, extra={"enriched": enriched})
        return result
    finally:
        db.close()


async def _loop() -> None:
    logger.info("cisa kev scheduler loop started (interval=24h)")
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            await run_kev_sync_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("kev loop iteration failed")
        await asyncio.sleep(timedelta(hours=24).total_seconds())


def start_cisa_kev_scheduler() -> None:
    """启动后台 KEV 同步任务（幂等；CISA_KEV_SCHEDULER_ENABLED=False 可关）"""
    global _task
    if not settings.CISA_KEV_SCHEDULER_ENABLED:
        logger.info("cisa kev scheduler disabled by config")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("cisa kev scheduler task started")


async def stop_cisa_kev_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("cisa kev scheduler task stopped")
