"""OH-2.4 证据链生成器（Evidence Chain Generator）。

**设计目的**（主方案 + 实施方案 OH-2.4）：
1. 把 AssetProfile 中所有 evidence[] 合并为统一时间线
2. 每项证据带 source / observed_at / confidence / evidence_id
3. 生成可审计的责任链：哪些维度扣分，扣分依据哪些证据，证据来自哪个 ORM 表
4. 输出 JSON-LD 风格 dict（前端「证据链」按钮消费）

**与既有 AHS / 画像的关系**：
- 输入：AssetProfile（含 ahs_score + 5 个 DimensionScore evidence[]）
- 输出：EvidenceChain（含 timeline[] + summary + JSON-LD dict）
- **不修改 AssetProfile**（frozen 兼容），纯计算 + 内存操作

**JSON-LD 风格字段**：
- @type: "EvidenceChain"
- @id: "evchain-{asset_id}-{sha256[:8]}"
- asset_id, ahs_score, generated_at
- timeline: List[EvidenceEntry]
- summary: {total_evidence, sources[], avg_confidence, timespan}

**降级**：
- AssetProfile 为空（evidence=[]） → 返回空链（marker=空 dict）
- 时间字段缺失 → 用 datetime.now(timezone.utc) 兜底
- confidence 越界（loader 异常）→ __post_init__ 已拦截；此处兜底：clamp 到 [0,1]
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.asset_profile._main import (
    AssetProfile,
    EvidenceItem,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceEntry:
    """单条证据（带 evidence_id + 归属维度）。"""

    evidence_id: str                      # sha256(asset_id + source + observed_at)[:12]
    dimension: str                       # identity/ownership/technology/exposure/vulnerability/threat/compliance/behavior/ahs
    source: str                          # ORM 表名
    observed_at: datetime
    confidence: float                    # [0, 1]
    reference: Optional[str] = None       # 行号 / commit / doc 引用
    note: Optional[str] = None            # 自由文本（loader 写入的备注）

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "dimension": self.dimension,
            "source": self.source,
            "observed_at": self.observed_at.isoformat() if isinstance(self.observed_at, datetime) else str(self.observed_at),
            "confidence": round(self.confidence, 4),
            "reference": self.reference,
            "note": self.note,
        }


@dataclass(frozen=True)
class EvidenceChainSummary:
    """证据链统计摘要。"""

    total_evidence: int = 0
    sources: List[str] = field(default_factory=list)         # 去重后的 source 列表
    dimensions: List[str] = field(default_factory=list)      # 有数据的维度
    avg_confidence: float = 0.0
    earliest_observed_at: Optional[str] = None              # ISO string
    latest_observed_at: Optional[str] = None
    timespan_hours: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "total_evidence": self.total_evidence,
            "sources": sorted(self.sources),
            "dimensions": sorted(self.dimensions),
            "avg_confidence": round(self.avg_confidence, 4),
            "earliest_observed_at": self.earliest_observed_at,
            "latest_observed_at": self.latest_observed_at,
            "timespan_hours": round(self.timespan_hours, 2) if self.timespan_hours is not None else None,
        }


@dataclass(frozen=True)
class EvidenceChain:
    """证据链（输出）。"""

    asset_id: str
    ahs_score: int
    state: str                            # "valid" / "insufficient_data" / "ahs_not_computed"
    chain_id: str                         # sha256(asset_id + AHS + evidence count)[:8]
    timeline: List[EvidenceEntry] = field(default_factory=list)  # 按 observed_at 升序
    summary: EvidenceChainSummary = field(default_factory=EvidenceChainSummary)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "@type": "EvidenceChain",
            "@id": f"evchain-{self.asset_id}-{self.chain_id}",
            "asset_id": self.asset_id,
            "ahs_score": self.ahs_score,
            "state": self.state,
            "chain_id": self.chain_id,
            "timeline": [e.to_dict() for e in self.timeline],
            "summary": self.summary.to_dict(),
            "generated_at": self.generated_at,
        }

    def to_jsonld(self) -> str:
        """JSON-LD 风格序列化字符串（前端直接渲染）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _make_evidence_id(asset_id: str, source: str, observed_at: datetime) -> str:
    """生成稳定的 evidence_id（同样输入 → 同样 ID）。"""
    raw = f"{asset_id}|{source}|{observed_at.isoformat() if isinstance(observed_at, datetime) else observed_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _clamp_confidence(c: float) -> float:
    """confidence 兜底（OH-2.1 __post_init__ 已拦，此处兜底）。"""
    try:
        return max(0.0, min(1.0, float(c)))
    except (TypeError, ValueError):
        return 0.0


