"""network_segment 推断规则（环境事实表，2026-XX-XX 与用户确认）

唯一用途：给定 asset_ip，推断它属于哪个逻辑网段。

为什么需要这个模块：
  资产唯一约束是 (network_segment, asset_ip) 组合。多网段环境下
  （内网 192.168.0.x + 访客段 192.168.199.x + 多云 VPC 撞段），
  采集器（tplink/wazuh）上报通常不带 network_segment，
  如果统一落 'default'，查重会 miss → 产生重复资产。

  本模块是【唯一】规则来源：
    - scripts/backfill_network_segment.py（存量回填）
    - services/sync_handlers/asset_sync_handler.py（增量同步查重/新建）
  都从这里取规则，避免两处维护漂移。

规则（按当前环境事实登记；新增网段/新云 VPC 时来这里加行）：
  精确 IP 表优先（用于"同私网段但不同云商"的撞段区分），
  其次 CIDR 前缀表，最后兜底 'default'。

命名规范：小写 + 连字符；lan-用途（内网）/ 云商-VPC段 / vps-公网IP。
"""
from __future__ import annotations

# 精确 IP → segment（撞段单机 / asset_ip 即公网 的资产）
_EXACT: dict[str, str] = {
    "172.16.0.10":   "volc-172.16",          # 火山引擎 ECS（lavm 前缀命名）
    "172.16.0.51":   "vps-202.189.23.82",    # 自建 VPS（与火山引擎同撞 172.16.x）
    "154.219.98.59": "vps-154.219.98.59",    # 自建 VPS，asset_ip 即公网 IP
}

# CIDR 前缀 → segment（按前缀长度降序匹配无所谓，前缀互不重叠）
_PREFIX: list[tuple[str, str]] = [
    ("192.168.0.",   "lan-main"),      # 内网主段（TP-Link 主网）
    ("192.168.199.", "lan-199"),       # 内网次段（独立广播域，访客/次 SSID）
    ("172.18.",      "aliyun-172.18"), # 阿里云 VPC（两台 ECS 确认同 VPC）
]

DEFAULT_SEGMENT = "default"


def infer_segment(asset_ip: str | None) -> str:
    """按环境事实表推断 segment。空/异常 IP 返回 DEFAULT_SEGMENT。

    注意：127.0.0.1 / 0.0.0.0 等无效 IP 不做特殊映射，落 default，
    与存量数据处理口径一致（待资产稽核清理）。
    """
    ip = (asset_ip or "").strip()
    if not ip:
        return DEFAULT_SEGMENT
    if ip in _EXACT:
        return _EXACT[ip]
    for prefix, seg in _PREFIX:
        if ip.startswith(prefix):
            return seg
    return DEFAULT_SEGMENT
