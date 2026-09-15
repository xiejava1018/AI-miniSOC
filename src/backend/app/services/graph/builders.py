"""
资产知识图谱 - 边构建器（5 个 builder）

每个 builder 一个类，统一接口 ``rebuild_all()`` → dict {"created", "updated", "deleted"}。

边构建数据流：
  1) 从源表读取事实（端口/漏洞/登录/告警簇等）
  2) 通过 ``resolve_asset_or_ip_node`` 归并节点
  3) 通过 ``ensure_node`` / ``upsert_edge`` 写入边表
  4) 边属性自动写入 evidence / sources / last_seen_by_source

边构建规则卡（§6.3.2）：
  - has_port       asset → port          永久    confidence 1.0
  - has_vuln       asset → vulnerability 扫描刷新  confidence 1.0
  - port_has_vuln  port  → vulnerability 永久    confidence 0.9
  - belongs_to_system  asset → business_system  永久  1.0
  - owned_by       asset → person         永久    1.0
  - system_owned_by   business_system → person 永久  1.0
  - runs_on        asset → asset          永久    0.8
  - login_to       account → asset        30 天  0.9
  - login_from     ip → asset             30 天  0.8
  - session_on     account → asset        90 天  0.9
  - external_access  ip → asset           7 天   0.7
  - same_segment   asset ↔ asset          年度   0.5
  - shared_tag     asset ↔ asset          90 天  0.4
  - alerted_on     asset → alert_group    簇关闭 90 天  0.95
  - co_alerted     asset ↔ asset          簇关闭 90 天  0.3
  - depends_on     asset → asset/system   永久    1.0（人工）

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.3
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    AccountPerson,
    AlertGroupSnapshot,
    Asset,
    AssetBusiness,
    AssetPort,
    AssetTag,
    AssetVulnerability,
    BusinessSystem,
    IdentityBinding,
    IdentityEvent,
    Vulnerability,
)
from app.services.graph.utils import (
    ensure_node,
    ensure_nodes_batch,
    is_external_ip,
    make_expires_at,
    resolve_asset_or_ip_node,
    upsert_edge,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Builder 1: AssetPortVulnBuilder（D1 确定性边）
# ---------------------------------------------------------------------------


class AssetPortVulnBuilder:
    """构建 has_port / has_vuln / port_has_vuln 边（D1 类）。

    数据源：
      - soc_asset_ports       端口列表（含 vulnerabilities JSONB）
      - soc_asset_vulnerabilities  资产-漏洞关联（按 scanner 拆分）

    触发：资产/端口/漏洞变更时 + 每日全量。
    """

    def __init__(self, db: Session):
        self.db = db

    def rebuild_all(self) -> dict:
        """重建资产-端口-漏洞三类边。返回 {"created", "updated", "deleted"}。

        v1.1 优化（修 N+1）：一次 batch 加载 asset/vuln dict，避免 3521 条 AssetVulnerability
        每条 4 次 db.query 的 N+1 问题（曾导致 seed 跑 6+ 分钟不返回）。
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "scanned": 0}

        # 0. 一次性 batch 加载 Asset / Vulnerability 的 id→obj 映射（关键 N+1 修复）
        asset_by_id = {a.id: a for a in self.db.query(Asset).all()}
        vuln_by_id = {v.id: v for v in self.db.query(Vulnerability).all()}

        # 1. has_port：asset → port
        ports = (
            self.db.query(AssetPort)
            .filter(AssetPort.asset_id.isnot(None))
            .all()
        )
        now = _utcnow()
        for p in ports:
            asset_node = f"asset:{p.asset_id}"
            port_node = f"port:{p.asset_ip}:{p.port}/{p.protocol}"

            ensure_node(
                self.db, asset_node, "asset", self._asset_label_from_obj(asset_by_id.get(p.asset_id)),
                ref_table="soc_assets", ref_id=str(p.asset_id),
            )
            ensure_node(
                self.db, port_node, "port", f"{p.asset_ip}:{p.port}/{p.protocol}",
                ref_table="soc_asset_ports", ref_id=str(p.id),
                props={"port": p.port, "protocol": p.protocol, "state": p.state,
                       "service": p.service, "version": p.version},
                props_synced_at=now,
            )

            upsert_edge(
                self.db, asset_node, port_node, "has_port",
                weight=1.0, confidence=1.0,
                sources=p.sources or ["scanner"],
                last_seen_by_source={k: (p.last_seen_by_source or {}).get(k, now.isoformat())
                                     for k in (p.sources or ["scanner"])},
                evidence={
                    "table": "soc_asset_ports",
                    "id": str(p.id),
                    "ip": p.asset_ip,
                    "port": p.port,
                    "protocol": p.protocol,
                },
                last_seen=p.last_seen or now,
                first_seen=p.created_at or now,
            )
            stats["scanned"] += 1

        # 2. has_vuln：asset → vulnerability + port_has_vuln：port → vulnerability
        #    通过 soc_asset_vulnerabilities + asset_port.vulnerabilities JSONB 双路
        vuln_links = (
            self.db.query(AssetVulnerability)
            .all()
        )
        for av in vuln_links:
            asset = asset_by_id.get(av.asset_id)
            vuln = vuln_by_id.get(av.vulnerability_id)
            if not asset or not vuln:
                continue
            asset_node = f"asset:{asset.id}"
            vuln_node = f"vuln:{vuln.id}"

            ensure_node(
                self.db, asset_node, "asset", self._asset_label_from_obj(asset),
                ref_table="soc_assets", ref_id=str(asset.id),
            )
            ensure_node(
                self.db, vuln_node, "vulnerability", f"{vuln.cve_id} ({vuln.cvss_score})",
                ref_table="soc_vulnerabilities", ref_id=str(vuln.id),
                props={"cve_id": vuln.cve_id, "cvss": float(vuln.cvss_score or 0),
                       "severity": vuln.severity, "title": vuln.title},
                props_synced_at=now,
            )

            upsert_edge(
                self.db, asset_node, vuln_node, "has_vuln",
                weight=1.0, confidence=1.0,
                sources=[av.scanner],
                last_seen_by_source={av.scanner: (av.detected_at or now).isoformat()},
                evidence={
                    "table": "soc_asset_vulnerabilities",
                    "id": str(av.id),
                    "scanner": av.scanner,
                    "status": av.status,
                },
                last_seen=av.detected_at or now,
                first_seen=av.detected_at or now,
            )

            # 同时补 port_has_vuln 边（按 IP+port 找端口节点）
            # asset 已从 batch 加载，不用再 db.query
            if asset and asset.asset_ip:
                # 找匹配的端口（vuln 通过 soc_asset_ports.vulnerabilities JSONB 关联）
                port_rows = (
                    self.db.query(AssetPort)
                    .filter(AssetPort.asset_ip == asset.asset_ip)
                    .all()
                )
                for p in port_rows:
                    p_vulns = p.vulnerabilities or []
                    if vuln.cve_id in p_vulns:
                        port_node = f"port:{p.asset_ip}:{p.port}/{p.protocol}"
                        ensure_node(
                            self.db, port_node, "port", f"{p.asset_ip}:{p.port}/{p.protocol}",
                            ref_table="soc_asset_ports", ref_id=str(p.id),
                        )
                        upsert_edge(
                            self.db, port_node, vuln_node, "port_has_vuln",
                            weight=1.0, confidence=0.9,
                            sources=[av.scanner],
                            last_seen_by_source={av.scanner: (av.detected_at or now).isoformat()},
                            evidence={
                                "table": "soc_asset_ports",
                                "id": str(p.id),
                                "vuln_cve_id": vuln.cve_id,
                                "scanner": av.scanner,
                            },
                            last_seen=av.detected_at or now,
                            first_seen=av.detected_at or now,
                        )

        self.db.flush()
        # 应用层 upsert 自身已统计 created/updated 困难；粗略按扫描数返回
        stats["created"] = stats["scanned"]
        logger.info("AssetPortVulnBuilder rebuilt %d port/vuln edges", stats["scanned"])
        return stats

    def _asset_label(self, asset_id) -> str:
        """旧 API 兼容；新代码优先用 _asset_label_from_obj。"""
        a = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not a:
            return f"asset:{asset_id}"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"

    def _asset_label_from_obj(self, a) -> str:
        """优化版：接受已加载的 Asset 对象，避免 N+1。"""
        if not a:
            return "asset:unknown"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"