def _safe_observed_at(dt: Any) -> datetime:
    """observed_at 兜底（None 或非法 → now(utc)）。"""
    if isinstance(dt, datetime):
        return dt
    return datetime.now(timezone.utc)


def _collect_dimension_evidence(
    profile: AssetProfile,
) -> List[tuple[str, EvidenceItem]]:
    """从 AssetProfile 收集所有 (dimension, evidence) 元组。

    八维 + AHS（ahs_evidence 作为 'ahs' 维度）。
    """
    out: List[tuple[str, EvidenceItem]] = []
    out.extend(("identity", ev) for ev in profile.identity.evidence)
    out.extend(("ownership", ev) for ev in profile.ownership.evidence)
    out.extend(("technology", ev) for ev in profile.technology.evidence)
    out.extend(("exposure", ev) for ev in profile.exposure.evidence)
    out.extend(("vulnerability", ev) for ev in profile.vulnerability.evidence)
    out.extend(("threat", ev) for ev in profile.threat.evidence)
    out.extend(("compliance", ev) for ev in profile.compliance.evidence)
    out.extend(("behavior", ev) for ev in profile.behavior.evidence)
    out.extend(("ahs", ev) for ev in profile.ahs_evidence)
    return out


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def build_evidence_chain(
    profile: AssetProfile,
    *,
    state: Optional[str] = None,
    dedup_by_source: bool = True,
) -> EvidenceChain:
    """生成证据链。

    Args:
        profile: 八维画像（含 ahs_score + ahs_evidence）
        state: AHS 状态（"valid"/"insufficient_data"/"ahs_not_computed"）。
               None → 根据 ahs_score 自动判断（0 → "ahs_not_computed"）
        dedup_by_source: 是否按 source 去重（每个 ORM 表只留最新一条），
                        默认 True（避免 timeline 过长）

    Returns:
        EvidenceChain（frozen + JSON-LD ready）
    """
    raw_entries = _collect_dimension_evidence(profile)

    # 1. dedup_by_source=True：仅按 source 去重 → 每个 ORM 表只留**最新**一条
    #    dedup_by_source=False：按 (source, observed_at) 去重 → 同表多条保留
    #    **不分两步**：一轮 O(n) 跨同 source 取最新，跳过 set().add() 的“首条”语义
    if dedup_by_source:
        latest_per_source: dict[str, tuple[str, EvidenceItem]] = {}
        for dim, ev in raw_entries:
            obs = _safe_observed_at(ev.observed_at)
            cur = latest_per_source.get(ev.source)
            if cur is None or _safe_observed_at(cur[1].observed_at) <= obs:
                latest_per_source[ev.source] = (dim, ev)
        deduped = list(latest_per_source.values())
    else:
        seen_keys: set = set()
        deduped = []
        for dim, ev in raw_entries:
            obs = _safe_observed_at(ev.observed_at)
            key = (ev.source, obs)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append((dim, ev))

    # 2. 按 observed_at 升序
    deduped_sorted = sorted(deduped, key=lambda x: _safe_observed_at(x[1].observed_at))

    # 3. 转 EvidenceEntry
    entries: List[EvidenceEntry] = []
    for dim, ev in deduped_sorted:
        obs = _safe_observed_at(ev.observed_at)
        entries.append(EvidenceEntry(
            evidence_id=_make_evidence_id(profile.asset_id, ev.source, obs),
            dimension=dim,
            source=ev.source,
            observed_at=obs,
            confidence=_clamp_confidence(ev.confidence),
            reference=ev.reference,
            note=ev.note,
        ))

    # 3. 按 observed_at 升序（deduped_sorted 已排，此处再去重保险）
    entries.sort(key=lambda e: e.observed_at)

    # 4. 状态判定
    if state is None:
        state = "ahs_not_computed" if profile.ahs_score == 0 else "valid"

    # 5. 摘要
    summary = _build_summary(entries)

    # 6. chain_id = sha256(asset_id + ahs + count)[:8]
    chain_id_src = f"{profile.asset_id}|{profile.ahs_score}|{len(entries)}"
    chain_id = hashlib.sha256(chain_id_src.encode("utf-8")).hexdigest()[:8]

    return EvidenceChain(
        asset_id=profile.asset_id,
        ahs_score=profile.ahs_score,
        state=state,
        chain_id=chain_id,
        timeline=entries,
        summary=summary,
    )


