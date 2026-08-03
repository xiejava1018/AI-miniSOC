"""
日志解析

将 Loki 返回的原始 syslog 行解析为结构化记录，并按秒级去重。

日志格式（TP-Link TL-R479GP-AC 路由器 behavior_ctl）:
    <13>Aug 03 22:28:08 TL-R479GP-AC behavior_ctl: 2026-08-03 22:28:08 <5> :
      上网行为:a:IPGROUP_ANY a:192.168.0.8 网站分组:所有网站 网址:main.vscode-cdn.net 。
    <13>... 上网行为:a:IPGROUP_ANY a:192.168.0.9 apptype:网络基础协议 使用HTTP 。
"""

import ipaddress
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

logger = logging.getLogger(__name__)

# 字段提取正则
_RE_DOMAIN = re.compile(r"网址[:：]\s*([^\s。]+)")
_RE_APPTYPE = re.compile(r"apptype[:：]?\s*([^\s。]+)")
_RE_CATEGORY = re.compile(r"网站分组[:：]\s*([^\s。]+)")
# 日志体中内嵌的时间戳（备份，优先用 Loki 时间戳）
_RE_INNER_TS = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


@dataclass
class BrowsingRecord:
    """解析后的单条上网行为记录"""

    ip: str
    domain: str = ""
    apptype: str = ""
    category: str = ""
    action: str = ""  # "url" 访问网址 / "app" 使用应用
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: str = ""

    @property
    def is_internal(self) -> bool:
        """是否内网 IP（公网 IP 不参与基线检测）"""
        return _is_internal_ip(self.ip)

    @property
    def dedupe_key(self) -> str:
        """秒级去重键"""
        return f"{self.ip}|{self.domain or self.apptype}|{self.ts.strftime('%Y%m%d%H%M%S')}"


def _is_internal_ip(ip: str) -> bool:
    """判断是否内网 IP（私有地址 / 回环 / 链路本地）"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


def _extract_body(raw_line: str) -> str:
    """从 Loki 返回的 JSON 行中提取 body 字段，失败则返回原行"""
    if not raw_line:
        return ""
    line = raw_line.strip()
    # Loki 值通常是 {"body": "..."} 的 JSON
    if line.startswith("{"):
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and "body" in obj:
                return obj["body"]
        except (json.JSONDecodeError, TypeError):
            pass
    return line


def parse_loki_result(loki_result: Iterable[dict]) -> list[BrowsingRecord]:
    """
    解析 Loki query_range 返回的流列表，去重后返回结构化记录。

    仅返回能提取到有效信息的记录（有 ip 且有 domain 或 apptype）。
    """
    seen: set[str] = set()
    records: list[BrowsingRecord] = []

    for stream in loki_result:
        labels = stream.get("stream", {}) or {}
        ip = labels.get("ip", "")
        values = stream.get("values", []) or []

        for ts_ns, raw_line in values:
            body = _extract_body(raw_line)
            if not body:
                continue

            # 解析时间戳（纳秒 → datetime，带时区）
            ts = _ns_to_datetime(ts_ns)

            # 提取字段
            m_domain = _RE_DOMAIN.search(body)
            m_app = _RE_APPTYPE.search(body)
            m_cat = _RE_CATEGORY.search(body)

            domain = m_domain.group(1).rstrip(".") if m_domain else ""
            apptype = m_app.group(1) if m_app else ""
            category = m_cat.group(1) if m_cat else ""

            # 没有任何有效字段则跳过
            if not ip or (not domain and not apptype):
                continue

            action = "url" if domain else "app"

            rec = BrowsingRecord(
                ip=ip,
                domain=domain.lower(),
                apptype=apptype,
                category=category,
                action=action,
                ts=ts,
                raw=body[:500],  # 截断，避免过长
            )

            # 秒级去重（路由器存在重复推送）
            key = rec.dedupe_key
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)

    return records


def _ns_to_datetime(ts_ns) -> datetime:
    """纳秒时间戳 → 带时区的 datetime"""
    try:
        secs = int(ts_ns) / 1_000_000_000
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)
