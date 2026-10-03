"""三源适配器（P0 联邦查询）。

每个适配器暴露同步 `fetch(anchor, start, end) -> List[EventRecord]`，
由 TimelineService 用 `run_in_executor` 卸载到线程池（关闭 G1）。
适配器内部自开 `SessionLocal()` 独立会话（参照 graph.py:307 独立 Session 范式），
避免共享同一 Session 跨线程。

G2 关闭：所有 IP 匹配均基于 `anchor.ips`（资产已知 IP 集）反查，绝不从裸 IP 反推资产。
G3 关闭：行为画像查询补充 `asset_id IS NULL AND ip IN (...)` 回退（未纳管设备）。
G4 关闭：`soc_identity_events` 已纳入 PG 适配器；Loki stream 选择器见 `_build_loki_query` 占位。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.models.alert_group_analysis import AlertGroupAnalysis
from app.models.behavior_profile import BehaviorProfile
from app.models.identity import IdentityEvent
from app.services.alert_query import AlertQueryService
from app.services.browsing_detection.loki_client import LokiClient

from .schemas import AssetAnchor, EventRecord, EventType, SourceKey

logger = logging.getLogger(__name__)


def _parse_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PG 适配器：行为画像 / 身份事件 / 告警簇研判
# ---------------------------------------------------------------------------


class PGAdapter:
    def fetch(self, anchor: AssetAnchor, start: datetime, end: datetime) -> List[EventRecord]:
        session = SessionLocal()
        try:
            events: List[EventRecord] = []
            aid = anchor.asset_id
            ips = anchor.ips or []

            # 行为画像（G3：asset_id 可空 → ip 回退，覆盖未纳管设备）
            bp_stmt = select(BehaviorProfile).where(
                BehaviorProfile.profile_date.between(start.date(), end.date()),
                or_(
                    BehaviorProfile.asset_id == aid,
                    BehaviorProfile.ip.in_(ips),
                ),
            )
            for bp in session.execute(bp_stmt).scalars().all():
                ts = bp.generated_at or datetime(
                    bp.profile_date.year, bp.profile_date.month, bp.profile_date.day, tzinfo=timezone.utc
                )
                events.append(
                    EventRecord(
                        event_id=f"bp:{bp.id}",
                        ts=ts,
                        source=SourceKey.PG,
                        event_type=EventType.BEHAVIOR,
                        asset_anchor=bp.ip or aid,
                        asset_id=aid if bp.asset_id else None,
                        severity=None,
                        summary=f"行为画像快照（当日访问 {bp.total} 次，置信度 {bp.confidence}）",
                        payload={
                            "total": bp.total,
                            "status": bp.status,
                            "confidence": bp.confidence,
                            "tags": bp.tags,
                        },
                        raw_ref=f"soc_behavior_profiles:{bp.id}",
                    )
                )

            # 身份事件（G4：已是 PG 数据，含 src_ip/dst_ip/ts）
            # 注：IdentityEvent 模型无 asset_id 列（仅 IdentityBinding 有），
            # 故仅按资产已知 IP 集匹配（src_ip/dst_ip ∈ anchor.ips）；
            # 命中的事件归属当前 anchor（按 IP 反查，对应 G2 纪律）。
            ie_stmt = select(IdentityEvent).where(
                IdentityEvent.ts.between(start, end),
                or_(
                    IdentityEvent.dst_ip.in_(ips),
                    IdentityEvent.src_ip.in_(ips),
                ),
            )
            for ie in session.execute(ie_stmt).scalars().all():
                events.append(
                    EventRecord(
                        event_id=f"ie:{ie.id}",
                        ts=ie.ts,
                        source=SourceKey.PG,
                        event_type=EventType.IDENTITY,
                        asset_anchor=ie.dst_ip or ie.src_ip or aid,
                        asset_id=aid,
                        severity=None,
                        summary=f"身份事件 {ie.event_type} account={ie.account} success={ie.success}",
                        payload={
                            "event_type": ie.event_type,
                            "account": ie.account,
                            "success": ie.success,
                            "rule_id": ie.rule_id,
                        },
                        raw_ref=f"soc_identity_events:{ie.id}",
                    )
                )

            # 告警簇研判（linked_asset_id 关联）
            ag_stmt = select(AlertGroupAnalysis).where(
                AlertGroupAnalysis.linked_asset_id == aid,
                AlertGroupAnalysis.created_at.between(start, end),
            )
            for ag in session.execute(ag_stmt).scalars().all():
                events.append(
                    EventRecord(
                        event_id=f"ag:{ag.id}",
                        ts=ag.created_at,
                        source=SourceKey.PG,
                        event_type=EventType.ALERT,
                        asset_anchor=aid,
                        asset_id=aid,
                        severity=None,
                        summary=f"告警簇研判 {ag.priority} noise={ag.is_noise} conf={ag.confidence:.2f}",
                        payload={
                            "priority": ag.priority,
                            "is_noise": ag.is_noise,
                            "confidence": ag.confidence,
                            "source": ag.source,
                        },
                        raw_ref=f"soc_alert_group_analyses:{ag.id}",
                    )
                )

            return events
        finally:
            session.close()


# ---------------------------------------------------------------------------
# OpenSearch 适配器：原始告警（复用 AlertQueryService）
# ---------------------------------------------------------------------------


class OSAdapter:
    def fetch(self, anchor: AssetAnchor, start: datetime, end: datetime) -> List[EventRecord]:
        session = SessionLocal()
        events: List[EventRecord] = []
        try:
            aqs = AlertQueryService(session)
            for ip in anchor.ips or []:
                try:
                    resp = aqs.get_alerts_by_ip(ip, limit=200)
                except Exception as e:
                    logger.warning("OSAdapter get_alerts_by_ip failed ip=%s: %s", ip, e)
                    continue
                for item in (resp or {}).get("items", []):
                    ts = _parse_ts(item.get("@timestamp") or item.get("timestamp"))
                    if ts is None or not (start <= ts <= end):
                        continue
                    events.append(
                        EventRecord(
                            event_id=f"os:{item.get('_id') or item.get('id')}",
                            ts=ts,
                            source=SourceKey.OPENSEARCH,
                            event_type=EventType.ALERT,
                            asset_anchor=ip,
                            asset_id=anchor.asset_id,
                            severity=item.get("level"),
                            summary=item.get("description") or item.get("rule") or "Wazuh alert",
                            payload=item,
                            raw_ref=f"wazuh-alerts:{item.get('_id')}",
                        )
                    )
            return events
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Loki 适配器：访问日志（复用 LokiClient.query_range）
# ---------------------------------------------------------------------------


def _build_loki_query(ips: List[str]) -> str:
    """构造 LogQL（G4 占位：stream 选择器 `access_log` 待采集侧确认日志流名）。

    仅按资产已知 IP 集匹配 srcip（G2：用 IP 集反查，不反推资产）。
    """
    if not ips:
        return "{access_log}"
    ip_re = "|".join(ips)
    return f'{{access_log}} | json | srcip =~ "({ip_re})"'


class LokiAdapter:
    def fetch(self, anchor: AssetAnchor, start: datetime, end: datetime) -> List[EventRecord]:
        try:
            client = LokiClient()
        except Exception as e:
            logger.warning("LokiAdapter init failed: %s", e)
            return []
        try:
            query = _build_loki_query(anchor.ips or [])
            start_ns = int(start.timestamp() * 1_000_000_000)
            end_ns = int(end.timestamp() * 1_000_000_000)
            streams = client.query_range(query, start_ns, end_ns, limit=1000)
            events: List[EventRecord] = []
            for stream in streams or []:
                labels = stream.get("stream", {}) or {}
                for entry in stream.get("values", []):
                    # entry: [ns_timestamp, line]
                    ns, line = entry[0], entry[1]
                    try:
                        ts = datetime.fromtimestamp(int(ns) / 1_000_000_000, tz=timezone.utc)
                    except Exception:
                        continue
                    if not (start <= ts <= end):
                        continue
                    events.append(
                        EventRecord(
                            event_id=f"loki:{ns}:{labels.get('filename', '')}",
                            ts=ts,
                            source=SourceKey.LOKI,
                            event_type=EventType.LOG,
                            asset_anchor=labels.get("srcip") or labels.get("dstip") or anchor.asset_id,
                            asset_id=anchor.asset_id,
                            severity=None,
                            summary=str(line)[:200],
                            payload={"labels": labels, "line": line},
                            raw_ref=f"loki:{labels}",
                        )
                    )
            return events
        except Exception as e:
            logger.warning("LokiAdapter fetch failed: %s", e)
            return []
        finally:
            try:
                client.close()
            except Exception:
                pass
