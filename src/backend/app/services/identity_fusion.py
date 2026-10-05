"""多因子身份融合评分（OH-3.1 · AOG-3）。

职责（与底座 P1 ``EntityResolver`` 互补，见底座 §4.1/§6.1）：
    判断「来自不同数据源的两条资产观测」是否指向**同一物理实体**，
    输出融合置信度 confidence 与判定结论。

    - 本模块：算"两条观测是否同一实体"的置信度 —— 纯计算；
    - EntityResolver（D-2，独立）：维护"任意源 ID → asset_id"的全局锚定。
    二者叠加才构成完整融合，本模块不依赖它、也不建表。

5 个身份因子（信号强度有强弱）：
    ① IP        asset_ip 一致        权重 .25
    ② MAC       mac_address 一致     权重 .30（强物理信号）
    ③ 主机名     name 归一化后一致    权重 .15
    ④ Wazuh agent id 一致            权重 .20（管理面强 ID）
    ⑤ 硬件指纹  序列号/主板一致       权重 .10（强物理信号）

归一化纪律（避免"双方都没数据"反得高分）：
    某个因子只有在**两条观测都提供了该信号**时才参与打分；
    只在"参与因子"间按权重重归一化。数据缺失既不投赞成也不投反对。

判定（阈值可配）：
    confidence >= auto_merge_threshold(默认 .80)  → auto_merge
    confidence >= review_threshold(默认 .40)      → needs_review
    否则                                          → distinct

冲突仲裁（强否定）：
    若强物理因子（MAC / 硬件指纹）双方都有值却**不一致**，
    即使 IP/主机名相同（DHCP 漂移、改名）也压到 needs_review，不自动合并。

纯净约束：不 import sqlalchemy / fastapi / pydantic，便于 CI 与独立复用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------- 权重配置


@dataclass(frozen=True)
class FactorWeights:
    """因子权重。总和应为 1.0；可被自定义覆盖。"""

    ip: float = 0.25
    mac: float = 0.30
    hostname: float = 0.15
    wazuh_agent: float = 0.20
    hardware: float = 0.10

    def as_dict(self) -> Dict[str, float]:
        return {
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "wazuh_agent": self.wazuh_agent,
            "hardware": self.hardware,
        }


DEFAULT_WEIGHTS = FactorWeights()

# 强物理因子：双方有值却不一致时触发冲突压制
_STRONG_FACTORS = ("mac", "hardware")

# 判定阈值（默认值；调用方可覆盖）
AUTO_MERGE_THRESHOLD_DEFAULT = 0.80
REVIEW_THRESHOLD_DEFAULT = 0.40


class FusionError(ValueError):
    """融合输入非法。消息面向调用方。"""


# ----------------------------------------------------------------- 结果结构


@dataclass(frozen=True)
class FactorScore:
    """单因子评估结果。"""

    name: str
    weight: float
    present: bool            # 双方是否都提供了该信号
    match: bool             # 信号是否一致
    a_value: Optional[str]
    b_value: Optional[str]


@dataclass(frozen=True)
class FusionResult:
    """融合评分结果。"""

    confidence: float
    decision: str            # auto_merge / needs_review / distinct
    factors: List[FactorScore]
    participating_factors: List[str]
    weight_sum: float        # 参与因子的原始权重和（归一化前）
    conflict: bool
    conflict_factors: List[str]
    auto_merge_threshold: float
    review_threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidence": round(self.confidence, 4),
            "decision": self.decision,
            "factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "present": f.present,
                    "match": f.match,
                    "a_value": f.a_value,
                    "b_value": f.b_value,
                }
                for f in self.factors
            ],
            "participating_factors": self.participating_factors,
            "weight_sum": round(self.weight_sum, 4),
            "conflict": self.conflict,
            "conflict_factors": self.conflict_factors,
            "auto_merge_threshold": self.auto_merge_threshold,
            "review_threshold": self.review_threshold,
        }


# ----------------------------------------------------------------- 信号归一化


def _clean(v: Any) -> Optional[str]:
    """统一转字符串并去空白；空值/空串 → None。"""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def norm_ip(v: Any) -> Optional[str]:
    s = _clean(v)
    return s.lower() if s else None


def norm_mac(v: Any) -> Optional[str]:
    """MAC 归一化：去分隔符、转小写，使 00:11.. 与 00-11.. 与 0011.. 等价。"""
    s = _clean(v)
    if s is None:
        return None
    s = re.sub(r"[^0-9a-fA-F]", "", s).lower()
    return s or None


def norm_hostname(v: Any) -> Optional[str]:
    """主机名归一化：小写、去空白、去掉可能的尾点（FQDN root label）。"""
    s = _clean(v)
    if s is None:
        return None
    return s.lower().rstrip(".").strip()


def norm_agent_id(v: Any) -> Optional[str]:
    s = _clean(v)
    return s.lower() if s else None


def norm_hardware(v: Any) -> Optional[str]:
    """硬件指纹归一化。

    接受字符串或 dict（hardware_info）。dict 时优先取序列号/主板序列号，
    多个字段拼接以提高区分度；取值全部缺失 → None。
    """
    if v is None:
        return None
    if isinstance(v, dict):
        keys = (
            "serial_number", "serial", "serialno", "system_serial",
            "board_serial", "baseboard_serial", "uuid", "product_uuid",
        )
        parts = []
        for k in keys:
            val = v.get(k)
            c = _clean(val)
            if c:
                parts.append(c.lower())
        if not parts:
            return None
        return "|".join(parts)
    s = _clean(v)
    return s.lower() if s else None


# 观测记录 → 各因子取值
_EXTRACTORS = {
    "ip": (("asset_ip", "ip", "ip_address"), norm_ip),
    "mac": (("mac_address", "mac", "macaddr"), norm_mac),
    "hostname": (("name", "hostname", "host_name"), norm_hostname),
    "wazuh_agent": (("wazuh_agent_id", "agent_id", "wazuh_agent"), norm_agent_id),
    "hardware": (("hardware_info", "hardware", "serial_number"), norm_hardware),
}


def _extract(obs: Any, factor: str) -> Optional[str]:
    """从观测（dict 或对象）中提取某因子的归一化值。"""
    keys, normalizer = _EXTRACTORS[factor]

    def _get(key: str) -> Any:
        if isinstance(obs, dict):
            return obs.get(key)
        return getattr(obs, key, None)

    for k in keys:
        raw = _get(k)
        if raw is not None:
            val = normalizer(raw)
            if val is not None:
                return val
    return None


# ----------------------------------------------------------------- 核心评分


def score_fusion(
    a: Any,
    b: Any,
    *,
    weights: Optional[FactorWeights] = None,
    auto_merge_threshold: float = AUTO_MERGE_THRESHOLD_DEFAULT,
    review_threshold: float = REVIEW_THRESHOLD_DEFAULT,
) -> FusionResult:
    """对两条观测做融合评分。

    参数:
        a, b: 观测记录（dict 或对象），需含身份信号字段。
        weights: 可选自定义因子权重。
        auto_merge_threshold: 自动合并置信度线。
        review_threshold: 进入人工复核的最低置信度线。
    """
    if a is None or b is None:
        raise FusionError("融合评分需要两条观测记录")
    if not (0.0 <= review_threshold <= auto_merge_threshold <= 1.0):
        raise FusionError("阈值需满足 0 ≤ review ≤ auto_merge ≤ 1")

    w = weights or DEFAULT_WEIGHTS
    wmap = w.as_dict()

    factors: List[FactorScore] = []
    participating: List[str] = []
    conflicts: List[str] = []
    strong_matches: List[str] = []
    weight_sum = 0.0
    matched_weight = 0.0

    for name in ("ip", "mac", "hostname", "wazuh_agent", "hardware"):
        va = _extract(a, name)
        vb = _extract(b, name)
        present = va is not None and vb is not None
        match = present and va == vb
        factors.append(
            FactorScore(
                name=name,
                weight=wmap[name],
                present=present,
                match=match,
                a_value=va,
                b_value=vb,
            )
        )
        if present:
            participating.append(name)
            weight_sum += wmap[name]
            if match:
                matched_weight += wmap[name]
                if name in _STRONG_FACTORS:
                    # 强物理因子一致 → 正向强证据
                    strong_matches.append(name)
            elif name in _STRONG_FACTORS and wmap[name] > 0:
                # 强物理因子双方有值却不一致且权重非零 → 冲突
                conflicts.append(name)

    # 在参与因子间重归一化；无任何共同信号 → confidence=0（无法判断）
    confidence = (matched_weight / weight_sum) if weight_sum > 0 else 0.0

    conflict = bool(conflicts)

    # 冲突压制：强物理信号矛盾时，不允许自动合并
    effective_auto = auto_merge_threshold
    if conflict:
        # 直接把自动合并门槛抬到不可达
        effective_auto = 1.0001
    elif strong_matches:
        # 对称规则：强物理证据一致（同一网卡/主板）时，弱信号不一致
        # （IP 漂移、改名）不应拦截自动合并——门槛降至复核线
        effective_auto = review_threshold

    if confidence >= effective_auto:
        decision = "auto_merge"
    elif confidence >= review_threshold:
        decision = "needs_review"
    else:
        decision = "distinct"

    return FusionResult(
        confidence=confidence,
        decision=decision,
        factors=factors,
        participating_factors=participating,
        weight_sum=weight_sum,
        conflict=conflict,
        conflict_factors=conflicts,
        auto_merge_threshold=auto_merge_threshold,
        review_threshold=review_threshold,
    )


def should_auto_merge(result: FusionResult) -> bool:
    """便于调用方的语义判定。"""
    return result.decision == "auto_merge"


# =========================================================================
# OH-3.2 单资产身份可信度评分（Identity Trust）
# =========================================================================
#
# 与 OH-3.1 的区别：
#   OH-3.1 是 pairwise——"两条观测是否同一实体"；
#   OH-3.2 是 single-asset——"这个已存在资产的身份有多可信"，
#          作为一等评分项，不达阈值不入推理层。
#
# 三个构成维度：
#   coverage      身份因子覆盖广度（5 因子加权覆盖）
#   corroboration 多源佐证（被几个独立来源观测到；单源未经佐证）
#   strength      强身份锚（wazuh agent / MAC / 硬件指纹）
#
# 核心安全语义：单源 + 仅弱信号（IP/主机名）拿不到 trusted。

# 因子在"身份可信度"语境下的覆盖权重（强 ID 更能锚定身份）
_TRUST_FACTOR_WEIGHTS = {
    "ip": 0.15,
    "mac": 0.25,
    "hostname": 0.10,
    "wazuh_agent": 0.30,
    "hardware": 0.20,
}
_STRONG_TRUST_FACTORS = ("wazuh_agent", "mac", "hardware")

# 多源佐证：不同有效来源数 → 佐证分
#   0 源（异常）=0；1 源=0.45（未经独立佐证）；2 源=0.8；3+源=1.0
_CORROBORATION_BY_SOURCES = {0: 0.0, 1: 0.45, 2: 0.8, 3: 1.0}

# 合成权重：coverage / corroboration / strength
TRUST_W_COVERAGE = 0.40
TRUST_W_CORROBORATION = 0.35
TRUST_W_STRENGTH = 0.25

# 分档阈值
TRUSTED_THRESHOLD_DEFAULT = 0.80
TENTATIVE_THRESHOLD_DEFAULT = 0.40


@dataclass(frozen=True)
class IdentityTrustResult:
    """单资产身份可信度评分结果。"""

    identity_confidence: float
    tier: str               # trusted / tentative / unverified
    coverage_score: float
    corroboration_score: float
    strength_score: float
    factors_present: List[str]
    strong_anchors: List[str]
    source_count: int
    eligible_for_reasoning: bool
    trusted_threshold: float
    tentative_threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity_confidence": round(self.identity_confidence, 4),
            "tier": self.tier,
            "coverage_score": round(self.coverage_score, 4),
            "corroboration_score": round(self.corroboration_score, 4),
            "strength_score": round(self.strength_score, 4),
            "factors_present": self.factors_present,
            "strong_anchors": self.strong_anchors,
            "source_count": self.source_count,
            "eligible_for_reasoning": self.eligible_for_reasoning,
            "trusted_threshold": self.trusted_threshold,
            "tentative_threshold": self.tentative_threshold,
        }


def score_identity_trust(
    asset: Any,
    *,
    sources: Optional[List[Any]] = None,
    trusted_threshold: float = TRUSTED_THRESHOLD_DEFAULT,
    tentative_threshold: float = TENTATIVE_THRESHOLD_DEFAULT,
) -> IdentityTrustResult:
    """评估单个资产的身份可信度。

    参数：
        asset: 资产记录（dict 或对象），含身份信号字段。
        sources: 可选的该资产来源列表（AssetSource 对象/dict），
                 用于多源佐证；不传则按单一来源处理。
        trusted_threshold: 可入推理层的置信度线。
        tentative_threshold: 入图谱但结论降权的最低线。
    """
    if asset is None:
        raise FusionError("身份可信度评分需要资产记录")
    if not (0.0 <= tentative_threshold <= trusted_threshold <= 1.0):
        raise FusionError("阈值需满足 0 ≤ tentative ≤ trusted ≤ 1")

    # --- coverage：因子加权覆盖 ---
    present: List[str] = []
    coverage_sum = 0.0
    for name, w in _TRUST_FACTOR_WEIGHTS.items():
        val = _extract(asset, name)
        if val is not None:
            present.append(name)
            coverage_sum += w
    # 权重和为 1，coverage 即加权覆盖度
    coverage_score = min(1.0, coverage_sum)

    # --- strength：强身份锚 ---
    strong = [n for n in _STRONG_TRUST_FACTORS
              if _extract(asset, n) is not None]
    # 至少一个强锚给基础分，多个略提；clamp
    strength_score = 0.0 if not strong else min(1.0, 0.6 + 0.2 * (len(strong) - 1))

    # --- corroboration：多源佐证 ---
    source_count = 0
    if sources is not None:
        # 去重（按 source 名），防止同一来源多条记录虚高
        distinct = set()
        for s in sources:
            key = s.get("source") if isinstance(s, dict) else getattr(s, "source", None)
            if key:
                distinct.add(str(key))
        source_count = len(distinct)
    else:
        # 未提供来源列表：资产至少有主数据源 → 单源
        source_count = 1
    corroboration_score = _CORROBORATION_BY_SOURCES.get(
        min(source_count, 3), 1.0
    )

    # --- 合成 ---
    identity_confidence = (
        coverage_score * TRUST_W_COVERAGE
        + corroboration_score * TRUST_W_CORROBORATION
        + strength_score * TRUST_W_STRENGTH
    )

    if identity_confidence >= trusted_threshold:
        tier = "trusted"
    elif identity_confidence >= tentative_threshold:
        tier = "tentative"
    else:
        tier = "unverified"

    return IdentityTrustResult(
        identity_confidence=identity_confidence,
        tier=tier,
        coverage_score=coverage_score,
        corroboration_score=corroboration_score,
        strength_score=strength_score,
        factors_present=present,
        strong_anchors=strong,
        source_count=source_count,
        eligible_for_reasoning=(tier == "trusted"),
        trusted_threshold=trusted_threshold,
        tentative_threshold=tentative_threshold,
    )
