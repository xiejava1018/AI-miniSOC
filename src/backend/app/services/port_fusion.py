"""端口多源融合（方案 A：一端口一行，字段级融合）

soc_asset_ports 的 (asset_ip, port, protocol) 唯一，多个来源（scanner / wazuh /
manual）对同一端口的观测在字段级融合：

- sources: 观测来源清单（并集）
- last_seen_by_source: 每来源各自最后观测时间；全局 last_seen = max
- service/version/banner: 非空不覆盖空；高优先来源可覆盖低优先来源的值
  （scanner 实测指纹 > wazuh 本地监听 > manual 人工登记）
- state 冲突取更悲观（closed > filtered > open，宁误报不漏报）
- vulnerabilities: CVE 并集（沿用既有逻辑）
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 来源优先级：值越大越权威（指纹类字段）
SOURCE_PRIORITY = {"scanner": 3, "wazuh": 2, "manual": 1}

# state 悲观度：取更悲观者（安全工具宁误报不漏报）
STATE_SEVERITY = {"closed": 3, "filtered": 2, "open": 1}


def merge_sources(existing: Optional[list], source: str) -> list:
    lst = list(existing or [])
    if source not in lst:
        lst.append(source)
    return lst


def merge_last_seen_by_source(existing: Optional[dict], source: str,
                              seen_at: Optional[datetime]) -> dict:
    d = dict(existing or {})
    if seen_at is None:
        seen_at = datetime.now(timezone.utc)
    old = d.get(source)
    # 只前进不后退（ISO 字符串比较等价于时间比较）
    if old is None or str(seen_at) > str(old):
        d[source] = seen_at.isoformat() if hasattr(seen_at, "isoformat") else str(seen_at)
    return d


def _global_last_seen(by_source: dict, fallback: Optional[datetime]) -> Optional[datetime]:
    vals = [v for v in (by_source or {}).values()]
    if not vals:
        return fallback
    return max(vals)  # ISO 字符串 max 等价时间 max


def _should_override(field: str, existing_value, new_value, existing_sources, new_source) -> bool:
    """指纹类字段是否允许新值覆盖旧值。

    规则：
    1. 新值为空 → 不覆盖（沿用现有 `item.get(x) or existing.x` 范式）
    2. 旧值为空 → 覆盖
    3. 都非空 → 新来源优先级 >= 记录中最高优先来源才覆盖
    """
    if not new_value:
        return False
    if existing_value in (None, ""):
        return True
    old_max = max((SOURCE_PRIORITY.get(s, 0) for s in (existing_sources or [])), default=0)
    return SOURCE_PRIORITY.get(new_source, 0) >= old_max


def merge_state(existing_state: Optional[str], new_state: Optional[str]) -> Optional[str]:
    """state 冲突取更悲观（closed > filtered > open）。"""
    if not new_state:
        return existing_state
    if not existing_state:
        return new_state
    if STATE_SEVERITY.get(new_state, 0) >= STATE_SEVERITY.get(existing_state, 0):
        return new_state
    return existing_state


def apply_fusion(port, source: str, item: dict) -> bool:
    """把一次观测融合进既有 AssetPort 行（原地修改），返回是否有变化。

    port: AssetPort ORM 实例（须已存在）
    item: 观测数据（asset_ip/port/protocol/service/version/service_banner/state/
          cves/scan_time）
    """
    existing_sources = list(port.sources or [])
    changed = False

    new_sources = merge_sources(existing_sources, source)
    if new_sources != existing_sources:
        port.sources = new_sources
        changed = True

    seen_at = item.get("scan_time") or datetime.now(timezone.utc)
    new_by_source = merge_last_seen_by_source(port.last_seen_by_source, source, seen_at)
    if new_by_source != (port.last_seen_by_source or {}):
        port.last_seen_by_source = new_by_source
        changed = True
        gl = _global_last_seen(new_by_source, port.last_seen)
        if gl is not None and (port.last_seen is None or str(gl) > str(port.last_seen)):
            port.last_seen = gl

    for field in ("service", "version", "service_banner"):
        new_v = item.get(field)
        if _should_override(field, getattr(port, field, None), new_v, existing_sources, source):
            setattr(port, field, new_v)
            changed = True

    new_state = merge_state(port.state, item.get("state"))
    if new_state and new_state != port.state:
        port.state = new_state
        changed = True

    new_cves = item.get("cves") or []
    if new_cves:
        merged = sorted(set(port.vulnerabilities or []) | set(new_cves))
        if merged != list(port.vulnerabilities or []):
            port.vulnerabilities = merged
            changed = True

    return changed


def new_port_fields(source: str, item: dict) -> dict:
    """新建 AssetPort 行时的 sources / last_seen_by_source / last_seen 字段。"""
    seen_at = item.get("scan_time") or datetime.now(timezone.utc)
    by_source = merge_last_seen_by_source({}, source, seen_at)
    return {
        "sources": [source],
        "last_seen_by_source": by_source,
        "last_seen": seen_at,
    }
