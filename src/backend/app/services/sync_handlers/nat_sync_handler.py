"""
NAT 端口映射同步处理器（OH-6.1b，S2 暴露面归位第③段）

数据流（docs/design/2026-09-30-资产管理AI能力建设方案.md §5.2）：
  tplink-collector NAT 分支（firewall.redirect，5min）
    → POST /data/sync (data_type=nat_mapping)
    → 本 handler
    → soc_maps_to（按唯一约束 upsert）

设计要点：
  - 幂等：唯一约束 (source, wan_if, wan_port, protocol, internal_ip,
    internal_port)——同一路由器同一外网端口/协议/内网目标只一行，
    重复推送走 last_seen_at/updated 刷新。
  - wan_ip 当前不采集（firewall.redirect 不含公网 IP，实测 2026-XX）；
    OH-6.1a 落地后由本 handler 回填（item 带 wan_ip 即更新，防回退）。
  - 字段与已建表对齐（迁移 4d5e6f7a8b9c）：无 confidence——静态 NAT
    规则是配置事实，置信度属图谱边属性（OH-3.4 入图时定）。
  - source_health：独立 key "tplink:nat"（与 tplink:collector 的资产健康
    分开，/data-health 各自可见）；预期间隔 300s 同采集节奏。
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy.orm import Session

from app.models.nat_mapping import NatMapping
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)

# P4 WO-2 同款：source → source_health source_key 映射（当前仅 tplink 推 NAT）
_SOURCE_HEALTH_KEYS = {
    "tplink": "tplink:nat",
    "tplink-router": "tplink:nat",
}
_SOURCE_HEALTH_INTERVALS = {
    "tplink": 300,
    "tplink-router": 300,
}

_VALID_PROTOCOLS = {"tcp", "udp", "all"}

# OH-6.1a：WAN 公网 IP 回填。firewall.redirect 不含公网 IP（实测），
# 路由器 API 的运行时状态表亦未开放（network.interface 只有配置无运行 IP，
# 探测被限流后改用本方案）。后端进程部署在与路由器同出口的内网（102）时，
# HTTP 回显服务返回的出口 IP 即 WAN 口公网 IP（单线 PPPoE 场景准确）。
# DNS 方案（grafana.xiejava.dpdns.org）不可用：域名挂 Cloudflare 代理，
# 解析出的是 CF 边缘 IP 非 WAN（实测 2026-10-01）。
_WAN_IP_CACHE = {"ip": None, "ts": 0.0}
_WAN_IP_TTL = 300  # 同采集节奏，避免每条规则都请求外部服务


def _get_wan_ip() -> str | None:
    """获取后端出口 IP（=路由器 WAN 公网 IP）。

    带缓存；多回显服务 fallback；全失败返回 None（调用方不得覆盖已有值）。
    注意：仅当后端与路由器同出口（102 生产部署）时语义正确；
    本地 dev 走代理拿到的是代理出口，仅开发参考不作生产数据。
    """
    import ipaddress
    import time
    import urllib.request

    now = time.time()
    if _WAN_IP_CACHE["ip"] and now - _WAN_IP_CACHE["ts"] < _WAN_IP_TTL:
        return _WAN_IP_CACHE["ip"]
    for url in ("http://ifconfig.me", "http://api.ipify.org"):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                ip = resp.read().decode().strip()
                ipaddress.ip_address(ip)  # 非法串在此抛异常进下一 fallback
                _WAN_IP_CACHE.update(ip=ip, ts=now)
                return ip
        except Exception:
            continue
    return None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class NatSyncHandler(BaseSyncHandler):
    """NAT 端口映射同步：upsert soc_maps_to（OH-6.1b）。"""

    data_type = "nat_mapping"

    def handle(self, source: str, items: list[dict], db: Session, task_uuid: str | None = None) -> dict:
        """批量 upsert + source_health 上报（成功/源级失败都记，防 /data-health 盲区）。

        task_uuid 参数仅为与 base/其他 handler 的调用约定一致（data_sync.py
        F-S3 透传），NAT 同步不消费它。
        """
        try:
            # OH-6.1a：每轮取一次 WAN 出口 IP 注入 items（失败不注入，
            # handler 对无 wan_ip 的 item 跳过回填，保留 DB 原值）
            wan_ip = _get_wan_ip()
            if wan_ip:
                for it in items:
                    it.setdefault("wan_ip", wan_ip)
            stats = super().handle(source, items, db)
            # 数据源健康上报（成功/部分失败都算"采集活着"；逐条失败已入死信）
            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:nat")
                SourceHealthRecorder(db).record_success(
                    key,
                    source_type=source,
                    records_count=stats.get("total"),
                    expected_interval_seconds=_SOURCE_HEALTH_INTERVALS.get(source),
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.debug("source_health record_success failed", exc_info=True)
            return stats
        except Exception as e:
            # 源级失败（DB 炸 / 未知异常）记 record_failure，独立 session 防被灭
            logger.error("NatSyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.services.source_health import SourceHealthRecorder
                from app.core import database as _db
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:nat")
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        key,
                        source_type=source,
                        error=f"{type(e).__name__}: {e}"[:1000],
                    )
                    fail_db.commit()
                finally:
                    fail_db.close()
            except Exception:
                logger.debug("source_health record_failure failed", exc_info=True)
            raise

    def _validate_one(self, item: dict) -> None:
        """必填字段校验：内网 IP 可解析、端口可转 int、协议在白名单。"""
        from ipaddress import ip_address

        ip = (item.get("internal_ip") or "").strip()
        if not ip:
            raise ValueError("缺少 internal_ip 字段")
        try:
            ip_address(ip)
        except ValueError:
            raise ValueError(f"internal_ip 不是合法 IP: {ip!r}")

        if _as_int(item.get("wan_port")) is None:
            raise ValueError(f"wan_port 非法: {item.get('wan_port')!r}")
        if _as_int(item.get("internal_port")) is None:
            raise ValueError(f"internal_port 非法: {item.get('internal_port')!r}")

        proto = (item.get("protocol") or "all").lower()
        if proto not in _VALID_PROTOCOLS:
            raise ValueError(f"protocol 非法: {proto!r}（允许 {_VALID_PROTOCOLS}）")

    def _item_key(self, item: dict) -> str:
        """死信 item_key（按映射五元组，便于排查）。"""
        return (
            f"{item.get('wan_port')}/{item.get('protocol')}"
            f"->{item.get('internal_ip')}:{item.get('internal_port')}"
        )

    def _handle_one(self, source: str, item: dict, db: Session) -> Dict[str, int]:
        """单条 upsert。source 以推送层参数为准（忽略 item 内同名键，防伪造）。"""
        now = datetime.now(timezone.utc)

        proto = (item.get("protocol") or "all").lower()
        wan_port = _as_int(item["wan_port"])
        internal_port = _as_int(item["internal_port"])
        wan_if = (item.get("wan_if") or "WAN").strip() or "WAN"
        internal_ip = item["internal_ip"].strip()

        existing: NatMapping | None = (
            db.query(NatMapping)
            .filter(
                NatMapping.source == source,
                NatMapping.wan_if == wan_if,
                NatMapping.wan_port == wan_port,
                NatMapping.protocol == proto,
                NatMapping.internal_ip == internal_ip,
                NatMapping.internal_port == internal_port,
            )
            .first()
        )

        if existing:
            existing.rule_name = item.get("rule_name")
            existing.enabled = bool(item.get("enabled", True))
            # wan_ip 只在有新值时更新（防 OH-6.1a 回填后被空值冲掉）
            if item.get("wan_ip"):
                existing.wan_ip = str(item["wan_ip"]).strip()
            existing.last_seen_at = now
            db.flush()
            return {"updated": 1}

        row = NatMapping(
            source=source,
            wan_if=wan_if,
            protocol=proto,
            wan_port=wan_port,
            wan_ip=str(item["wan_ip"]).strip() if item.get("wan_ip") else None,
            internal_ip=internal_ip,
            internal_port=internal_port,
            rule_name=item.get("rule_name"),
            enabled=bool(item.get("enabled", True)),
            last_seen_at=now,
        )
        db.add(row)
        db.flush()
        return {"created": 1}