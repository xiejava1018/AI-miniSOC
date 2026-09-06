"""身份管道：OpenSearch 认证类告警抽取 → soc_identity_events/bindings

方案 §4.1 Phase 0。抽取规则（CLAUDE.md §1.3）：
  5715 sshd 认证成功 / 5760 sshd 认证失败 / 5763 暴力破解
  5501 PAM 会话开始 / 5502 PAM 会话结束 / 5503 PAM 登录失败 / 5551 多次失败
用户名从 full_log 正则提取（"Accepted publickey for xiejava from 192.168.0.8"）。
每日增量（watermark），es doc id 幂等 upsert。
"""

import datetime as dt
import logging
import re
import threading
from typing import List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.identity import IdentityBinding, IdentityEvent

logger = logging.getLogger(__name__)

ALERTS_INDEX = "wazuh-alerts-4.x-*"
AUTH_RULES = ["5715", "5760", "5763", "5501", "5502", "5503", "5551"]
LOOKBACK_DAYS = 30  # 首次回填窗口

# full_log 正则：sshd "Accepted publickey for USER from IP" / "Failed password for USER from IP"
_RE_SSH = re.compile(
    r"(?:Accepted|Failed)\s+\S+\s+for\s+(?:invalid user\s+)?(\S+)\s+from\s+(\d{1,3}(?:\.\d{1,3}){3})",
    re.IGNORECASE,
)
_RE_PAM_OPEN = re.compile(r"session opened for user\s*\(?([a-zA-Z0-9_.-]+)\$?\)?")
_RE_PAM_FAIL = re.compile(r"authentication failure.*?user=(\S+)")


def _rule_event_type(rule_id: str, log: str) -> Tuple[str, bool]:
    if rule_id in ("5715",):
        return "auth_success", True
    if rule_id in ("5760", "5763", "5503", "5551"):
        return "auth_failed", False
    if rule_id == "5501":
        return "session_open", True
    if rule_id == "5502":
        return "session_close", False
    if "Failed" in log or "failure" in log:
        return "auth_failed", False
    return "auth_success", True


def _extract(log: str, rule_id: str) -> Tuple[Optional[str], Optional[str]]:
    """从 full_log 提取 (account, src_ip)。"""
    m = _RE_SSH.search(log or "")
    if m:
        return m.group(1)[:64], m.group(2)
    m = _RE_PAM_OPEN.search(log or "")
    if m:
        return m.group(1)[:64], None
    m = _RE_PAM_FAIL.search(log or "")
    if m:
        return m.group(1)[:64], None
    return None, None


def _os_search(body: dict) -> dict:
    with httpx.Client(
        base_url=settings.OPENSEARCH_URL.rstrip("/"),
        auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        verify=False,
        timeout=60,
    ) as c:
        r = c.post(f"/{ALERTS_INDEX}/_search",
                   headers={"Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        return r.json()


def _fetch_auth_hits(since: dt.datetime) -> List[dict]:
    """拉取 since 之后的认证类告警原始文档。"""
    body = {
        "size": 5000,
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"rule.id": AUTH_RULES}},
                    {"range": {"@timestamp": {"gte": since.isoformat()}}},
                ]
            }
        },
        "sort": [{"@timestamp": "asc"}],
    }
    out: List[dict] = []
    try:
        data = _os_search(body)
    except Exception:
        logger.exception("身份管道 OpenSearch 查询失败")
        return out
    out = data.get("hits", {}).get("hits", [])
    # 翻页（search_after）
    while len(out) % 5000 == 0 and out:
        last = out[-1].get("sort")
        if not last:
            break
        body["search_after"] = last
        try:
            page = _os_search(body).get("hits", {}).get("hits", [])
        except Exception:
            logger.exception("身份管道翻页失败")
            break
        if not page:
            break
        out.extend(page)
    return out