def _build_summary(entries: List[EvidenceEntry]) -> EvidenceChainSummary:
    """统计摘要。"""
    if not entries:
        return EvidenceChainSummary()

    sources = {e.source for e in entries}
    dimensions = {e.dimension for e in entries}
    confidences = [e.confidence for e in entries]
    avg_confidence = sum(confidences) / len(confidences)

    times = sorted(e.observed_at for e in entries)
    earliest = times[0]
    latest = times[-1]
    timespan_hours: Optional[float] = None
    if isinstance(earliest, datetime) and isinstance(latest, datetime):
        delta = latest - earliest
        timespan_hours = delta.total_seconds() / 3600.0

    return EvidenceChainSummary(
        total_evidence=len(entries),
        sources=sorted(sources),
        dimensions=sorted(dimensions),
        avg_confidence=round(avg_confidence, 4),
        earliest_observed_at=earliest.isoformat() if isinstance(earliest, datetime) else str(earliest),
        latest_observed_at=latest.isoformat() if isinstance(latest, datetime) else str(latest),
        timespan_hours=timespan_hours,
    )


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def build_evidence_chain_from_ahs_result(
    profile: AssetProfile,
    ahs_result,
) -> EvidenceChain:
    """从 AHSResult 构建证据链（带 state 透传）。"""
    from app.services.asset_profile.ahs_service import AHSResult
    if not isinstance(ahs_result, AHSResult):
        raise TypeError(f"ahs_result 必须为 AHSResult, got {type(ahs_result).__name__}")

    state = ahs_result.state if hasattr(ahs_result, "state") else "ahs_not_computed"
    return build_evidence_chain(profile, state=state)


def group_by_source(chain: EvidenceChain) -> Dict[str, List[EvidenceEntry]]:
    """按 source 分组（前端可按"数据来源"折叠展示）。"""
    out: Dict[str, List[EvidenceEntry]] = {}
    for e in chain.timeline:
        out.setdefault(e.source, []).append(e)
    return out


def group_by_dimension(chain: EvidenceChain) -> Dict[str, List[EvidenceEntry]]:
    """按 dimension 分组（前端可按"八维"折叠展示）。"""
    out: Dict[str, List[EvidenceEntry]] = {}
    for e in chain.timeline:
        out.setdefault(e.dimension, []).append(e)
    return out


def filter_by_confidence(
    chain: EvidenceChain,
    *,
    min_confidence: float = 0.0,
    max_confidence: float = 1.0,
) -> List[EvidenceEntry]:
    """按置信度区间过滤证据条目。"""
    return [
        e for e in chain.timeline
        if min_confidence <= e.confidence <= max_confidence
    ]