# ---------------------------------------------------------------------------
# Builder 2: IdentityGraphBuilder（D2 观测边）
# ---------------------------------------------------------------------------


class IdentityGraphBuilder:
    """构建 login_to / login_from / session_on / external_access / owned_by 边。

    数据源：
      - soc_identity_events        认证类事件流（30 天窗口）
      - soc_identity_bindings      账号 ↔ IP 稳定映射
      - soc_account_person         账号 → 自然人 user_id 映射（产生 owned_by 边）

    触发：每小时增量；窗口 7-30 天（按 rel_type 区分）。
    """

    def __init__(self, db: Session, window_days: int = 30):
        self.db = db
        self.window_days = window_days

    def rebuild_all(self) -> dict:
        """重建身份相关所有 D2 类边。

        返回 ``{"events_seen": N, "bindings_seen": N, "account_person_seen": N}``。

        v1.5 优化（修 N+1）：
        一次性 batch 加载所有 IP→Asset 映射、所有 account→asset 绑定，
        避免 6 万条 IdentityEvent 每条都做 2~3 次 db.query（曾导致 builder 跑 10+ 分钟
        并锁住 uvicorn 主 event loop）。
        """
        stats = {
            "events_seen": 0,
            "login_to_built": 0,
            "login_from_built": 0,
            "external_access_built": 0,
            "session_on_built": 0,
            "owned_by_built": 0,
        }
        since = _utcnow() - timedelta(days=self.window_days)

        # === 0. 批量预加载：避免 N+1 ===
        # 0.1 资产按 IP 建索引（resolve_asset_or_ip_node 一次查完所有 IP）
        asset_by_ip: dict[str, Asset] = {
            a.asset_ip: a
            for a in self.db.query(Asset).filter(Asset.asset_ip.isnot(None)).all()
        }
        # 0.2 资产按 id 建索引（_asset_label_from_obj 用）
        asset_by_id: dict[str, Asset] = {str(a.id): a for a in asset_by_ip.values()}
        # 0.3 account 字符串 -> 绑定的所有 asset_id（owned_by 用）
        bindings_by_account: dict[str, set[str]] = {}
        for b in self.db.query(IdentityBinding).filter(
            IdentityBinding.asset_id.isnot(None)
        ).all():
            bindings_by_account.setdefault(b.account, set()).add(str(b.asset_id))

        # ---- 1. login_to + login_from：从 soc_identity_events 聚合 ----
        logger.info("IdentityGraphBuilder step1: query events (window=%dd)", self.window_days)
        events = (
            self.db.query(IdentityEvent)
            .filter(IdentityEvent.ts >= since)
            .filter(IdentityEvent.account.isnot(None))
            .filter(IdentityEvent.dst_ip.isnot(None))
            .all()
        )
        logger.info("IdentityGraphBuilder step1: got %d events", len(events))
        # 按 (account, dst_ip) / (src_ip, dst_ip) 聚合
        login_to_agg: dict[tuple[str, str], dict] = {}
        login_from_agg: dict[tuple[str, str], dict] = {}
        external_agg: dict[tuple[str, str], dict] = {}
        # 节点去重集（避免重复 ensure_node 调用，节省 N 倍 RTT）
        # 关键：同一 node_key 只能存一份（即使 type 也只能一个）
        # bug 修复 v1.6：之前用 (node_key, type) 作 dict key，导致
        # `asset:xxx` 同时被识别为 asset 和 ip 时重复入库。
        seen_nodes: dict[str, dict] = {}  # node_key -> node dict

        for e in events:
            stats["events_seen"] += 1
            # 使用预加载的 ip→asset 索引（O(1)），避免 N+1
            asset_for_dst = asset_by_ip.get(e.dst_ip)
            dst_node = (
                f"asset:{asset_for_dst.id}" if asset_for_dst else f"ip:{e.dst_ip}"
            )
            ts = e.ts or _utcnow()

            # account 节点（去重，不立即 INSERT）
            account_node = f"account:{e.account.lower()}"
            if account_node not in seen_nodes:
                seen_nodes[account_node] = {
                    "node_key": account_node, "node_type": "account",
                    "label": e.account,
                    "ref_table": "soc_identity_events", "ref_id": str(e.id),
                    "props": {"account": e.account, "last_event_ts": ts.isoformat()},
                    "props_synced_at": ts,
                }
            # dst 节点（去重：同一 node_key 只存一份）
            if dst_node not in seen_nodes:
                dst_kind = dst_node.split(":", 1)[0]
                seen_nodes[dst_node] = {
                    "node_key": dst_node, "node_type": dst_kind,
                    "label": self._label_for_node(dst_node),
                }

            # login_to（account → dst）
            key = (account_node, dst_node)
            agg = login_to_agg.setdefault(key, {
                "count": 0, "success": 0, "fail": 0, "sample_ids": [],
                "last_seen": ts, "first_seen": ts,
            })
            agg["count"] += 1
            if e.success:
                agg["success"] += 1
            else:
                agg["fail"] += 1
            agg["sample_ids"].append(str(e.id))
            agg["last_seen"] = max(agg["last_seen"], ts)
            agg["first_seen"] = min(agg["first_seen"], ts)

            # login_from（src_ip → dst）—— src_ip 可能未纳管
            if e.src_ip:
                # 使用预加载的 ip→asset 索引
                asset_for_src = asset_by_ip.get(e.src_ip)
                src_node = (
                    f"asset:{asset_for_src.id}" if asset_for_src
                    else f"ip:{e.src_ip}"
                )
                if src_node not in seen_nodes:
                    src_kind = src_node.split(":", 1)[0]
                    seen_nodes[src_node] = {
                        "node_key": src_node, "node_type": src_kind,
                        "label": e.src_ip,
                        "props": {"ip": e.src_ip, "is_external": is_external_ip(e.src_ip)},
                    }

                if is_external_ip(e.src_ip):
                    key = (src_node, dst_node)
                    agg = external_agg.setdefault(key, {
                        "count": 0, "sample_ids": [], "last_seen": ts, "first_seen": ts,
                    })
                    agg["count"] += 1
                    agg["sample_ids"].append(str(e.id))
                    agg["last_seen"] = max(agg["last_seen"], ts)
                    agg["first_seen"] = min(agg["first_seen"], ts)
                else:
                    key = (src_node, dst_node)
                    agg = login_from_agg.setdefault(key, {
                        "count": 0, "sample_ids": [], "last_seen": ts, "first_seen": ts,
                    })
                    agg["count"] += 1
                    agg["sample_ids"].append(str(e.id))
                    agg["last_seen"] = max(agg["last_seen"], ts)
                    agg["first_seen"] = min(agg["first_seen"], ts)

        # 批量写入节点（关键优化：6 万 events 聚合后节点去重为几千个）
        logger.info("IdentityGraphBuilder step1.5: ensure_nodes_batch %d nodes", len(seen_nodes))
        if seen_nodes:
            ensure_nodes_batch(self.db, seen_nodes.values())
        self.db.flush()
        logger.info("IdentityGraphBuilder step1.5: nodes flushed")
        # 写入 login_to 边
        logger.info("IdentityGraphBuilder step1.6: write %d login_to edges", len(login_to_agg))
        from datetime import datetime, timezone as _tz
        _t_now = datetime.now(_tz.utc)
        for i, ((src, dst), agg) in enumerate(login_to_agg.items()):
            if i % 20 == 0 and i > 0:
                logger.info("IdentityGraphBuilder login_to: %d/%d", i, len(login_to_agg))
                self.db.flush()
            upsert_edge(
                self.db, src, dst, "login_to",
                weight=1.0, confidence=0.9,
                sources=["wazuh"],
                last_seen_by_source={"wazuh": agg["last_seen"].isoformat()},
                evidence={
                    "table": "soc_identity_events",
                    "count": agg["count"],
                    "success": agg["success"],
                    "fail": agg["fail"],
                    "sample_ids": agg["sample_ids"][:10],
                },
                first_seen=agg["first_seen"],
                last_seen=agg["last_seen"],
                expires_at=make_expires_at("login_to", agg["last_seen"]),
                _now=_t_now,
            )
            stats["login_to_built"] += 1
        self.db.flush()
        # 写入 login_from 边
        logger.info("IdentityGraphBuilder step1.7: write %d login_from edges", len(login_from_agg))
        for i, ((src, dst), agg) in enumerate(login_from_agg.items()):
            if i % 20 == 0 and i > 0:
                logger.info("IdentityGraphBuilder login_from: %d/%d", i, len(login_from_agg))
                self.db.flush()
            upsert_edge(
                self.db, src, dst, "login_from",
                weight=1.0, confidence=0.8,
                sources=["wazuh"],
                last_seen_by_source={"wazuh": agg["last_seen"].isoformat()},
                evidence={
                    "table": "soc_identity_events",
                    "count": agg["count"],
                    "sample_ids": agg["sample_ids"][:10],
                },
                first_seen=agg["first_seen"],
                last_seen=agg["last_seen"],
                expires_at=make_expires_at("login_from", agg["last_seen"]),
                _now=_t_now,
            )
            stats["login_from_built"] += 1
        self.db.flush()
        # 写入 external_access 边
        logger.info("IdentityGraphBuilder step1.8: write %d external_access edges", len(external_agg))
        for i, ((src, dst), agg) in enumerate(external_agg.items()):
            if i % 20 == 0 and i > 0:
                logger.info("IdentityGraphBuilder external: %d/%d", i, len(external_agg))
                self.db.flush()
            upsert_edge(
                self.db, src, dst, "external_access",
                weight=1.0, confidence=0.7,
                sources=["wazuh"],
                last_seen_by_source={"wazuh": agg["last_seen"].isoformat()},
                evidence={
                    "table": "soc_identity_events",
                    "count": agg["count"],
                    "sample_ids": agg["sample_ids"][:10],
                },
                first_seen=agg["first_seen"],
                last_seen=agg["last_seen"],
                expires_at=make_expires_at("external_access", agg["last_seen"]),
                _now=_t_now,
            )
            stats["external_access_built"] += 1
        self.db.flush()
        logger.info("IdentityGraphBuilder step1 done: %d login_to, %d login_from, %d external",
                    stats["login_to_built"], stats["login_from_built"], stats["external_access_built"])

        # ---- 2. session_on：从 soc_identity_bindings（90 天窗口） ----
        logger.info("IdentityGraphBuilder step2: query bindings")
        bindings = (
            self.db.query(IdentityBinding)
            .filter(IdentityBinding.asset_id.isnot(None))
            .all()
        )
        # v1.6: 批量节点去重 + 批量边写入
        seen_nodes2: dict[str, dict] = {}
        session_edges: list[dict] = []
        for b in bindings:
            account_node = f"account:{b.account.lower()}"
            if account_node not in seen_nodes2:
                seen_nodes2[account_node] = {
                    "node_key": account_node, "node_type": "account",
                    "label": b.account,
                    "ref_table": "soc_identity_bindings", "ref_id": str(b.id),
                }
            asset_node = f"asset:{b.asset_id}"
            if asset_node not in seen_nodes2:
                seen_nodes2[asset_node] = {
                    "node_key": asset_node, "node_type": "asset",
                    "label": self._asset_label_from_obj(asset_by_id.get(b.asset_id)),
                    "ref_table": "soc_assets", "ref_id": str(b.asset_id),
                }
            session_edges.append({
                "src_key": account_node, "dst_key": asset_node, "rel_type": "session_on",
                "weight": 1.0, "confidence": 0.9, "sources": ["wazuh"],
                "last_seen_by_source": {"wazuh": (b.last_seen or _utcnow()).isoformat()},
                "evidence": {
                    "table": "soc_identity_bindings",
                    "id": str(b.id), "logins": b.logins, "ip": b.ip,
                },
                "first_seen": b.first_seen or _utcnow(),
                "last_seen": b.last_seen or _utcnow(),
                "expires_at": make_expires_at("session_on", b.last_seen or _utcnow()),
                "_now": _t_now,
            })
            stats["session_on_built"] += 1
        if seen_nodes2:
            ensure_nodes_batch(self.db, seen_nodes2.values())
        for i, e in enumerate(session_edges):
            if i % 50 == 0 and i > 0:
                self.db.flush()
            upsert_edge(self.db, **e)
        self.db.flush()
        logger.info("IdentityGraphBuilder step2 done: %d session_on", stats["session_on_built"])

        # ---- 3. owned_by：通过 soc_account_person → owned_by 边（asset）----
        ap_rows = (
            self.db.query(AccountPerson)
            .filter(AccountPerson.user_id.isnot(None))
            .all()
        )
        for ap in ap_rows:
            person_node = f"person:{ap.user_id}"
            ensure_node(
                self.db, person_node, "person", f"user#{ap.user_id}",
                ref_table="soc_users", ref_id=str(ap.user_id),
            )
            # 使用预加载的 bindings_by_account 索引（避免每账号再查 IdentityBinding）
            asset_ids = bindings_by_account.get(ap.account, set())
            for aid in asset_ids:
                asset_node = f"asset:{aid}"
                ensure_node(
                    self.db, asset_node, "asset", self._asset_label_from_obj(asset_by_id.get(aid)),
                    ref_table="soc_assets", ref_id=str(aid),
                )
                upsert_edge(
                    self.db, asset_node, person_node, "owned_by",
                    weight=1.0, confidence=1.0,
                    sources=[f"account_person:{ap.match_method}"],
                    last_seen_by_source={"account_person": (ap.verified_at or _utcnow()).isoformat()},
                    evidence={
                        "table": "soc_account_person",
                        "account": ap.account,
                        "match_method": ap.match_method,
                        "confidence": float(ap.confidence or 0),
                    },
                    last_seen=ap.verified_at or _utcnow(),
                )
                stats["owned_by_built"] += 1

        # ---- 4. owned_by：通过 soc_assets.owner_id（直接责任人）----
        assets_with_owner = (
            self.db.query(Asset).filter(Asset.owner_id.isnot(None)).all()
        )
        for a in assets_with_owner:
            asset_node = f"asset:{a.id}"
            person_node = f"person:{a.owner_id}"
            # 用 _asset_label_from_obj 拿已加载的 Asset 对象
            ensure_node(
                self.db, asset_node, "asset", self._asset_label_from_obj(a),
                ref_table="soc_assets", ref_id=str(a.id),
            )
            ensure_node(
                self.db, person_node, "person", f"user#{a.owner_id}",
                ref_table="soc_users", ref_id=str(a.owner_id),
            )
            upsert_edge(
                self.db, asset_node, person_node, "owned_by",
                weight=1.0, confidence=1.0,
                sources=["soc_assets.owner_id"],
                evidence={"table": "soc_assets", "asset_id": str(a.id), "owner_id": a.owner_id},
            )

        # ---- 5. system_owned_by：通过 soc_business_systems.owner_id ----
        systems = (
            self.db.query(BusinessSystem).filter(BusinessSystem.owner_id.isnot(None)).all()
        )
        for s in systems:
            sys_node = f"system:{s.code}"
            person_node = f"person:{s.owner_id}"
            ensure_node(
                self.db, sys_node, "business_system", s.name,
                ref_table="soc_business_systems", ref_id=str(s.id),
            )
            ensure_node(
                self.db, person_node, "person", f"user#{s.owner_id}",
                ref_table="soc_users", ref_id=str(s.owner_id),
            )
            upsert_edge(
                self.db, sys_node, person_node, "system_owned_by",
                weight=1.0, confidence=1.0,
                sources=["soc_business_systems.owner_id"],
                evidence={"table": "soc_business_systems", "system_code": s.code,
                          "owner_id": s.owner_id},
            )

        self.db.flush()
        logger.info("IdentityGraphBuilder rebuilt: %s", stats)
        return stats

    def _asset_label(self, asset_id) -> str:
        a = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not a:
            return f"asset:{asset_id}"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"

    def _label_for_node(self, node_key: str) -> str:
        kind, ident = node_key.split(":", 1)
        if kind == "asset":
            return self._asset_label(ident)
        if kind == "ip":
            return ident
        return f"{kind}:{ident}"

    def _is_managed_ip(self, ip: str) -> bool:
        return self.db.query(Asset).filter(Asset.asset_ip == ip).first() is not None

    def _asset_id_for_ip(self, ip: str) -> str:
        a = self.db.query(Asset).filter(Asset.asset_ip == ip).first()
        return str(a.id) if a else ip

    def _asset_label_from_obj(self, a) -> str:
        """从已加载的 Asset 对象生成 label，避免 N+1。"""
        if not a:
            return "asset:unknown"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"