def run_extraction(db: Session, since: Optional[dt.datetime] = None) -> dict:
    """抽取 since 之后的认证事件并落库（幂等）。

    性能约束：psycopg2 单语句 32767 绑定参数上限（gkpj）——
    预加载已有文档 id 集合、关闭 autoflush、每 BATCH 条显式 commit。
    """
    from sqlalchemy import select

    if since is None:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=LOOKBACK_DAYS)
    hits = _fetch_auth_hits(since)
    stats = {"hits": len(hits), "events": 0, "bindings": 0, "skipped": 0}

    existing = {
        (idx, doc)
        for idx, doc in db.execute(
            select(IdentityEvent.es_index, IdentityEvent.es_doc_id)
        ).all()
    }
    db.autoflush = False
    pending_bindings: dict = {}  # (account, ip) -> IdentityEvent（autoflush 关闭时防重复 add）

    # 资产 ip → asset_id 映射
    asset_map = {
        a.asset_ip: str(a.id)
        for a in db.query(Asset).filter(Asset.asset_ip.isnot(None)).all()
        if a.asset_ip
    }

    BATCH = 250
    for i, hit in enumerate(hits):
        if i and i % BATCH == 0:
            db.commit()  # 分批提交：单语句参数超 32767 会炸（gkpj）
        src = hit.get("_source", {})
        if (hit.get("_index", ""), hit.get("_id", "")) in existing:
            continue
        rule_id = str((src.get("rule") or {}).get("id", ""))
        log = src.get("full_log") or ""
        agent_ip = ((src.get("agent") or {}).get("ip")) or None
        ts_raw = src.get("@timestamp")
        try:
            ts = dt.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            continue

        account, srcip = _extract(log, rule_id)
        if not account and not srcip:
            stats["skipped"] += 1
            continue
        event_type, success = _rule_event_type(rule_id, log)

        db.add(IdentityEvent(
            es_index=hit.get("_index", "")[:64],
            es_doc_id=hit.get("_id", "")[:64],
            rule_id=rule_id,
            account=account,
            src_ip=srcip,
            dst_ip=agent_ip,
            success=success,
            event_type=event_type,
            ts=ts,
        ))
        stats["events"] += 1

        # 绑定：成功登录 → account 在 dst_ip（agent.ip）上使用
        if success and account and agent_ip:
            binding = (
                db.query(IdentityBinding)
                .filter(IdentityBinding.account == account,
                        IdentityBinding.ip == agent_ip)
                .first()
            )
            key = (account, agent_ip)
            binding = pending_bindings.get(key)
            if binding is None:
                binding = (
                    db.query(IdentityBinding)
                    .filter(IdentityBinding.account == account,
                            IdentityBinding.ip == agent_ip)
                    .first()
                )
            if binding is None:
                binding = IdentityBinding(account=account, ip=agent_ip)
                db.add(binding)
                pending_bindings[key] = binding
                stats["bindings"] += 1
            binding.logins = (binding.logins or 0) + 1
            binding.asset_id = asset_map.get(agent_ip)
            binding.last_seen = ts

    db.commit()
    db.expunge_all()
    db.autoflush = True
    logger.info("身份管道抽取完成: %s", stats)
    return stats


# ── 关系画像查询（层4） ──────────────────────────────────

