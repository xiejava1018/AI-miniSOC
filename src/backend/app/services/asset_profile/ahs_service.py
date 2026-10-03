"""OH-2.2 AHS（Asset Health Score，资产健康分）计算服务。

**设计原则**（主方案 §3.3 + 跟踪表硬约束）：
1. **输入**：OH-2.1 八维画像 `AssetProfile`（含证据 + 关键性 3 维）
2. **输出**：0-100 分 + 证据链 + 计算元数据
3. **与 `asset_risk.py` 并存不替换**：
   - `risk_score` = 既有四维（暴露 30 + 健康 25 + 告警 25 + 重要性 20），用于"风险"语义
   - `ahs_score` = 新五维扣分（健康/风险语义相反），用于"健康"语义
   - `risk_score` 作为脆弱/威胁维输入之一
4. **降级路径**（主方案 §3.3 红线）：
   - 等保字段空 → 该维取中性值（不放大/不报错）
   - 合规缺口 w4 无数据 → 权重并入其余维重归一化
   - 覆盖率极低 → 整体分无效（state="insufficient_data"），禁止误导
5. **不依赖 sqlalchemy / fastapi / pydantic**（OH-2.1 强约束，方便独立 CI）
6. **不修改 AssetProfile**（frozen=True），返回 AHSResult 给调用方

**模块边界**：
- `compute_ahs(profile)`：纯函数，无 DB 依赖
- `AHSResult`：frozen，evidence[] + score + state
- `AHS_DIMENSION_WEIGHTS`：默认权重（与 `asset_risk.py` 兼容）
- `CRITICALITY_FACTOR`：BIA × CIA × 等保 → 0.8~1.5 系数
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.services.asset_profile._main import (
    AssetProfile,
    EvidenceItem,
)

# ---------------------------------------------------------------------------
# 维度权重（主方案 §3.3 公式）
# ---------------------------------------------------------------------------
# 五维权重总和 = 1.0
# 数据缺失 → 重归一化（剩余维按比例放大）
# 关键性系数（关键资产扣分更重） = 0.8 ~ 1.5
AHS_DIMENSION_WEIGHTS: dict[str, float] = {
    "exposure": 0.20,        # 暴露面风险（公网/端口）
    "vulnerability": 0.25,   # 脆弱性（含 risk_score 输入）
    "threat": 0.25,          # 威胁（告警/事件）
    "compliance": 0.15,      # 合规缺口
    "behavior": 0.15,        # 行为异常
}

# 资产关键性系数（BIA × CIA × 等保）→ 范围 0.8 ~ 1.5
# 关键性越高，扣分越重（AHS 越低），促使优先修复
# 注：业务影响（BIA）/数据敏感度（CIA）来自 `criticality.py` 5 档常量
CRITICALITY_FACTOR_BIA = {
    "core":       1.30,   # 核心业务
    "important":  1.10,   # 重要业务
    "normal":     1.00,   # 一般业务
    "auxiliary":  0.90,   # 辅助
    "ignorable":  0.80,   # 可忽略
    None:         1.00,   # 缺数据 → 中性
}
CRITICALITY_FACTOR_CIA = {
    "extreme":    1.30,
    "high":       1.15,
    "medium":     1.00,
    "low":         0.90,
    "negligible":  0.80,
    None:         1.00,
}
CRITICALITY_FACTOR_PROTECTION = {
    "level_5":    1.50,   # 等保五级
    "level_4":    1.30,
    "level_3":    1.10,
    "level_2":    0.95,
    "level_1":    0.85,
    None:         1.00,   # 缺数据 → 中性（主方案红线：禁止放大）
}


@dataclass(frozen=True)
class DimensionScore:
    """单维扣分明细。"""

    name: str                          # exposure/vulnerability/threat/compliance/behavior
    raw_score: int                     # 0-100 原始扣分
    weight: float                      # 原始权重
    effective_weight: float            # 重归一化后的实际权重（数据缺时按 0.5 折 或 跳过）
    data_gap: bool                     # 该维数据是否全缺
    contributing_factors: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AHSResult:
    """AHS 计算结果。

    状态机：
    - "valid"              → 至少 3 维有数据 + 分数已加权
    - "insufficient_data" → 覆盖维 < 3 或整体可信度过低，禁止用作排序
    """

    asset_id: str
    score: int                                # 0-100
    state: str                               # valid / insufficient_data
    criticality_factor: float               # 0.8~1.5
    dimensions: List[DimensionScore] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    computed_at: Optional[str] = None        # ISO 8601 string

    def to_dict(self) -> dict:
        """JSON-safe dict（与 profile_to_dict 一致）。"""
        return {
            "asset_id": self.asset_id,
            "score": self.score,
            "state": self.state,
            "criticality_factor": self.criticality_factor,
            "dimensions": [
                {
                    "name": d.name,
                    "raw_score": d.raw_score,
                    "weight": d.weight,
                    "effective_weight": d.effective_weight,
                    "data_gap": d.data_gap,
                    "contributing_factors": d.contributing_factors,
                    "evidence_count": len(d.evidence),
                }
                for d in self.dimensions
            ],
            "evidence_count": len(self.evidence),
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# 单维评分函数
# ---------------------------------------------------------------------------

def _score_exposure(profile: AssetProfile) -> DimensionScore:
    """④ 暴露面维度（0-100，越高越差）。"""
    exp = profile.exposure
    factors: List[str] = []
    score = 0
    data_gap = not exp.evidence

    if exp.public_ip:
        score += 40
        factors.append(f"公网 IP: {exp.public_ip}")
    if exp.exposure_level == "public":
        score += 30
        factors.append("exposure_level=public")
    elif exp.exposure_level == "dmz":
        score += 20
        factors.append("exposure_level=dmz")
    elif exp.exposure_level == "isolated":
        score -= 30  # 隔离网络 → 减分（健康加分）
        factors.append("exposure_level=isolated（隔离网络）")

    score = max(0, min(100, score))
    if not data_gap and not factors:
        factors.append(f"内网资产（{exp.exposure_level or 'internal'}）")
    return DimensionScore(
        name="exposure",
        raw_score=score,
        weight=AHS_DIMENSION_WEIGHTS["exposure"],
        effective_weight=AHS_DIMENSION_WEIGHTS["exposure"],
        data_gap=data_gap,
        contributing_factors=factors,
        evidence=list(exp.evidence),
    )


def _score_vulnerability(profile: AssetProfile) -> DimensionScore:
    """⑤ 脆弱性维度（0-100，越高越差）。

    输入：vuln.risk_score（asset_risk.py 既有 0-100）+ vuln 计数
    """
    vuln = profile.vulnerability
    factors: List[str] = []
    score = 0
    data_gap = not vuln.evidence

    # risk_score（既有评分，0-100，越高越危险）→ 直接进入
    if vuln.risk_score is not None:
        score = max(score, vuln.risk_score)
        factors.append(f"risk_score={vuln.risk_score}")

    # 漏洞计数（critical 30 + high 15 + medium 5 + low 2，封顶 100）
    crit = vuln.vuln_by_severity.get("critical", 0)
    high = vuln.vuln_by_severity.get("high", 0)
    med = vuln.vuln_by_severity.get("medium", 0)
    low = vuln.vuln_by_severity.get("low", 0)
    count_score = min(100, crit * 30 + high * 15 + med * 5 + low * 2)
    if count_score > 0:
        score = max(score, count_score)
        factors.append(f"活跃漏洞 critical={crit} high={high} medium={med} low={low}")

    if vuln.unfixed_high_count > 0:
        score += min(20, vuln.unfixed_high_count * 5)
        factors.append(f"未修复高危 {vuln.unfixed_high_count}")

    score = max(0, min(100, score))
    if not data_gap and not factors:
        factors.append("未见活跃漏洞")
    return DimensionScore(
        name="vulnerability",
        raw_score=score,
        weight=AHS_DIMENSION_WEIGHTS["vulnerability"],
        effective_weight=AHS_DIMENSION_WEIGHTS["vulnerability"],
        data_gap=data_gap,
        contributing_factors=factors,
        evidence=list(vuln.evidence),
    )


def _score_threat(profile: AssetProfile) -> DimensionScore:
    """⑥ 威胁维度（0-100，越高越差）。"""
    thr = profile.threat
    factors: List[str] = []
    score = 0
    data_gap = not thr.evidence

    # 告警级别（critical 50 + high 30 + medium 10 + low 2）
    if thr.highest_alert_level:
        level_score = {
            "critical": 50,
            "high": 30,
            "medium": 10,
            "low": 2,
        }.get(thr.highest_alert_level, 0)
        score += level_score
        factors.append(f"最高告警等级: {thr.highest_alert_level}")

    # 未关闭告警数（每个 +5，封顶 30）
    if thr.open_alerts > 0:
        score += min(30, thr.open_alerts * 5)
        factors.append(f"未关闭告警 {thr.open_alerts} 个")

    # 30 天事件数（每个 +10，封顶 40）
    if thr.recent_incident_count_30d > 0:
        score += min(40, thr.recent_incident_count_30d * 10)
        factors.append(f"30 天事件 {thr.recent_incident_count_30d}")

    # ATT&CK 技战术（每个 +10，封顶 20）
    if thr.attack_patterns:
        score += min(20, len(thr.attack_patterns) * 10)
        factors.append(f"ATT&CK 命中 {len(thr.attack_patterns)} 个技战术")

    score = max(0, min(100, score))
    if not data_gap and not factors:
        factors.append("近 30 天无活跃威胁")
    return DimensionScore(
        name="threat",
        raw_score=score,
        weight=AHS_DIMENSION_WEIGHTS["threat"],
        effective_weight=AHS_DIMENSION_WEIGHTS["threat"],
        data_gap=data_gap,
        contributing_factors=factors,
        evidence=list(thr.evidence),
    )


def _score_compliance(profile: AssetProfile) -> DimensionScore:
    """⑦ 合规维度（0-100，越高越差）。

    关键降级（主方案 §3.3 红线）：
    - 字段空 → 取中性值（不放大）
    - 合规数据全缺 → data_gap=True（重归一化跳过该维）
    """
    comp = profile.compliance
    factors: List[str] = []
    score = 0
    data_gap = not comp.evidence

    total_findings = (
        comp.compliance_pass_count
        + comp.compliance_fail_count
        + comp.compliance_unknown_count
    )

    if total_findings > 0:
        # 合规失败率 × 100
        fail_ratio = comp.compliance_fail_count / total_findings
        score += round(fail_ratio * 80)
        # unknown 也算风险
        unknown_ratio = comp.compliance_unknown_count / total_findings
        score += round(unknown_ratio * 20)
        factors.append(
            f"合规 pass={comp.compliance_pass_count} "
            f"fail={comp.compliance_fail_count} "
            f"unknown={comp.compliance_unknown_count}"
        )
    elif comp.data_classification:
        # 无合规 findings，但有数据分级（粗略估算：secret 80 / confidential 60 / internal 30 / public 10）
        cls_score = {
            "secret": 80,
            "confidential": 60,
            "internal": 30,
            "public": 10,
        }.get(comp.data_classification, 0)
        # 无 findings 时不放大（仅作提示）
        score += cls_score // 2  # 半权（无具体稽核结果时保守）
        factors.append(f"数据分级={comp.data_classification}（无具体稽核，半权）")

    score = max(0, min(100, score))
    if not data_gap and not factors:
        factors.append("合规数据全空，取中性值")
    return DimensionScore(
        name="compliance",
        raw_score=score,
        weight=AHS_DIMENSION_WEIGHTS["compliance"],
        effective_weight=AHS_DIMENSION_WEIGHTS["compliance"],
        data_gap=data_gap,
        contributing_factors=factors,
        evidence=list(comp.evidence),
    )


def _score_behavior(profile: AssetProfile) -> DimensionScore:
    """⑧ 行为维度（0-100，越高越差）。

    输入：BehaviorProfile 的 status / tags / layer_visit
    """
    beh = profile.behavior
    factors: List[str] = []
    score = 0
    data_gap = not beh.evidence

    # status=gap → 视为异常
    if beh.status == "gap":
        score += 30
        factors.append("behavior_status=gap（无行为数据）")

    # layer_visit 异常：ACT 占比过低（< 10%）→ 异常流量 / 横向活动多
    if beh.layer_visit:
        act_ratio = beh.layer_visit.get("ACT", 0.0)
        sys_ratio = beh.layer_visit.get("SYS", 0.0)
        ad_ratio = beh.layer_visit.get("AD", 0.0)
        if act_ratio < 0.1:
            score += 20
            factors.append(f"ACT 占比 {act_ratio:.2f} < 0.1（可疑）")
        # SYS 占比过高（> 60%）→ 系统访问多，可能为服务器（不是异常）
        # AD 占比过高（> 50%）→ 域控访问多，可能为域内机器（不扣分）

    # tags 命中敏感标签（如 "anomaly" / "scan" / "lateral" / "brute"）
    risky_tags = {"anomaly", "scan", "lateral", "brute", "exfil", "c2"}
    matched = [t for t in beh.tags if t.lower() in risky_tags]
    if matched:
        score += min(40, len(matched) * 15)
        factors.append(f"敏感标签: {', '.join(matched)}")

    score = max(0, min(100, score))
    if not data_gap and not factors:
        factors.append(f"行为正常（{beh.traffic_type or 'unknown'}）")
    return DimensionScore(
        name="behavior",
        raw_score=score,
        weight=AHS_DIMENSION_WEIGHTS["behavior"],
        effective_weight=AHS_DIMENSION_WEIGHTS["behavior"],
        data_gap=data_gap,
        contributing_factors=factors,
        evidence=list(beh.evidence),
    )


# ---------------------------------------------------------------------------
# 关键性系数
# ---------------------------------------------------------------------------

def compute_criticality_factor(profile: AssetProfile) -> float:
    """计算关键性系数（BIA × CIA × 等保 → 0.8~1.5）。

    主方案 §3.3：
        资产关键性系数 = f(业务影响, 数据敏感度, 等保等级)
                       = 三维加权（BIA 5 档 × CIA 5 档 × 等保 5 级）
                       范围 0.8 ~ 1.5

    降级（主方案红线）：
    - 业务影响空 → 取 1.00（中性，不放大）
    - 数据敏感度空 → 取 1.00
    - 等保等级空 → 取 1.00（与业务/数据维度"必须"作为合规兜底不同，等保可后置）

    返回值范围保护：[0.8, 1.5]
    """
    own = profile.ownership
    bia = CRITICALITY_FACTOR_BIA.get(own.business_impact, 1.00)
    cia = CRITICALITY_FACTOR_CIA.get(own.data_sensitivity, 1.00)
    prot = CRITICALITY_FACTOR_PROTECTION.get(own.protection_level, 1.00)
    factor = bia * cia * prot
    # 范围保护
    return round(max(0.8, min(1.5, factor)), 3)


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

# 至少 N 维有数据 → AHS 才有效（低于此 → state="insufficient_data"）
AHS_MIN_COVERED_DIMENSIONS = 3


def compute_ahs(profile: AssetProfile) -> AHSResult:
    """计算 AHS（资产健康分 0-100，越高越健康）。

    主方案 §3.3 公式：
        AHS = 100 - (exposure·w1 + vuln·w2 + threat·w3 + compliance·w4 + behavior·w5)
              × criticality_factor

    降级规则：
    1. 数据缺失维 → 重归一化（剩余维按比例放大）
    2. 等保/合规空 → 取中性值，不放大（主方案红线）
    3. 覆盖维 < AHS_MIN_COVERED_DIMENSIONS → state="insufficient_data"

    返回 AHSResult：score + state + criticality_factor + 5 个 DimensionScore + 证据合并
    """
    from datetime import datetime, timezone

    # 单维评分
    dim_scores = [
        _score_exposure(profile),
        _score_vulnerability(profile),
        _score_threat(profile),
        _score_compliance(profile),
        _score_behavior(profile),
    ]

    # 重归一化（数据缺维按 0.5 折 或 完全跳过）
    available_dims = [d for d in dim_scores if not d.data_gap]
    covered_count = len(available_dims)

    if covered_count == 0:
        # 全部缺数据 → 返回 50（中性）+ state="insufficient_data"
        return AHSResult(
            asset_id=profile.asset_id,
            score=50,
            state="insufficient_data",
            criticality_factor=1.0,
            dimensions=dim_scores,
            evidence=[],
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    # 状态判定
    if covered_count < AHS_MIN_COVERED_DIMENSIONS:
        state = "insufficient_data"
    else:
        state = "valid"

    # 有效权重（重归一化）
    total_w = sum(d.weight for d in available_dims)
    if total_w == 0:
        return AHSResult(
            asset_id=profile.asset_id,
            score=50,
            state="insufficient_data",
            criticality_factor=1.0,
            dimensions=dim_scores,
            evidence=[],
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    # 数据缺维有效权重折半（已 data_gap=True 的 dim 不在 available_dims）
    new_dims_list: list = []
    weighted_score = 0.0
    for d in dim_scores:
        if d.data_gap:
            new_dims_list.append(d)
            continue
        # 重归一化到总权重 = 1.0（让 sum effective_weight = 1）
        new_eff_w = d.weight / total_w
        new_d = DimensionScore(
            name=d.name,
            raw_score=d.raw_score,
            weight=d.weight,
            effective_weight=round(new_eff_w, 4),
            data_gap=d.data_gap,
            contributing_factors=d.contributing_factors,
            evidence=d.evidence,
        )
        new_dims_list.append(new_d)
        weighted_score += d.raw_score * new_eff_w

    dim_scores = new_dims_list

    # 关键性系数
    crit_factor = compute_criticality_factor(profile)

    # AHS = 100 - 加权扣分 × 关键性系数
    raw_ahs = 100 - weighted_score * crit_factor
    # 截断 [0, 100]
    final_score = max(0, min(100, round(raw_ahs)))

    # 合并 evidence（来自所有维度，按 source 去重）
    merged_evidence: List[EvidenceItem] = []
    seen_sources = set()
    for d in dim_scores:
        for ev in d.evidence:
            if ev.source in seen_sources:
                continue
            seen_sources.add(ev.source)
            merged_evidence.append(ev)

    return AHSResult(
        asset_id=profile.asset_id,
        score=final_score,
        state=state,
        criticality_factor=crit_factor,
        dimensions=dim_scores,
        evidence=merged_evidence,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# 与 AssetProfile 集成
# ---------------------------------------------------------------------------

def apply_ahs_to_profile(profile: AssetProfile, ahs_result: AHSResult) -> AssetProfile:
    """把 AHS 结果写回 AssetProfile（构造新对象，frozen 兼容）。

    OH-2.1 强约束：AssetProfile.frozen=True → 用 dataclasses.replace 构造新对象
    """
    import dataclasses

    return dataclasses.replace(
        profile,
        ahs_score=ahs_result.score,
        ahs_evidence=list(ahs_result.evidence),
        ahs_computed_at=_parse_iso(ahs_result.computed_at),
    )


def _parse_iso(s: Optional[str]):
    """ISO 8601 string → datetime（None-safe）。"""
    if not s:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None