# ---------------------------------------------------------------------------
# Builder 3: TopologyBuilder（D3 推断边）
# ---------------------------------------------------------------------------


class TopologyBuilder:
    """构建 same_segment / shared_tag 边（D3 推断类）。

    数据源：
      - soc_assets.network_segment   同网段
      - soc_asset_tags               共享标签

    触发：每日全量（这些边"诚实降级"，UI 强制标灰 + 标注推断关系）。
    """

    def __init__(self, db: Session):
        self.db = db

    def rebuild_all(self) -> dict:
        """重建拓扑推断边。

        D3 边不进入攻击路径计算（§4.3），仅用于"影响面提示"。
        """
        stats = {"same_segment_built": 0, "shared_tag_built": 0}
        now = _utcnow()

        # ---- same_segment：同一 network_segment 的所有资产两两相连 ----
        assets = self.db.query(Asset).all()
        # 按 network_segment 分组
        seg_groups: dict[str, list] = {}
        for a in assets:
            seg = a.network_segment or "default"
            seg_groups.setdefault(seg, []).append(a)

        for seg, group in seg_groups.items():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i+1:]:
                    ensure_node(
                        self.db, f"asset:{a.id}", "asset", self._label(a),
                        ref_table="soc_assets", ref_id=str(a.id),
                    )
                    ensure_node(
                        self.db, f"asset:{b.id}", "asset", self._label(b),
                        ref_table="soc_assets", ref_id=str(b.id),
                    )
                    upsert_edge(
                        self.db, f"asset:{a.id}", f"asset:{b.id}", "same_segment",
                        weight=1.0, confidence=0.5,
                        direction="undirected",
                        sources=["inferred:network_segment"],
                        evidence={"table": "soc_assets", "segment": seg,
                                  "asset_a": str(a.id), "asset_b": str(b.id)},
                        last_seen=now,
                        first_seen=now,
                        expires_at=make_expires_at("same_segment", now),
                    )
                    stats["same_segment_built"] += 1

        # ---- shared_tag：任意 (tag_key, tag_value) 相同的资产两两相连 ----
        tags = self.db.query(AssetTag).all()
        # 按 (tag_key, tag_value) 分组
        tag_groups: dict[tuple, list] = {}
        for t in tags:
            tag_groups.setdefault((t.tag_key, t.tag_value), []).append(t.asset_id)

        for (k, v), asset_ids in tag_groups.items():
            if len(asset_ids) < 2:
                continue
            unique_ids = list(set(asset_ids))
            for i, aid in enumerate(unique_ids):
                for bid in unique_ids[i+1:]:
                    ensure_node(
                        self.db, f"asset:{aid}", "asset",
                        self._label_by_id(aid),
                        ref_table="soc_assets", ref_id=str(aid),
                    )
                    ensure_node(
                        self.db, f"asset:{bid}", "asset",
                        self._label_by_id(bid),
                        ref_table="soc_assets", ref_id=str(bid),
                    )
                    upsert_edge(
                        self.db, f"asset:{aid}", f"asset:{bid}", "shared_tag",
                        weight=1.0, confidence=0.4,
                        direction="undirected",
                        sources=["inferred:tag"],
                        evidence={"table": "soc_asset_tags", "tag_key": k, "tag_value": v,
                                  "asset_a": str(aid), "asset_b": str(bid)},
                        last_seen=now,
                        first_seen=now,
                        expires_at=make_expires_at("shared_tag", now),
                    )
                    stats["shared_tag_built"] += 1

        self.db.flush()
        logger.info("TopologyBuilder rebuilt: %s", stats)
        return stats

    def _label(self, a: Asset) -> str:
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"

    def _label_by_id(self, aid) -> str:
        a = self.db.query(Asset).filter(Asset.id == aid).first()
        return self._label(a) if a else f"asset:{aid}"