def get_relations(db: Session, ip: str, days: int = 30) -> dict:
    """关系画像：入站登录（谁登了本机，含账号归一化/设备共享度）/
    出站登录（本机主动登了谁）/ 外部攻击源。"""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    inbound = (
        db.query(IdentityEvent.account, IdentityEvent.src_ip,
                 IdentityEvent.success, func_count())
        .filter(IdentityEvent.dst_ip == ip, IdentityEvent.ts >= since,
                IdentityEvent.src_ip.isnot(None))
        .group_by(IdentityEvent.account, IdentityEvent.src_ip, IdentityEvent.success)
        .order_by(func_count().desc())
        .all()
    )
    outbound = (
        db.query(IdentityEvent.dst_ip, IdentityEvent.account, IdentityEvent.success,
                 func_count())
        .filter(IdentityEvent.src_ip == ip, IdentityEvent.ts >= since,
                IdentityEvent.dst_ip.isnot(None))
        .group_by(IdentityEvent.dst_ip, IdentityEvent.account, IdentityEvent.success)
        .order_by(func_count().desc())
        .all()
    )
    # 外部攻击源：非内网 src 的失败登录
    import ipaddress

    def _is_internal(x: str) -> bool:
        try:
            return ipaddress.ip_address(x).is_private
        except Exception:
            return False

    externals = [
        {"ip": s, "count": c}
        for s, c in (
            db.query(IdentityEvent.src_ip, func_count())
            .filter(IdentityEvent.dst_ip == ip, IdentityEvent.success == False,  # noqa: E712
                    IdentityEvent.ts >= since, IdentityEvent.src_ip.isnot(None))
            .group_by(IdentityEvent.src_ip).all()
        )
        if not _is_internal(s)
    ]

    in_ok = [{"account": a or "?", "ip": s, "count": int(c)}
             for a, s, ok, c in inbound if ok]
    out_ok = [{"account": a or "?", "ip": d, "count": int(c)}
              for d, a, ok, c in outbound if ok]
    in_fail_total = sum(int(c) for _a, _s, ok, c in inbound if not ok)

    accounts_on_host = sorted({r["account"] for r in in_ok if r["account"] != "?"})

    # 同网段邻居（拓扑图用，§6.4；排除自己，取前 12 防爆炸）
    me = db.query(Asset).filter(Asset.asset_ip == ip).first()
    same_segment = []
    if me:
        neighbors = (
            db.query(Asset.asset_ip, Asset.name)
            .filter(Asset.network_segment == me.network_segment,
                    Asset.asset_ip != ip,
                    Asset.asset_ip.notin_(("0.0.0.0", "127.0.0.1")))
            .order_by(Asset.asset_ip)
            .limit(12)
            .all()
        )
        same_segment = [
            {"ip": n.asset_ip, "name": n.name}
            for n in neighbors
        ]

    return {
        "ip": ip,
        "days": days,
        "inbound": in_ok,
        "outbound": out_ok,
        "inbound_fail_total": in_fail_total,
        "external_attackers": externals,
        "accounts_on_host": accounts_on_host,
        "device_shared_by": len(accounts_on_host),
        "same_segment": same_segment,
        "note": None if (in_ok or out_ok) else "该设备无认证事件记录（未装 agent 或无 SSH 活动）",
    }


def func_count():
    from sqlalchemy import func

    return func.count()


# ── 调度（并入 snapshot_job 的线程，每日抽一次） ──────────

def start_identity_scheduler() -> None:
    """每日 02:30 抽取；启动即补一次。实现为独立 daemon 线程。"""

    def _loop():
        import time

        logger.info("identity scheduler started")
        db = SessionLocal()
        try:
            run_extraction(db)
        except Exception:
            logger.exception("身份管道启动抽取失败")
        finally:
            db.close()
        while True:
            now = dt.datetime.now(dt.timezone.utc)
            nxt = (now + dt.timedelta(days=1)).replace(hour=18, minute=30, second=0,
                                                       microsecond=0)  # UTC 18:30 = 北京 02:30
            if now.hour < 18:
                nxt = now.replace(hour=18, minute=30, second=0, microsecond=0)
            if _stop.wait(max((nxt - now).total_seconds(), 60)):
                break
            db = SessionLocal()
            try:
                run_extraction(db)
            except Exception:
                logger.exception("身份管道定时抽取失败")
            finally:
                db.close()

    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="identity-scheduler", daemon=True)
    _thread.start()


def stop_identity_scheduler() -> None:
    _stop.set()


_stop = threading.Event()
_thread: Optional[threading.Thread] = None
