"""
数据转换器

将 Wazuh API 返回的数据转换为 AI-miniSOC 标准格式。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def convert_agent_to_asset(agent: dict) -> dict:
    """
    将 Wazuh agent 转换为资产格式

    Wazuh Agent 数据结构 (扁平格式):
    {
        "id": "000",
        "name": "agent-name",
        "ip": "x.x.x.x",
        "status": "active/disconnected/never_connected",
        "os": {"name": "Ubuntu", "version": "22.04"},
        "dateAdd": "2023-01-01T00:00:00Z"
    }
    """
    ip = agent.get("ip")
    name = agent.get("name")
    agent_id = agent.get("id")
    status = agent.get("status", "")

    if not ip or ip == "any":
        logger.debug(f"Agent {name} IP 无效，跳过: {ip}")
        return None

    # OS 信息
    os_obj = agent.get("os", {})
    os_name = os_obj.get("name", "Unknown")
    os_version = os_obj.get("version", "")

    # 网络区域判断
    network_zone = determine_network_zone(ip)

    # 状态映射
    asset_status = "online" if status == "active" else "offline"

    return {
        "asset_ip": ip,
        "name": name,
        "asset_status": asset_status,
        "os_name": os_name,
        "os_version": os_version,
        "network_segment": "default",
        "network_zone": network_zone,
        "asset_type": "server",
        "criticality": "normal",
        "data_source": "wazuh",
        "source_id": agent_id,
        "wazuh_agent_id": agent_id,
        "asset_description": f"Wazuh Agent - {os_name} {os_version}".strip(),
    }


def convert_vuln_to_asset_vulnerability(vuln: dict) -> dict:
    """
    将 Wazuh 漏洞转换为资产漏洞格式

    Wazuh 漏洞数据结构:
    {
        "agent_id": "001",
        "agent_name": "agent-name",
        "agent_ip": "x.x.x.x",
        "cve": {"id": "CVE-2023-1234", "description": "..."},
        "condition": {"status": "Fixed", "version": "1.0.0"},
        "severity": "High",
        "title": "...",
        "type": "Package"
    }
    """
    cve_obj = vuln.get("cve", {})
    condition = vuln.get("condition", {})
    severity = vuln.get("severity", "Unknown")

    return {
        "asset_ip": vuln.get("agent_ip"),
        "asset_name": vuln.get("agent_name"),
        "cve_id": cve_obj.get("id"),
        "vulnerability_name": vuln.get("title", cve_obj.get("id")),
        "severity": map_severity(severity),
        "description": cve_obj.get("description", ""),
        "status": "open" if condition.get("status") == "Fixed" else "resolved",
        "affected_component": vuln.get("type", "Unknown"),
        "affected_version": condition.get("version", ""),
        "fix_version": condition.get("condition", ""),
        "data_source": "wazuh",
        "source_id": f"{vuln.get('agent_id')}_{cve_obj.get('id')}",
        "published_date": vuln.get("published_date"),
        "cvss_score": vuln.get("cvss", {}).get("score"),
        "cvss_vector": vuln.get("cvss", {}).get("vector_string"),
    }


def convert_sca_to_baseline(sca: dict) -> dict:
    """
    将 Wazuh SCA 结果转换为基线检查格式

    Wazuh SCA 数据结构:
    {
        "agent_id": "001",
        "agent_name": "agent-name",
        "agent_ip": "x.x.x.x",
        "policy_id": "cis_rhel8_linux",
        "name": "CIS Benchmark for Red Hat Enterprise Linux 8",
        "description": "...",
        "checks": [...]
    }
    """
    # 提取检查项
    checks = sca.get("checks", {})
    check_results = []
    for check_id, check in checks.items():
        check_results.append({
            "check_id": check_id,
            "title": check.get("title", ""),
            "description": check.get("description", ""),
            "status": check.get("status", "Failed"),
            "reason": check.get("reason", ""),
        })

    return {
        "asset_ip": sca.get("agent_ip"),
        "asset_name": sca.get("agent_name"),
        "baseline_name": sca.get("name", sca.get("policy_id", "")),
        "baseline_type": "sca",
        "baseline_source": "wazuh",
        "description": sca.get("description", ""),
        "status": "passed" if sca.get("pass", 0) > 0 else "failed",
        "total_checks": sca.get("total_checks", 0),
        "failed_checks": sca.get("fail", 0),
        "passed_checks": sca.get("pass", 0),
        "score": calculate_score(sca.get("pass", 0), sca.get("total_checks", 1)),
        "data_source": "wazuh",
        "source_id": f"{sca.get('agent_id')}_{sca.get('policy_id')}",
        "check_results": check_results,
    }


def determine_network_zone(ip: str) -> str:
    """根据 IP 判断网络区域"""
    if ip.startswith("192.168.") or ip.startswith("10."):
        return "intranet"
    elif ip.startswith("172.16.") or ip.startswith("172.17.") or ip.startswith("172.18."):
        return "intranet"
    elif ip.startswith("8.") or ip.startswith("1.") or ip.startswith("114."):
        return "dmz"
    else:
        return "other"


def map_severity(severity: str) -> str:
    """映射 Wazuh 严重等级到 AI-miniSOC 格式"""
    severity_map = {
        "Critical": "critical",
        "High": "high",
        "Medium": "medium",
        "Low": "low",
        "Info": "low",
    }
    return severity_map.get(severity, "unknown")


def calculate_score(passed: int, total: int) -> float:
    """计算合规分数"""
    if total == 0:
        return 0.0
    return round((passed / total) * 100, 2)