# ---------------------------------------------------------------------------
# Builder 4: AlertGroupBuilder（告警簇 → 资产）
# ---------------------------------------------------------------------------


class AlertGroupBuilder:
    """构建 alerted_on / co_alerted 边（告警聚合，绝不全量入图）。

    数据源：
      - soc_alert_groups.linked_asset_id（已通过 §7.0.1 规则卡回填）

    触发：告警簇生成时增量；每日清理过期边。
    """

    def __init__(self, db: Session):
        self.db = db

    def rebuild_all(self, since_days: int = 90) -> dict:
        """重建告警簇边（取最近 N 天）。

        Returns:
            {"alerted_on_built": N, "co_alerted_built": N}
        """
        stats = {"alerted_on_built": 0, "co_alerted_built": 0}
        since = _utcnow() - timedelta(days=since_days)

        groups = (
            self.db.query(AlertGroupSnapshot)
            .filter(AlertGroupSnapshot.snapshot_at >= since)
            .filter(AlertGroupSnapshot.linked_asset_id.isnot(None))
            .all()
        )

        # 按 group_id 收集资产 → 产生 co_alerted 边
        from collections import defaultdict
        group_to_assets: dict[str, set] = defaultdict(set)

        for g in groups:
            asset_node = f"asset:{g.linked_asset_id}"
            alert_node = f"alertgroup:{g.id}"

            ensure_node(
                self.db, asset_node, "asset",
                self._asset_label(g.linked_asset_id),
                ref_table="soc_assets", ref_id=str(g.linked_asset_id),
            )
            ensure_node(
                self.db, alert_node, "alert_group",
                f"{g.rule_description or g.rule_id or 'alert'} ({g.count or 0}次)",
                ref_table="soc_alert_groups", ref_id=str(g.id),
                props={"count": g.count, "level_max": g.level_max,
                       "rule_id": g.rule_id, "fingerprint": g.fingerprint},
                props_synced_at=g.snapshot_at or _utcnow(),
            )
            upsert_edge(
                self.db, asset_node, alert_node, "alerted_on",
                weight=1.0, confidence=0.95,
                sources=["soc_alert_groups"],
                last_seen_by_source={"soc_alert_groups": (g.snapshot_at or _utcnow()).isoformat()},
                evidence={
                    "table": "soc_alert_groups",
                    "id": str(g.id),
                    "count": g.count,
                    "level_max": g.level_max,
                },
                last_seen=g.snapshot_at or _utcnow(),
                first_seen=g.snapshot_at or _utcnow(),
                expires_at=make_expires_at("alerted_on", g.snapshot_at or _utcnow()),
            )
            stats["alerted_on_built"] += 1
            group_to_assets[g.id].add(str(g.linked_asset_id))

        # co_alerted：同一 alert_group 簇内的资产两两相连
        for group_id, asset_ids in group_to_assets.items():
            ids = list(asset_ids)
            for i, a in enumerate(ids):
                for b in ids[i+1:]:
                    ensure_node(
                        self.db, f"asset:{a}", "asset", self._asset_label(a),
                        ref_table="soc_assets", ref_id=str(a),
                    )
                    ensure_node(
                        self.db, f"asset:{b}", "asset", self._asset_label(b),
                        ref_table="soc_assets", ref_id=str(b),
                    )
                    upsert_edge(
                        self.db, f"asset:{a}", f"asset:{b}", "co_alerted",
                        weight=1.0, confidence=0.3,
                        direction="undirected",
                        sources=["soc_alert_groups"],
                        evidence={
                            "table": "soc_alert_groups",
                            "group_id": str(group_id),
                            "asset_a": a, "asset_b": b,
                        },
                        last_seen=_utcnow(),
                        first_seen=_utcnow(),
                        expires_at=make_expires_at("co_alerted", _utcnow()),
                    )
                    stats["co_alerted_built"] += 1

        self.db.flush()
        logger.info("AlertGroupBuilder rebuilt: %s", stats)
        return stats

    def _asset_label(self, asset_id) -> str:
        a = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not a:
            return f"asset:{asset_id}"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"


