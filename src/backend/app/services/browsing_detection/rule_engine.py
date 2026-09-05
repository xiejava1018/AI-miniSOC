"""
规则引擎

实现 6 类检测规则，对解析后的记录按 (ip, domain) 聚合打分。

规则：
  R1 恶意域名命中   100  黑名单匹配
  R2 突发高频访问    40  窗口内同IP同域名次数 > burst_threshold
  R3 基线偏离        20  访问历史未见过的域名
  R4 隧道/穿透工具    35  域名匹配隧道关键词
  R5 凌晨活跃        15  凌晨时段该IP访问量超阈值（IP级加成）
  R6 可疑域名特征    15  高熵/超长/IP直连
"""

import fnmatch
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.models.browsing_blacklist import BrowsingBlacklist
from app.services.browsing_detection.config import DetectionConfig
from app.services.browsing_detection.log_parser import BrowsingRecord

logger = logging.getLogger(__name__)


@dataclass
class RuleHitDetail:
    """单条规则命中详情"""
    rule: str       # "R1"
    weight: int
    detail: str


@dataclass
class DetectionFinding:
    """一次聚合后的检测结果（对应一条事件）"""
    ip: str
    domain: str
    apptype: str
    score: int
    rule_hits: List[RuleHitDetail]
    source_count: int
    window_start: datetime
    window_end: datetime


# IP 直连检测（域名实际是 IP 地址）
_RE_IP_LIKE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$")


def shannon_entropy(s: str) -> float:
    """计算字符串的 Shannon 熵"""
    if not s:
        return 0.0
    freq = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _domain_main_part(domain: str) -> str:
    """取域名的主体部分（去掉公共后缀，简化处理：取倒数第二段）"""
    if not domain:
        return ""
    # 去掉协议、端口、路径
    clean = domain.split("/")[0].split(":")[0]
    parts = clean.split(".")
    # 过滤空段
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return clean
    # 取主域名部分（去掉最后1-2段TLD）
    return "".join(parts[:-2]) if len(parts) > 2 else parts[0]


