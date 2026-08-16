"""
OpenSearch 统一字段映射层（P2-T1）

背景（v2 方案 §D）：
- `wazuh-states-vulnerabilities-*` 使用 ECS **顶层**结构：`vulnerability.id`、`vulnerability.severity`...
- `wazuh-alerts-4.x-*` 漏洞告警使用 `data.vulnerability.*` 嵌套结构
- 两源均为真实结构但路径不同，混用易静默取空值

本模块：抽离**统一逻辑字段**到两源物理路径的映射与取数函数，
所有 OS 查询/解析只走本层，禁止 `data.vulnerability.*` 与顶层混写。

用法：
    from app.services.opensearch.os_field_map import extract_vuln_fields, OSFieldProbe

    cve_id, severity, cvss = extract_vuln_fields(hit, source="states")
    cve_id, severity, cvss = extract_vuln_fields(hit, source="alerts")
"""
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 源类型与字段路径定义
# ─────────────────────────────────────────────────────────────────

# 两源的字段路径（实测 ECS 结构）
PATHS_STATES = {
    "cve_id": "vulnerability.id",
    "description": "vulnerability.description",
    "severity": "vulnerability.severity",
    "score": "vulnerability.score",
    "reference": "vulnerability.reference",
    "published_at": "vulnerability.published_at",
    "detected_at": "vulnerability.detected_at",
    "classification": "vulnerability.classification",
    "agent_id": "agent.id",
    "agent_name": "agent.name",
    "package_name": "package.name",
    "package_version": "package.version",
    "package_architecture": "package.architecture",
    "package_condition": "package.condition",
    "under_evaluation": "vulnerability.under_evaluation",
}

# alerts 索引路径（data.vulnerability.*）
PATHS_ALERTS = {
    "cve_id": "data.vulnerability.id",
    "description": "data.vulnerability.description",
    "severity": "data.vulnerability.severity",
    "score": "data.vulnerability.score",
    "reference": "data.vulnerability.reference",
    "published_at": "data.vulnerability.published_at",
    "detected_at": "@timestamp",  # alerts 用 @timestamp
    "classification": "data.vulnerability.classification",
    "agent_id": "agent.id",
    "agent_name": "agent.name",
    "package_name": "data.package.name",
    "package_version": "data.package.version",
    "package_architecture": "data.package.architecture",
    "package_condition": "data.package.condition",
    "under_evaluation": "data.vulnerability.under_evaluation",
}

PATHS_BY_SOURCE = {
    "states": PATHS_STATES,
    "alerts": PATHS_ALERTS,
}


def _get_path(source: str, logical_key: str) -> str:
    paths = PATHS_BY_SOURCE.get(source)
    if paths is None:
        raise ValueError(
            f"unknown OS source: {source!r}; expected one of {list(PATHS_BY_SOURCE)}"
        )
    if logical_key not in paths:
        raise KeyError(f"unknown logical field: {logical_key!r}")
    return paths[logical_key]


def _get_nested(obj: dict, dotted_path: str) -> Any:
    """按点分路径取值；任一段不存在返回 None（不抛）。"""
    cur: Any = obj
    for seg in dotted_path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
        if cur is None:
            return None
    return cur


# ─────────────────────────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OSVulnFields:
    """统一逻辑字段：vulnerability 一次提取，跨源同结构。"""
    cve_id: Optional[str]
    severity: Optional[str]
    cvss_score: Optional[float]
    description: Optional[str]
    references: Optional[list[str]]
    published_at: Optional[str]
    detected_at: Optional[str]
    agent_id: Optional[str]
    agent_name: Optional[str]
    package: Optional[dict]
    under_evaluation: Optional[bool]


