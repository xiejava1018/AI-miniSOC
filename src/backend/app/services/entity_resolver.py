"""EntityResolver —— 统一实体解析锚（底座 P1 §4.1，D-2 拍板后落地）

把三源标识符（asset_ip / wazuh_agent_id / 日志 srcip·dstip）统一解析为
``soc_assets.id``，贯穿 S1 融合 / S6 告警关联 / S8 影子资产的实体主键。

设计依据：docs/design/2026-10-07-D2-EntityResolver-spike.md（G5/G6/G7 拍板）

优先级链（确定性，逐级短路）：
  1. wazuh_agent_id 精确匹配（agent 直报）
  2. asset_ip 精确匹配（实测唯一、100% 覆盖）
  3. mac_address 精确匹配
  4. src/dst ip 反向索引（soc_identity_events）——**仅限私有网段**：
     实测 3987 种 srcip 仅 0.2% 命中，主体是外部攻击 IP，禁锚资产。

诚实红线：
  - v1 不做 hostname/模糊匹配（阈值无标注语料，不伪造精度）。
  - 同级多命中 → asset_id=None + conflicts，不猜。
  - register_alias 不建表（G7 拍板），返回 not_supported。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.graph.utils import is_external_ip

logger = logging.getLogger(__name__)

# 别名类型（显式指定可跳过低优先级误判，也用于结果标注）
ALIAS_AGENT = "wazuh_agent_id"
ALIAS_IP = "asset_ip"
ALIAS_MAC = "mac_address"
ALIAS_LOG_IP = "log_ip"          # 日志 srcip/dstip（走反向索引）


class EntityResolver:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 解析入口
    # ------------------------------------------------------------------

    def resolve(
        self, alias: str, *, alias_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """alias → asset_id。

        Returns:
            {"alias", "alias_type", "asset_id", "matched_by",
             "conflicts": [...], "note"}
        """
        alias = (alias or "").strip()
        out: Dict[str, Any] = {
            "alias": alias,
            "alias_type": alias_type,
            "asset_id": None,
            "matched_by": None,
            "conflicts": [],
        }
        if not alias:
            out["note"] = "空 alias"
            return out

        # 显式类型 → 只走该链（调用方语义明确时避免误判）
        if alias_type == ALIAS_AGENT:
            out.update(self._by_agent(alias))
            return out
        if alias_type == ALIAS_IP:
            out.update(self._by_ip(alias))
            return out
        if alias_type == ALIAS_LOG_IP:
            out.update(self._by_log_ip(alias))
            return out
        if alias_type == ALIAS_MAC:
            out.update(self._by_mac(alias))
            return out

        # 自动判定：agent id（纯数字/短串）→ ip → mac → 日志反查
        # 顺序即优先级（G5 拍板），逐级短路。
        for step in (self._by_agent, self._by_ip, self._by_mac,
                     self._by_log_ip):
            r = step(alias)
            out.update({k: v for k, v in r.items()
                        if k in ("asset_id", "matched_by", "conflicts",
                                 "note")})
            if out["asset_id"]:
                break
        if not out["asset_id"] and not out["conflicts"] and not out.get("note"):
            out["note"] = "四级链均未命中"
        return out

    def resolve_batch(
        self, aliases: List[str]
    ) -> Dict[str, Any]:
        """批量解析。返回 {results: [...], hit: N, total: N}。"""
        results = [self.resolve(a) for a in aliases]
        hits = sum(1 for r in results if r["asset_id"])
        return {"results": results, "hit": hits, "total": len(results)}

    # ------------------------------------------------------------------
    # 优先级链各级
    # ------------------------------------------------------------------

    def _by_agent(self, agent_id: str) -> Dict[str, Any]:
        # agent id 是 3 位数字串（实测 000-029）；非数字直接跳过避免全表扫
        if not agent_id.isdigit() or len(agent_id) > 8:
            return {"asset_id": None}
        rows = self.db.execute(text(
            "SELECT id FROM soc_assets WHERE wazuh_agent_id = :a"
        ), {"a": agent_id}).fetchall()
        return self._pick(rows, ALIAS_AGENT)

    def _by_ip(self, ip: str) -> Dict[str, Any]:
        rows = self.db.execute(text(
            "SELECT id FROM soc_assets WHERE asset_ip::text = :ip"
        ), {"ip": ip}).fetchall()
        return self._pick(rows, ALIAS_IP)

    def _by_mac(self, mac: str) -> Dict[str, Any]:
        rows = self.db.execute(text(
            "SELECT id FROM soc_assets WHERE mac_address::text = :m"
        ), {"m": mac.lower()}).fetchall()
        return self._pick(rows, ALIAS_MAC)

    def _by_log_ip(self, ip: str) -> Dict[str, Any]:
        # G5 拍板：仅私有网段参与反查——外部攻击 IP 禁锚资产
        # （实测 srcip 3987 种仅 0.2% 命中，主体为攻击源）
        if is_external_ip(ip):
            return {"asset_id": None,
                    "note": "外网 IP 不参与日志反查（防攻击源误锚资产）"}
        # 语义：该内网 IP 在 identity_events 中被观测到且对应在册资产
        rows = self.db.execute(text("""
            SELECT DISTINCT a.id FROM soc_assets a
            WHERE a.asset_ip::text = :ip
              AND EXISTS (
                SELECT 1 FROM soc_identity_events e
                WHERE e.src_ip = :ip OR e.dst_ip = :ip
              )
        """), {"ip": ip}).fetchall()
        return self._pick(rows, ALIAS_LOG_IP)

    @staticmethod
    def _pick(rows, matched_by: str) -> Dict[str, Any]:
        ids = [str(r[0]) for r in rows]
        if len(ids) == 1:
            return {"asset_id": ids[0], "matched_by": matched_by}
        if len(ids) > 1:
            # 同级冲突：不猜（G5 拍板）
            return {"asset_id": None, "matched_by": None,
                    "conflicts": ids,
                    "note": f"{matched_by} 同级多命中，拒绝猜测"}
        return {"asset_id": None}

    # ------------------------------------------------------------------
    # register_alias（G7 拍板：v1 不建表，诚实 not_supported）
    # ------------------------------------------------------------------

    def register_alias(self, asset_id: str, alias_type: str,
                       alias_value: str) -> Dict[str, Any]:
        return {
            "supported": False,
            "reason": ("v1 不建 soc_entity_alias（D-2/G7 拍板）；"
                       "用 soc_assets 现有字段维护标识符"),
        }

    # ------------------------------------------------------------------
    # 覆盖率（G6：分段快照，不拍单一数字）
    # ------------------------------------------------------------------

    def coverage(self) -> Dict[str, Any]:
        r = self.db.execute(text("""
            SELECT count(*) total,
              count(*) FILTER (WHERE wazuh_agent_id IS NOT NULL) has_agent,
              count(*) FILTER (WHERE asset_ip IS NOT NULL) has_ip,
              count(*) FILTER (WHERE mac_address IS NOT NULL) has_mac,
              (SELECT count(*) FROM (
                 SELECT asset_ip FROM soc_assets WHERE asset_ip IS NOT NULL
                 GROUP BY asset_ip HAVING count(*) > 1) t) dup_ip,
              (SELECT count(*) FROM (
                 SELECT wazuh_agent_id FROM soc_assets
                 WHERE wazuh_agent_id IS NOT NULL
                 GROUP BY wazuh_agent_id HAVING count(*) > 1) t) dup_agent
            FROM soc_assets
        """)).one()
        total = r.total or 0
        return {
            "assets_total": total,
            "by_indicator": {
                "wazuh_agent_id": {
                    "covered": r.has_agent,
                    "ratio": round(r.has_agent / total, 4) if total else None,
                },
                "asset_ip": {
                    "covered": r.has_ip,
                    "ratio": round(r.has_ip / total, 4) if total else None,
                },
                "mac_address": {
                    "covered": r.has_mac,
                    "ratio": round(r.has_mac / total, 4) if total else None,
                },
            },
            "conflicts": {"dup_ip": r.dup_ip, "dup_agent": r.dup_agent},
            "note": ("分母=在册资产（非日志 IP 全集——攻击者公网 IP 计入"
                     "分母是口径错误）；快照非承诺，随资产增长漂移"),
        }
