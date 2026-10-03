"""资产八维画像 + AHS 数据模型（OH-2.1）

设计依据：
- 主方案 §3.2 八维画像数据模型（伪代码）
- 实施方案 OH-2.1（8 dataclass + profile_confidence）
- 实施方案 OH-2.2 AHS（输入八维画像，输出 0-100 + evidence[]；与 asset_risk.py 并存不替换）

【强约束】
1. **类型纯净**：本模块只定义 dataclass + 纯计算函数；ORM 装载逻辑放 loaders/ 子包
   （便于在脚本/CI 里直接构造画像快照）
2. **frozen=True**：所有画像 dataclass 不可变，避免下游误改导致 AHS 失真
3. **EvidenceItem 全统一**：每维装载都产出 evidence；evidence 含 source + observed_at + confidence
   （与本体 §axiom axiom-persistent-vs-observable 呼应：可解释可审计）
4. **profile_confidence 算法固定**：覆盖维度越多 + 证据越新 → 越高；最高 1.0
5. **AHS 仅占位**：本任务（OH-2.1）只画框，公式由 OH-2.2 落实；AHS = 0 + evidence 空不报错

【单测覆盖（OH-2.5 §测试）】
- 8 dataclass 实例化
- profile_confidence 三档（0/部分/全）
- missing_dimensions 统计
- CoverageInfo 加权
- to_dict 可序列化（dict / JSON safe）
- 跨维度组合空值兜底
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 证据项（八维共用）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """单个证据项。"""

    source: str            # e.g. "soc_assets", "soc_behavior_profiles", "ai_query"
    observed_at: datetime  # 证据观测时间（数据采集时刻）
    confidence: float      # 0-1，本证据的可信度
    reference: Optional[str] = None  # 行号 / commit / doc 引用
    note: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"EvidenceItem.confidence must be in [0, 1], got {self.confidence}"
            )


# ---------------------------------------------------------------------------
# 八维 dataclass（所有字段均有默认，便于 empty_profile 兜底）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssetIdentity:
    """① 身份维 — 多源 ID + 置信度。

    数据来源：soc_assets + soc_identity_bindings + soc_identity_events
    """

    source_id: Optional[str] = None                # soc_assets.source_id
    data_source: Optional[str] = None              # soc_assets.data_source: manual/wazuh/tplink-router/...
    wazuh_agent_id: Optional[str] = None           # soc_assets.wazuh_agent_id
    mac_address: Optional[str] = None              # soc_assets.mac_address
    hostname: Optional[str] = None                 # 派生自 soc_assets.name 或 soc_identity_bindings.hostname
    identity_confidence: float = 0.0               # 0-1，来自 IdentityBinding fusion_confidence
    identity_bindings_count: int = 0               # soc_identity_bindings 行数
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetOwnership:
    """② 归属维 — 责任人 / 业务影响 / 业务系统。

    数据来源：soc_assets + soc_asset_business + soc_business_systems + soc_users
    """

    owner: Optional[str] = None                    # soc_assets.owner（自由文本）
    owner_contact: Optional[str] = None            # soc_assets.owner_contact
    business_unit: Optional[str] = None            # soc_assets.business_unit
    business_impact: Optional[str] = None          # 5 档 core/important/normal/auxiliary/ignorable
    data_sensitivity: Optional[str] = None         # 5 档 extreme/high/medium/low/negligible
    protection_level: Optional[str] = None         # 5 档 level_5..level_1
    business_systems: List[str] = field(default_factory=list)  # 业务系统 name 列表
    business_system_codes: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetTechnology:
    """③ 技术维 — OS / 硬件 / 端口 / 组件（SBOM 占位）。

    数据来源：soc_assets + soc_asset_ports + 后续 OH-2.1 SBOM 表
    """

    os_name: Optional[str] = None
    os_version: Optional[str] = None
    hardware_info: Dict[str, Any] = field(default_factory=dict)
    open_ports_count: int = 0                      # open 状态端口数
    services: List[str] = field(default_factory=list)  # 去重后的 service 名
    components: List[str] = field(default_factory=list)  # SBOM 占位（OH-2.1 SBOM 表）
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetExposure:
    """④ 暴露维 — public_ip / exposure_level / NAT 推导（OH-3.4）/ 7 天探测（占位）。

    数据来源：soc_assets + soc_asset_ports + 图谱 maps_to 边
    """

    public_ip: Optional[str] = None
    exposure_level: Optional[str] = None           # public/internal/isolated
    nat_mapped_internal_ips: List[str] = field(default_factory=list)  # 来自 maps_to 边
    exposed_ports: List[int] = field(default_factory=list)            # public_ip 上的端口
    wan_ip: Optional[str] = None                    # WAN IP（来自 TP-Link NAT 表，由 OH-3.4 填充）
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetVulnerability:
    """⑤ 脆弱维 — risk_score + 漏洞列表 + 健康分明细。

    数据来源：soc_assets.risk_score + soc_assets.score_breakdown + soc_asset_vulnerabilities + soc_vulnerabilities
    """

    risk_score: Optional[int] = None               # soc_assets.risk_score（0-100）
    risk_summary: Optional[str] = None
    risk_scored_at: Optional[datetime] = None
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    vuln_total: int = 0
    vuln_by_severity: Dict[str, int] = field(default_factory=dict)   # critical/high/medium/low
    unfixed_high_count: int = 0
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetThreat:
    """⑥ 威胁维 — 告警 + 事件 + ATT&CK 映射（OH-4.4 占位）。

    数据来源：soc_asset_incidents + soc_incidents + soc_alerts + ATT&CK feed（OH-4.4）
    """

    open_alerts: int = 0
    highest_alert_level: Optional[str] = None      # critical/high/medium/low
    recent_incident_count_30d: int = 0
    attack_patterns: List[str] = field(default_factory=list)  # ATT&CK technique id 列表
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetCompliance:
    """⑦ 合规维 — 等保 + 合规稽核结果。

    数据来源：soc_assets + soc_compliance_findings（最新 run）+ criticality.py
    """

    data_classification: Optional[str] = None     # public/internal/confidential/secret
    compliance_pass_count: int = 0
    compliance_fail_count: int = 0
    compliance_unknown_count: int = 0
    last_compliance_run_at: Optional[datetime] = None
    ruleset_version: Optional[str] = None
    evidence: List[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class AssetBehavior:
    """⑧ 行为维 — 行为画像特征。

    数据来源：soc_behavior_profiles（最近 profile_date 一行）
    """

    profile_date: Optional[str] = None             # YYYY-MM-DD
    traffic_type: Optional[str] = None             # human/machine/mixed
    status: Optional[str] = None                   # ok/gap
    total_visits: int = 0
    top_domain_count: int = 0                      # top_domains 数组长度
    tags: List[str] = field(default_factory=list)  # 画像标签名
    layer_visit: Dict[str, float] = field(default_factory=dict)  # ACT/SYS/AD 占比
    evidence: List[EvidenceItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 汇总：八维画像 + AHS 框架
# ---------------------------------------------------------------------------


# 八维枚举（避免 loader 用错顺序）
DIMENSIONS = (
    "identity", "ownership", "technology", "exposure",
    "vulnerability", "threat", "compliance", "behavior",
)


@dataclass(frozen=True)
class CoverageInfo:
    """画像覆盖度统计。"""

    total_dimensions: int = 8
    covered_dimensions: int = 0          # 非 None 维数
    missing_dimensions: List[str] = field(default_factory=list)
    coverage_ratio: float = 0.0          # covered / total


@dataclass(frozen=True)
class AssetProfile:
    """八维画像汇总。

    AHS 字段占位：OH-2.2 落实计算公式；OH-2.1 只画框。
    """

    asset_id: str
    identity: AssetIdentity = field(default_factory=AssetIdentity)
    ownership: AssetOwnership = field(default_factory=AssetOwnership)
    technology: AssetTechnology = field(default_factory=AssetTechnology)
    exposure: AssetExposure = field(default_factory=AssetExposure)
    vulnerability: AssetVulnerability = field(default_factory=AssetVulnerability)
    threat: AssetThreat = field(default_factory=AssetThreat)
    compliance: AssetCompliance = field(default_factory=AssetCompliance)
    behavior: AssetBehavior = field(default_factory=AssetBehavior)

    # AHS 占位（OH-2.2 落实公式）
    ahs_score: int = 0                   # 0-100
    ahs_evidence: List[EvidenceItem] = field(default_factory=list)
    ahs_computed_at: Optional[datetime] = None

    # 画像可信度
    profile_confidence: float = 0.0      # 0-1
    coverage: CoverageInfo = field(default_factory=CoverageInfo)
    built_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 纯计算函数
# ---------------------------------------------------------------------------


def compute_coverage(profile: AssetProfile) -> CoverageInfo:
    """统计画像覆盖度（覆盖维度 / 总维度）。"""
    dim_objects = {
        "identity": profile.identity,
        "ownership": profile.ownership,
        "technology": profile.technology,
        "exposure": profile.exposure,
        "vulnerability": profile.vulnerability,
        "threat": profile.threat,
        "compliance": profile.compliance,
        "behavior": profile.behavior,
    }
    missing: List[str] = []
    covered = 0
    for name, obj in dim_objects.items():
        # 维度"有数据"判定：evidence 非空 + 至少一个核心字段非空
        if _has_meaningful_data(name, obj):
            covered += 1
        else:
            missing.append(name)
    ratio = covered / len(DIMENSIONS) if DIMENSIONS else 0.0
    return CoverageInfo(
        total_dimensions=len(DIMENSIONS),
        covered_dimensions=covered,
        missing_dimensions=missing,
        coverage_ratio=round(ratio, 4),
    )


def _has_meaningful_data(dim_name: str, dim_obj: Any) -> bool:
    """判断单维是否有"有意义数据"。

    规则（按主方案 §3.1 现状表）：
    - identity：identity_confidence > 0 或任一 ID 字段非空
    - ownership：owner 或任一业务字段非空
    - technology：os_name 或 open_ports_count > 0 或 services 非空
    - exposure：public_ip 或 exposure_level 非空
    - vulnerability：risk_score 非空 或 vuln_total > 0
    - threat：open_alerts > 0 或 recent_incident_count_30d > 0
    - compliance：data_classification 非空 或 compliance_findings 三态至少一个 > 0
    - behavior：profile_date 非空
    """
    if not dim_obj.evidence:
        return False
    if dim_name == "identity":
        return bool(
            dim_obj.identity_confidence > 0
            or dim_obj.source_id
            or dim_obj.wazuh_agent_id
            or dim_obj.mac_address
        )
    if dim_name == "ownership":
        return bool(
            dim_obj.owner
            or dim_obj.business_unit
            or dim_obj.business_impact
            or dim_obj.business_systems
        )
    if dim_name == "technology":
        return bool(
            dim_obj.os_name
            or dim_obj.open_ports_count > 0
            or dim_obj.services
        )
    if dim_name == "exposure":
        return bool(dim_obj.public_ip or dim_obj.exposure_level)
    if dim_name == "vulnerability":
        return bool(dim_obj.risk_score is not None or dim_obj.vuln_total > 0)
    if dim_name == "threat":
        return bool(dim_obj.open_alerts > 0 or dim_obj.recent_incident_count_30d > 0)
    if dim_name == "compliance":
        return bool(
            dim_obj.data_classification
            or dim_obj.compliance_pass_count > 0
            or dim_obj.compliance_fail_count > 0
            or dim_obj.compliance_unknown_count > 0
        )
    if dim_name == "behavior":
        return bool(dim_obj.profile_date)
    return False


def compute_profile_confidence(profile: AssetProfile) -> float:
    """画像可信度 = 覆盖维度的 evidence confidence 均值 × coverage 权重。

    公式（OH-2.1 §profile_confidence）：
        conf = coverage_ratio × (Σ dim_avg_confidence / covered_dimensions)
    说明：
    - coverage 兜底：覆盖维度越多，整体可信度越高
    - evidence confidence 均值兜底：单维数据来源越多越新，分数越高
    - 范围 [0, 1]
    """
    cov = profile.coverage
    if cov.covered_dimensions == 0:
        return 0.0
    dim_objects = (
        profile.identity, profile.ownership, profile.technology, profile.exposure,
        profile.vulnerability, profile.threat, profile.compliance, profile.behavior,
    )
    dim_avg_sum = 0.0
    counted = 0
    for dim in dim_objects:
        if not dim.evidence:
            continue
        conf_values = [e.confidence for e in dim.evidence if 0.0 <= e.confidence <= 1.0]
        if conf_values:
            dim_avg_sum += sum(conf_values) / len(conf_values)
            counted += 1
    if counted == 0:
        return round(cov.coverage_ratio * 0.5, 4)  # 覆盖但无证据 → 给 0.5 折
    dim_avg = dim_avg_sum / counted
    return round(cov.coverage_ratio * dim_avg, 4)


# ---------------------------------------------------------------------------
# 序列化辅助（前端 / API 用）
# ---------------------------------------------------------------------------


def profile_to_dict(profile: AssetProfile) -> Dict[str, Any]:
    """画像 → dict（JSON-safe，可直接 envelope 返回）。

    datetime → ISO 8601 string；其余 dataclass 走 asdict。
    """
    raw = asdict(profile)
    return _normalize_jsonable(raw)


def _normalize_jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _normalize_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize_jsonable(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# 工厂函数（默认空画像）
# ---------------------------------------------------------------------------


def empty_profile(asset_id: str) -> AssetProfile:
    """构造一帧空画像（8 维全空 + 0 覆盖）。用于 loader 失败兜底。"""
    return AssetProfile(asset_id=asset_id)