# ---------------------------------------------------------------------------
# Builder 5: ManualRelationBuilder（人工登记 D4 边）
# ---------------------------------------------------------------------------


class ManualRelationBuilder:
    """构建 belongs_to_system / depends_on 边（人工登记，置信度最高）。

    数据源：
      - soc_asset_business       资产 ↔ 业务系统（belongs_to_system）
      - 人工录入的 depends_on    资产 → 资产 / 系统（UI 录入）

    触发：UI 人工登记时立即触发 + 每日重建校验。
    """

    def __init__(self, db: Session):
        self.db = db

    def rebuild_all(self) -> dict:
        """重建人工登记的边。

        belongs_to_system：从 soc_asset_business 反向重建
        depends_on：本版本从人工录入 API 维护（builder 不直接生成）
        runs_on：从 soc_assets.parent_id 自动推断（Docker/K8s 场景）
        """
        stats = {"belongs_to_system_built": 0, "runs_on_built": 0}
        now = _utcnow()

        # ---- belongs_to_system：从 soc_asset_business ----
        ab_rows = (
            self.db.query(AssetBusiness).all()
        )
        for ab in ab_rows:
            asset_node = f"asset:{ab.asset_id}"
            sys = self.db.query(BusinessSystem).filter(
                BusinessSystem.id == ab.system_id).first()
            if not sys:
                continue
            sys_node = f"system:{sys.code}"

            ensure_node(
                self.db, asset_node, "asset", self._asset_label(ab.asset_id),
                ref_table="soc_assets", ref_id=str(ab.asset_id),
            )
            ensure_node(
                self.db, sys_node, "business_system", sys.name,
                ref_table="soc_business_systems", ref_id=str(sys.id),
                props={"code": sys.code, "name": sys.name,
                       "criticality": sys.criticality},
                props_synced_at=now,
            )
            upsert_edge(
                self.db, asset_node, sys_node, "belongs_to_system",
                weight=1.0, confidence=1.0,
                sources=["manual", "soc_asset_business"],
                evidence={
                    "table": "soc_asset_business",
                    "asset_id": str(ab.asset_id),
                    "system_id": str(ab.system_id),
                    "role": ab.role,
                },
                last_seen=ab.created_at or now,
                first_seen=ab.created_at or now,
            )
            stats["belongs_to_system_built"] += 1

        # ---- runs_on：从 soc_assets.parent_id（容器/虚拟机 → 宿主机）----
        child_assets = (
            self.db.query(Asset).filter(Asset.parent_id.isnot(None)).all()
        )
        for child in child_assets:
            parent_id = child.parent_id
            if isinstance(parent_id, str):
                # parent_id 已是 UUID 类型（迁移后）；直接用
                parent_uuid = parent_id
            else:
                parent_uuid = parent_id
            parent = self.db.query(Asset).filter(Asset.id == parent_uuid).first()
            if not parent:
                continue

            asset_node = f"asset:{child.id}"
            parent_node = f"asset:{parent.id}"
            ensure_node(
                self.db, asset_node, "asset", self._asset_label(child.id),
                ref_table="soc_assets", ref_id=str(child.id),
            )
            ensure_node(
                self.db, parent_node, "asset", self._asset_label(parent.id),
                ref_table="soc_assets", ref_id=str(parent.id),
            )
            upsert_edge(
                self.db, asset_node, parent_node, "runs_on",
                weight=1.0, confidence=0.8,
                sources=["soc_assets.parent_id"],
                evidence={
                    "table": "soc_assets",
                    "child_id": str(child.id),
                    "parent_id": str(parent.id),
                },
                last_seen=now,
                first_seen=now,
            )
            stats["runs_on_built"] += 1

        self.db.flush()
        logger.info("ManualRelationBuilder rebuilt: %s", stats)
        return stats

    def _asset_label(self, asset_id) -> str:
        a = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not a:
            return f"asset:{asset_id}"
        return f"{a.name or 'unknown'} ({a.asset_ip or '?'})"


# ---------------------------------------------------------------------------
# 顶层调度入口（给 scheduler 用）
# ---------------------------------------------------------------------------


def run_all_builders(db: Session, only: Optional[str] = None) -> dict:
    """依次跑全部 5 个 builder，返回合并统计。

    v1.5 修复：每个 builder 跑完后立即 commit（避免长事务锁住其他 session
    或 SIGTERM 后在 PG 端留下僵尸事务）。每个 builder 异常时也回滚自身事务
    以保护下个 builder 跑。

    v1.8（2026-09-13）：新增 ``only`` 参数，支持只跑单个 builder
    （asset_port_vuln / identity / topology / alert_group / manual）。
    """
    all_builders = [
        ("asset_port_vuln", AssetPortVulnBuilder),
        ("identity", IdentityGraphBuilder),
        ("topology", TopologyBuilder),
        ("alert_group", AlertGroupBuilder),
        ("manual", ManualRelationBuilder),
    ]
    if only and only != "all":
        all_builders = [(n, c) for n, c in all_builders if n == only]
    out: dict = {}
    for name, cls in all_builders:
        try:
            out[name] = cls(db).rebuild_all()
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("run_all_builders: %s failed", name)
            out[name] = {"error": "see logs"}
    return out