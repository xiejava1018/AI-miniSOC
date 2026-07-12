"""
SCAP漏洞数据模拟器
用于测试和演示Wazuh集成功能
"""

import random
from typing import List, Dict, Any
from datetime import datetime, timedelta


class MockSCAPDataGenerator:
    """模拟SCAP漏洞数据生成器"""

    # 模拟CVE数据库
    CVE_DATABASE = [
        {
            "cve": "CVE-2024-1234",
            "title": "OpenSSH Remote Code Execution Vulnerability",
            "severity": "Critical",
            "cvss_score": 9.8,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "description": "OpenSSH before 9.8p1 contains a remote code execution vulnerability.",
            "published": "2024-12-20T00:00:00Z",
            "references": {
                "advisory": "https://www.openssh.com/txt/release-9.8",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-1234"
            },
            "affected_packages": ["openssh-server"],
            "fix": {"version": "1:9.8p1-1"},
            "has_exploit": True
        },
        {
            "cve": "CVE-2024-2345",
            "title": "Apache Tomcat HTTP Request Smuggling",
            "severity": "High",
            "cvss_score": 8.2,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:L",
            "description": "Apache Tomcat 10.1.0 to 10.1.20 does not properly validate HTTP requests.",
            "published": "2024-11-15T00:00:00Z",
            "references": {
                "advisory": "https://tomcat.apache.org/security-10.html",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-2345"
            },
            "affected_packages": ["tomcat10"],
            "fix": {"version": "10.1.20"},
            "has_exploit": True
        },
        {
            "cve": "CVE-2024-3456",
            "title": "OpenSSL Denial of Service",
            "severity": "Medium",
            "cvss_score": 5.3,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L",
            "description": "OpenSSL 3.0.0 to 3.1.1 contains a DoS vulnerability.",
            "published": "2024-10-10T00:00:00Z",
            "references": {
                "advisory": "https://www.openssl.org/news/secadv/20241010.txt",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-3456"
            },
            "affected_packages": ["openssl"],
            "fix": {"version": "3.1.2"},
            "has_exploit": False
        },
        {
            "cve": "CVE-2024-4567",
            "title": "nginx Information Disclosure",
            "severity": "Low",
            "cvss_score": 3.1,
            "cvss_vector": "CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N",
            "description": "nginx 1.25.0 may disclose sensitive information.",
            "published": "2024-09-05T00:00:00Z",
            "references": {
                "advisory": "https://nginx.org/en/security_advisories.html",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-4567"
            },
            "affected_packages": ["nginx"],
            "fix": {"version": "1.25.0"},
            "has_exploit": False
        },
        {
            "cve": "CVE-2024-5678",
            "title": "Linux Kernel Privilege Escalation",
            "severity": "High",
            "cvss_score": 7.8,
            "cvss_vector": "CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H",
            "description": "Linux kernel before 6.8.7 contains a privilege escalation vulnerability.",
            "published": "2024-11-20T00:00:00Z",
            "references": {
                "advisory": "https://kernel.org",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-5678"
            },
            "affected_packages": ["linux-image-generic"],
            "fix": {"version": "6.8.7"},
            "has_exploit": True
        },
        {
            "cve": "CVE-2024-6789",
            "title": "Python urllib3 URL Redirection",
            "severity": "Medium",
            "cvss_score": 5.0,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N",
            "description": "Python urllib3 before 2.0.7 does not properly validate URL redirects.",
            "published": "2024-08-15T00:00:00Z",
            "references": {
                "advisory": "https://github.com/urllib3/urllib3",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-6789"
            },
            "affected_packages": ["python3-urllib3"],
            "fix": {"version": "2.0.7-1build1"},
            "has_exploit": False
        },
        {
            "cve": "CVE-2024-7890",
            "title": "Systemd Local Privilege Escalation",
            "severity": "High",
            "cvss_score": 7.5,
            "cvss_vector": "CVSS:3.1/AV:L/AC:H/PR:L/UI:N/S:U/C:H/I:H/A:H",
            "description": "Systemd before v255 contains a local privilege escalation vulnerability.",
            "published": "2024-07-20T00:00:00Z",
            "references": {
                "advisory": "https://github.com/systemd/systemd",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-7890"
            },
            "affected_packages": ["systemd"],
            "fix": {"version": "255.4-1"},
            "has_exploit": True
        },
        {
            "cve": "CVE-2024-8901",
            "title": "SQLite Type Confusion",
            "severity": "Medium",
            "cvss_score": 6.5,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:H",
            "description": "SQLite before 3.45.0 contains a type confusion vulnerability.",
            "published": "2024-06-10T00:00:00Z",
            "references": {
                "advisory": "https://sqlite.org",
                "cve": "https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-8901"
            },
            "affected_packages": ["libsqlite3-0"],
            "fix": {"version": "3.45.0"},
            "has_exploit": False
        }
    ]

    @classmethod
    def generate_agent_vulnerabilities(
        cls,
        agent_id: str,
        count: int = None
    ) -> List[Dict[str, Any]]:
        """
        为指定agent生成模拟SCAP漏洞数据

        Args:
            agent_id: Agent ID
            count: 生成数量（随机如果未指定）

        Returns:
            模拟的漏洞数据列表
        """
        if count is None:
            count = random.randint(3, 8)

        # 随机选择CVE
        selected_cves = random.sample(cls.CVE_DATABASE, min(count, len(cls.CVE_DATABASE)))

        # 生成漏洞数据
        vulnerabilities = []
        now = datetime.utcnow()

        for cve in selected_cves:
            # 随机生成检测时间（最近30天内）
            days_ago = random.randint(1, 30)
            detected_at = now - timedelta(days=days_ago)

            vuln_data = {
                "cve": cve["cve"],
                "title": cve["title"],
                "severity": cve["severity"],
                "cvss_vector": cve["cvss_vector"],
                "description": cve["description"],
                "published": cve["published"],
                "references": cve["references"],
                "package": {
                    "name": random.choice(cve["affected_packages"]),
                    "version": f"{random.randint(1, 3)}.{random.randint(0, 9)}.{random.randint(0, 9)}"
                },
                "fix": cve["fix"],
                "detected_at": detected_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "agent_id": agent_id,
                "agent_name": f"agent-{agent_id}"
            }

            vulnerabilities.append(vuln_data)

        return vulnerabilities

    @classmethod
    def get_all_agents(cls) -> List[Dict[str, Any]]:
        """
        获取所有模拟agents

        Returns:
            Agent列表
        """
        return [
            {
                "id": "000",
                "name": "pve-ubuntu01",
                "ip": "127.0.0.1",
                "status": "active"
            },
            {
                "id": "001",
                "name": "fnos-vm-ubuntu01",
                "ip": "192.168.0.30",
                "status": "active"
            },
            {
                "id": "002",
                "name": "web-server-prod",
                "ip": "192.168.0.100",
                "status": "active"
            }
        ]

    @classmethod
    def generate_cve_stats(cls) -> Dict[str, int]:
        """
        生成CVE统计信息

        Returns:
            严重程度统计
        """
        return {
            "Critical": random.randint(0, 2),
            "High": random.randint(2, 5),
            "Medium": random.randint(3, 8),
            "Low": random.randint(1, 4)
        }
