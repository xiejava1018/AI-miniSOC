#!/usr/bin/env python3
"""
模拟 Wazuh 数据同步测试

直接测试 AI-miniSOC 的数据同步端点，绕过 Wazuh API 认证。
"""

import requests
import json

MINISOC_URL = "http://localhost:8000"
API_KEY = "sk-minisoc-wazuh-test2024"

# 模拟 Wazuh agent 数据
wazuh_assets = [
    {
        "asset_ip": "192.168.0.100",
        "name": "wazuh-agent-test-001",
        "asset_status": "online",
        "asset_type": "server",
        "mac_address": "00:11:22:33:44:55",
        "network_zone": "intranet",
        "network_segment": "default",
        "os_name": "Ubuntu Linux",
        "os_version": "24.04 LTS",
        "data_source": "wazuh",
        "source_id": "001",
        "wazuh_agent_id": "001",
        "criticality": "normal",
        "asset_description": "Test Wazuh Agent - Ubuntu 24.04",
        "data_classification": "internal",
    },
    {
        "asset_ip": "192.168.0.101",
        "name": "wazuh-agent-test-002",
        "asset_status": "active",
        "asset_type": "workstation",
        "mac_address": "00:11:22:33:44:66",
        "network_zone": "office",
        "network_segment": "default",
        "os_name": "Windows",
        "os_version": "11 Pro",
        "data_source": "wazuh",
        "source_id": "002",
        "wazuh_agent_id": "002",
        "criticality": "normal",
        "asset_description": "Test Wazuh Agent - Windows 11",
        "data_classification": "internal",
    },
    {
        "asset_ip": "192.168.0.102",
        "name": "wazuh-agent-centos-003",
        "asset_status": "online",
        "asset_type": "server",
        "mac_address": "00:11:22:33:44:77",
        "network_zone": "dmz",
        "network_segment": "default",
        "os_name": "CentOS Linux",
        "os_version": "7.9",
        "data_source": "wazuh",
        "source_id": "003",
        "wazuh_agent_id": "003",
        "criticality": "high",
        "asset_description": "Test Wazuh Agent - CentOS 7.9",
        "data_classification": "confidential",
    },
]

def test_sync():
    print("=" * 60)
    print("模拟 Wazuh 数据同步测试")
    print("=" * 60)

    url = f"{MINISOC_URL}/api/v1/data/sync"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    print(f"\n目标 URL: {url}")
    print(f"API Key: {API_KEY}")

    # 构建同步请求
    payload = {
        "source": "wazuh",
        "data_type": "asset",
        "items": wazuh_assets,
    }

    print(f"\n发送 {len(wazuh_assets)} 条资产数据...")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()

        print(f"\n✓ 同步成功!")
        print(f"\n响应:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 验证结果
        if result.get("code") == 200:
            data = result.get("data", {})
            print(f"\n统计:")
            print(f"  总计: {data.get('total', 0)}")
            print(f"  创建: {data.get('created', 0)}")
            print(f"  更新: {data.get('updated', 0)}")
            print(f"  跳过: {data.get('skipped', 0)}")
            print(f"  失败: {data.get('failed', 0)}")

            if data.get("errors"):
                print(f"\n错误:")
                for err in data.get("errors", []):
                    print(f"  - {err}")
        else:
            print(f"\n✗ 同步失败: {result.get('msg')}")

        return result

    except requests.exceptions.RequestException as e:
        print(f"\n✗ 请求失败: {e}")
        return None


def verify_assets():
    """验证资产是否正确同步"""
    print("\n" + "=" * 60)
    print("验证同步结果")
    print("=" * 60)

    # 获取 token
    login_url = f"{MINISOC_URL}/api/v1/auth/login"
    login_data = {"username": "admin", "password": "admin123"}

    try:
        resp = requests.post(login_url, json=login_data, timeout=10)
        resp.raise_for_status()
        token = resp.json().get("data", {}).get("access_token")

        if not token:
            print("✗ 无法获取认证令牌")
            return

        # 查询 wazuh 数据源的资产
        assets_url = f"{MINISOC_URL}/api/v1/assets?data_source=wazuh&limit=10"
        headers = {"Authorization": f"Bearer {token}"}

        resp = requests.get(assets_url, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        items = result.get("data", {}).get("items", [])

        print(f"\n找到 {len(items)} 条 data_source='wazuh' 的资产:")

        for item in items:
            print(f"\n  IP: {item.get('asset_ip')}")
            print(f"  名称: {item.get('name')}")
            print(f"  状态: {item.get('asset_status')}")
            print(f"  OS: {item.get('os_name')} {item.get('os_version')}")
            print(f"  data_source: {item.get('data_source')}")
            print(f"  wazuh_agent_id: {item.get('wazuh_agent_id')}")

    except requests.exceptions.RequestException as e:
        print(f"\n✗ 验证失败: {e}")


if __name__ == "__main__":
    # 测试同步
    test_sync()

    # 验证结果
    verify_assets()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
