#!/usr/bin/env python3
"""
Wazuh Collector 本地测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "base"))

from collector_framework.config import CollectorConfig
from wazuh_collector.collector import WazuhCollector


async def main():
    print("=" * 50)
    print("Wazuh Collector 本地测试")
    print("=" * 50)

    # 从环境变量获取配置
    import os
    minisoc_url = os.environ.get("MINISOC_URL", "http://localhost:8000")
    minisoc_api_key = os.environ.get("MINISOC_API_KEY", "sk-minisoc-wazuh-test2024")
    wazuh_url = os.environ.get("WAZUH_URL", "https://192.168.0.40:55000")
    wazuh_user = os.environ.get("WAZUH_USER", "wazuh")
    wazuh_password = os.environ.get("WAZUH_PASSWORD", "OgdHes6S57Y?L5HwU0dLB3tWtw.1.TUu")

    # 创建测试配置
    config = CollectorConfig(
        minisoc_url=minisoc_url,
        minisoc_api_key=minisoc_api_key,
        interval=300,
        collect_types=["asset"],
        once=True,
        extra={
            "wazuh": {
                "url": wazuh_url,
                "user": wazuh_user,
                "password": wazuh_password,
                "verify_ssl": False,
            }
        }
    )

    print(f"\n配置:")
    print(f"  AI-miniSOC: {minisoc_url}")
    print(f"  Wazuh: {wazuh_url}")

    # 创建采集器
    collector = WazuhCollector(config)

    # 测试连接
    print("\n1. 测试 Wazuh API 连接...")
    wazuh_ok = await collector.test_connection()
    print(f"   Wazuh API: {'✓ 成功' if wazuh_ok else '✗ 失败'}")

    if not wazuh_ok:
        print("\n请检查 Wazuh 配置:")
        print("  - URL 是否正确")
        print("  - 用户名密码是否正确")
        print("  - Wazuh API 服务是否运行")
        return

    # 测试采集资产
    print("\n2. 测试采集资产数据...")
    try:
        from collector_framework.base import DataType

        result = await collector.collect(DataType.ASSET)
        print(f"   采集到 {len(result.items)} 条资产")

        # 显示前 3 条
        for i, item in enumerate(result.items[:3]):
            print(f"\n   资产 {i + 1}:")
            print(f"     IP: {item.get('asset_ip')}")
            print(f"     名称: {item.get('name')}")
            print(f"     状态: {item.get('asset_status')}")
            print(f"     OS: {item.get('os_name')} {item.get('os_version')}")
            print(f"     data_source: {item.get('data_source')}")

    except Exception as e:
        print(f"   ✗ 采集失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 测试同步到 AI-miniSOC
    print("\n3. 测试同步到 AI-miniSOC...")
    try:
        sync_result = await collector.sync_client.sync(
            source=result.source,
            data_type=result.data_type.value,
            items=result.items[:3],  # 只同步前 3 条测试
        )
        print(f"   ✓ 同步成功: {sync_result}")
    except Exception as e:
        print(f"   ✗ 同步失败: {e}")
        import traceback
        traceback.print_exc()

    # 关闭连接
    await collector.close()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
