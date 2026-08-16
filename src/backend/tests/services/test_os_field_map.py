"""P2-T1：OpenSearch 统一字段映射层单测"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.opensearch.os_field_map import (
    extract_vuln_fields,
    OSFieldProbe,
    PATHS_STATES,
    PATHS_ALERTS,
)


# ──────────────── states 索引样本（顶层结构）────────────────

STATES_HIT_TOP = {
    "agent": {"id": "001", "name": "host-a"},
    "vulnerability": {
        "id": "CVE-2024-1234",
        "description": "Test vulnerability in OpenSSL",
        "severity": "High",
        "score": {"base": 7.5, "version": "3.1"},
        "reference": "https://example.com/cve,https://nvd.nist.gov/cve-2024-1234",
        "published_at": "2024-03-15T12:00:00Z",
        "detected_at": "2026-06-15T08:30:00Z",
    },
    "package": {
        "name": "openssl",
        "version": "1.1.1k",
        "architecture": "x86_64",
    },
}


# ──────────────── alerts 索引样本（data.vulnerability.*）────────────

ALERTS_HIT_TOP = {
    "agent": {"id": "002", "name": "host-b"},
    "data": {
        "vulnerability": {
            "id": "CVE-2024-5678",
            "description": "Test vulnerability in curl",
            "severity": "Critical",
            "score": {"base": 9.8},
            "reference": "https://curl.se/cve",
            "published_at": "2024-01-10T00:00:00Z",
        },
        "package": {
            "name": "curl",
            "version": "7.81.0",
            "architecture": "amd64",
        },
    },
    "@timestamp": "2026-06-15T09:00:00Z",
}


def test_extract_states_basic_fields():
    """states 索引：所有顶层字段均能取到。"""
    f = extract_vuln_fields(STATES_HIT_TOP, source="states")
    assert f.cve_id == "CVE-2024-1234"
    assert f.severity == "High"
    assert f.cvss_score == 7.5
    assert f.description == "Test vulnerability in OpenSSL"
    assert f.agent_id == "001"
    assert f.agent_name == "host-a"
    assert f.package == {
        "name": "openssl", "version": "1.1.1k", "architecture": "x86_64", "condition": None,
    }


def test_extract_alerts_data_dotted_path():
    """alerts 索引：data.vulnerability.* 与 data.package.* 均能取到。"""
    f = extract_vuln_fields(ALERTS_HIT_TOP, source="alerts")
    assert f.cve_id == "CVE-2024-5678"
    assert f.severity == "Critical"
    assert f.cvss_score == 9.8
    assert f.agent_id == "002"
    assert f.package == {
        "name": "curl", "version": "7.81.0", "architecture": "amd64", "condition": None,
    }
    # alerts 用 @timestamp 作 detected_at
    assert f.detected_at == "2026-06-15T09:00:00Z"


def test_cve_id_normalized_to_uppercase():
    """CVE 编号统一大写（避免 unique 约束大小写重复）。"""
    f = extract_vuln_fields(
        {"vulnerability": {"id": "cve-2024-9999", "severity": "Low"}},
        source="states",
    )
    assert f.cve_id == "CVE-2024-9999"


def test_cvss_invalid_range_returns_none():
    """CVSS 越界值（>10 / <0）应返回 None。"""
    f = extract_vuln_fields(
        {"vulnerability": {"id": "CVE-X", "severity": "Low", "score": {"base": 15.0}}},
        source="states",
    )
    assert f.cvss_score is None


def test_reference_string_split_to_list():
    """reference 单数字符串逗号分隔 → 列表。"""
    f = extract_vuln_fields(
        {"vulnerability": {"id": "CVE-X", "severity": "Low", "reference": "a.com,b.com"}},
        source="states",
    )
    assert f.references == ["a.com", "b.com"]


def test_reference_list_passthrough():
    """reference 已是 list 时直接透传。"""
    f = extract_vuln_fields(
        {"vulnerability": {"id": "CVE-X", "severity": "Low", "reference": ["a.com"]}},
        source="states",
    )
    assert f.references == ["a.com"]


def test_missing_fields_return_none():
    """关键字段缺失时返回 None（非抛错），由探针告警。"""
    f = extract_vuln_fields({"vulnerability": {}}, source="states")
    assert f.cve_id is None
    assert f.severity is None
    assert f.cvss_score is None


def test_field_probe_detects_missing_required():
    """OSFieldProbe 能识别缺失的关键字段。"""
    probe = OSFieldProbe()
    fields = extract_vuln_fields({"vulnerability": {"id": "CVE-X"}}, source="states")
    missing = probe.check(fields)
    assert "severity" in missing
    assert "cve_id" not in missing


def test_field_probe_detects_legacy_data_dotted_path():
    """探针：旧 data.vulnerability.* 路径视为违规。"""
    probe = OSFieldProbe()
    assert probe.has_data_vulnerability_legacy(ALERTS_HIT_TOP) is True
    assert probe.has_data_vulnerability_legacy(STATES_HIT_TOP) is False


def test_invalid_source_raises():
    """未知 source 应报错（防止上层写错路径）。"""
    try:
        extract_vuln_fields({}, source="bogus")
        assert False, "should raise"
    except ValueError:
        pass


def test_paths_have_same_keys():
    """两源路径字典必须字段对齐（漏字段会致双源取数不一致）。"""
    assert set(PATHS_STATES.keys()) == set(PATHS_ALERTS.keys())