def extract_vuln_fields(hit_source: dict, source: str) -> OSVulnFields:
    """从 OS hit._source 抽取统一逻辑字段。

    Args:
        hit_source: OS hit 的 _source dict
        source: 'states' 或 'alerts'

    Returns:
        OSVulnFields：所有字段都是 Optional，缺失时为 None
    """
    if not isinstance(hit_source, dict):
        return OSVulnFields(
            cve_id=None, severity=None, cvss_score=None, description=None,
            references=None, published_at=None, detected_at=None,
            agent_id=None, agent_name=None, package=None, under_evaluation=None,
        )

    def get(key: str) -> Any:
        return _get_nested(hit_source, _get_path(source, key))

    # 字段提取
    cve_id_raw = get("cve_id")
    cve_id = str(cve_id_raw).strip().upper() if cve_id_raw else None

    severity_raw = get("severity")
    severity = str(severity_raw).strip() if severity_raw else None

    score_raw = get("score")
    cvss_score = _parse_cvss(score_raw)

    description = get("description")
    if description:
        description = str(description).strip() or None

    references = _parse_reference(get("reference"))

    published_at = get("published_at")
    detected_at = get("detected_at")

    agent_id = get("agent_id")
    agent_name = get("agent_name")

    pkg_name = get("package_name")
    package = None
    if pkg_name:
        package = {
            "name": pkg_name,
            "version": get("package_version"),
            "architecture": get("package_architecture"),
            "condition": get("package_condition"),
        }

    under_evaluation = get("under_evaluation")
    if under_evaluation is not None:
        under_evaluation = bool(under_evaluation)

    return OSVulnFields(
        cve_id=cve_id,
        severity=severity,
        cvss_score=cvss_score,
        description=description,
        references=references,
        published_at=published_at,
        detected_at=detected_at,
        agent_id=agent_id,
        agent_name=agent_name,
        package=package,
        under_evaluation=under_evaluation,
    )


def _parse_cvss(score_field) -> Optional[float]:
    """嵌套 CVSS：实测 {"base": 5.9, "version": "3.1"}；兼容 {"base_score"} / 纯数字。"""
    if score_field is None:
        return None
    if isinstance(score_field, (int, float)):
        v = float(score_field)
        return v if 0.0 <= v <= 10.0 else None
    if isinstance(score_field, dict):
        for k in ("base", "base_score", "score", "value"):
            v = score_field.get(k)
            if isinstance(v, (int, float)):
                fv = float(v)
                if 0.0 <= fv <= 10.0:
                    return fv
    return None


def _parse_reference(ref_field) -> Optional[list[str]]:
    """reference 单数字符串（逗号分隔）→ 列表；兼容 list。"""
    if not ref_field:
        return None
    if isinstance(ref_field, list):
        items = [str(r).strip() for r in ref_field if r]
        return items or None
    if isinstance(ref_field, str):
        items = [u.strip() for u in ref_field.split(",") if u.strip()]
        return items or None
    return None


class OSFieldProbe:
    """字段存在性探针（P2-T1 验收：缺关键字段时告警而非静默取空）。

    用法：
        probe = OSFieldProbe()
        fields = extract_vuln_fields(hit, source="states")
        missing = probe.check(fields)
        if missing:
            logger.warning("OS hit 缺字段: %s", missing)
    """

    # 必须存在的关键字段（用于告警，不阻断业务）
    REQUIRED_FIELDS = ("cve_id", "severity")

    def check(self, fields: OSVulnFields) -> list[str]:
        """返回缺失的关键字段名列表。"""
        missing = []
        for k in self.REQUIRED_FIELDS:
            if getattr(fields, k) is None:
                missing.append(k)
        return missing

    def has_data_vulnerability_legacy(self, hit_source: dict) -> bool:
        """探针：检查 hit 是否使用了旧的 data.vulnerability.* 路径（混写违规）。

        任何 OS 解析点都不应再使用 data.vulnerability.*；本探针仅用于回归测试，
        确认调用方没绕过本映射层直接写死旧路径。
        """
        if not isinstance(hit_source, dict):
            return False
        return "data" in hit_source and isinstance(hit_source.get("data"), dict) and "vulnerability" in hit_source["data"]