#!/usr/bin/env python3
"""TP-Link Collector 测试脚本"""

import asyncio
import sys
import os
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / "tplink_collector"))
sys.path.insert(0, str(Path(__file__).parent.parent / "base"))

from collector_framework.config import CollectorConfig
from collector_framework.sync_client import MiniSOCClient
from collector_framework.base import DataType
from tplink_collector.collector import TPLinkCollector

async def main():
    print("=" * 50)
    print("TP-Link Collector 测试")
    print("=" * 50)

    # 配置 - 从环境变量或默认值
    router_host = os.getenv("ROUTER_HOST", "192.168.0.1")
    router_user = os.getenv("ROUTER_USERNAME", "tploginadmin")
    router_pass = os.getenv("ROUTER_PASSWORD", "")  # 需要设置
    minisoc_url = os.getenv("MINISOC_URL", "http://localhost:8000")
    minisoc_key = os.getenv("MINISOC_API_KEY", "sk-minisoc-wazuh-test2024")

    if not router_pass:
        print("错误: 需要设置 ROUTER_PASSWORD 环境变量")
        print("示例: export ROUTER_PASSWORD='your_password'")
        return

    print(f"\n配置:")
    print(f"  路由器: {router_host}")
    print(f"  AI-miniSOC: {minisoc_url}")

    # 创建采集器
    collector = TPLinkCollector(
        host=router_host,
        username=router_user,
        password=router_pass,
    )

    # 1. 测试路由器连接
    print("\n1. 测试路由器连接...")
    router_ok = await collector.test_connection()
    print(f"   路由器: {'✓ 成功' if router_ok else '✗ 失败'}")

    if not router_ok:
        print("\n请检查:")
        print("  - ROUTER_PASSWORD 是否正确")
        print("  - 路由器是否在线")
        return

    # 2. 采集数据
    print("\n2. 采集在线设备...")
    result = await collector.collect(DataType.ASSET)
    print(f"   采集到 {len(result.items)} 台设备")

    # 显示前3条
    for i, item in enumerate(result.items[:3]):
        print(f"\n   设备 {i+1}:")
        print(f"     IP: {item.get('asset_ip')}")
        print(f"     MAC: {item.get('mac_address')}")
        print(f"     名称: {item.get('name')}")

    # 3. 同步到 AI-miniSOC
    print("\n3. 同步到 AI-miniSOC...")
    soc_client = MiniSOCClient(base_url=minisoc_url, api_key=minisoc_key)

    sync_result = await soc_client.sync(
        source=result.source,
        data_type=result.data_type.value,
        items=result.items,
    )
    print(f"   ✓ 同步成功!")
    print(f"   创建: {sync_result.get('created', 0)}")
    print(f"   更新: {sync_result.get('updated', 0)}")
    print(f"   跳过: {sync_result.get('skipped', 0)}")

    await soc_client.close()
    await collector.close()

    print("\n" + "=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())