class RuleEngine:
    """检测规则引擎"""

    def __init__(self, db: Session, config: DetectionConfig) -> None:
        self.db = db
        self.config = config
        self.enabled = config.rules_enabled_set
        self._exact_blacklist: set[str] = set()
        self._wildcard_blacklist: list[str] = []
        self._exact_whitelist: set[str] = set()
        self._wildcard_whitelist: list[str] = []
        self._tunnel_re = None
        if config.tunnel_keywords:
            try:
                self._tunnel_re = re.compile(config.tunnel_keywords, re.IGNORECASE)
            except re.error:
                logger.warning("隧道关键词正则无效: %s", config.tunnel_keywords)
        self._load_blacklist()
        # N2 白名单支持通配符（2026-09-05 止血）：与黑名单同款 exact/wildcard 双轨
        for d in config.whitelist_domain_set:
            if "*" in d:
                self._wildcard_whitelist.append(d)
            else:
                self._exact_whitelist.add(d)

    # ── 黑名单加载 ──────────────────────────────────

    def _load_blacklist(self) -> None:
        """预加载 DB 黑名单 + 配置黑名单"""
        try:
            rows = self.db.query(BrowsingBlacklist).all()
            for r in rows:
                d = r.domain.strip().lower()
                if "*" in d:
                    self._wildcard_blacklist.append(d)
                else:
                    self._exact_blacklist.add(d)
        except Exception:
            logger.exception("加载黑名单失败，跳过DB黑名单")

        # 合并配置黑名单
        self._exact_blacklist |= self.config.config_blacklist_set

    def _match_blacklist(self, domain: str) -> bool:
        if not domain:
            return False
        d = domain.lower()
        if d in self._exact_blacklist:
            return True
        for pattern in self._wildcard_blacklist:
            if fnmatch.fnmatch(d, pattern):
                return True
        return False

    def _match_whitelist(self, domain: str) -> bool:
        """白名单匹配：exact + 通配符（与 _match_blacklist 同款逻辑）"""
        if not domain:
            return False
        d = domain.lower()
        if d in self._exact_whitelist:
            return True
        for pattern in self._wildcard_whitelist:
            if fnmatch.fnmatch(d, pattern):
                return True
        return False

    # ── 主入口：评估所有记录 ────────────────────────

    def evaluate(
        self,
        records: List[BrowsingRecord],
        known_map: dict[str, set[str]],
        window_start: datetime,
        window_end: datetime,
    ) -> List[DetectionFinding]:
        """
        对解析后的记录执行规则评估，返回达到阈值的结果列表。

        Args:
            records: 已去重的记录
            known_map: ip -> 已知域名集合（来自基线）
        """
        # 只评估内网IP的记录
        internal = [r for r in records if r.is_internal]
        if not internal:
            return []

        # 过滤白名单（支持通配符，如 *.miwifi.com）
        wl_ips = self.config.whitelist_ip_set
        internal = [
            r for r in internal
            if r.ip not in wl_ips
            and not (r.domain and self._match_whitelist(r.domain))
        ]
        if not internal:
            return []

        # 按 (ip, domain|apptype) 聚合
        groups: dict[tuple[str, str], List[BrowsingRecord]] = defaultdict(list)
        for r in internal:
            key_domain = r.domain or f"[app]{r.apptype}"
            groups[(r.ip, key_domain)].append(r)

        # R5 预计算：凌晨活跃的 IP 集合
        night_ips = self._compute_night_active_ips(internal)

        findings: List[DetectionFinding] = []
        threshold = self.config.score_threshold

        for (ip, domain), recs in groups.items():
            rule_hits: List[RuleHitDetail] = []
            representative = recs[0]  # 用于 apptype 等字段

            # R1 恶意域名
            if "R1" in self.enabled and representative.domain and self._match_blacklist(representative.domain):
                rule_hits.append(RuleHitDetail("R1", 100, f"命中黑名单域名: {representative.domain}"))

            # R2 突发高频（仅对域名类）
            if "R2" in self.enabled and representative.domain:
                count = len(recs)
                if count > self.config.burst_threshold:
                    rule_hits.append(RuleHitDetail("R2", 40, f"窗口内访问 {count} 次(阈值{self.config.burst_threshold})"))

            # R3 基线偏离（仅对域名类）
            if "R3" in self.enabled and representative.domain:
                known = known_map.get(ip, set())
                if representative.domain not in known:
                    rule_hits.append(RuleHitDetail("R3", 20, "历史基线中未见过的域名"))

            # R4 隧道/穿透工具
            if "R4" in self.enabled and representative.domain and self._tunnel_re:
                if self._tunnel_re.search(representative.domain):
                    rule_hits.append(RuleHitDetail("R4", 35, f"匹配隧道关键词: {representative.domain}"))

            # R6 可疑域名特征
            if "R6" in self.enabled and representative.domain:
                detail = self._check_domain_suspicious(representative.domain)
                if detail:
                    rule_hits.append(RuleHitDetail("R6", 15, detail))

            # R5 凌晨活跃（IP级加成）
            if "R5" in self.enabled and ip in night_ips:
                rule_hits.append(RuleHitDetail("R5", 15, f"凌晨({self.config.night_start_hour}-{self.config.night_end_hour}点)活跃"))

            # 打分
            score = sum(h.weight for h in rule_hits)
            if score < threshold:
                continue

            findings.append(DetectionFinding(
                ip=ip,
                domain=domain,
                apptype=representative.apptype,
                score=score,
                rule_hits=[{"rule": h.rule, "weight": h.weight, "detail": h.detail} for h in rule_hits],
                source_count=len(recs),
                window_start=window_start,
                window_end=window_end,
            ))

        # 按分值倒序
        findings.sort(key=lambda f: f.score, reverse=True)
        return findings

    # ── R5 凌晨活跃 IP 计算 ─────────────────────────

    def _compute_night_active_ips(self, records: List[BrowsingRecord]) -> set[str]:
        """计算凌晨时段活跃超过阈值的 IP"""
        start_h = self.config.night_start_hour
        end_h = self.config.night_end_hour
        threshold = self.config.night_count_threshold
        ip_counter: Counter = Counter()
        for r in records:
            # Loki 时间戳为 UTC，中国时区 UTC+8（凌晨按北京时间判断）
            hour = (r.ts.hour + 8) % 24
            if start_h <= end_h:
                in_night = start_h <= hour < end_h
            else:
                # 跨午夜，如 22~5
                in_night = hour >= start_h or hour < end_h
            if in_night:
                ip_counter[r.ip] += 1
        return {ip for ip, n in ip_counter.items() if n >= threshold}

    # ── R6 可疑域名特征 ─────────────────────────────

    def _check_domain_suspicious(self, domain: str) -> str:
        """检查域名是否可疑，返回命中描述或空串"""
        d = domain.strip().lower()
        if not d:
            return ""
        # IP 直连
        if _RE_IP_LIKE.match(d):
            return f"直接使用IP访问: {d}"
        # 超长
        if len(d) >= 63:
            return f"域名超长({len(d)}字符)"
        # 高熵
        main = _domain_main_part(d)
        if main:
            ent = shannon_entropy(main)
            if ent >= 4.0 and len(main) >= 8:
                return f"域名熵值偏高({ent:.2f}): {main}"
        return ""
