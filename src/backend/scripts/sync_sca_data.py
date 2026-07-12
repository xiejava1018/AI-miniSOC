#!/usr/bin/env python3
"""
临时脚本：同步Wazuh SCA数据到新表
"""
import os
import sys
import json

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def sync_sca_data():
    """同步SCA数据"""
    import requests
    import psycopg2
    from datetime import datetime
    from urllib.parse import urlparse

    # Wazuh API配置
    wazuh_api_url = "https://192.168.0.40:55000/api"
    wazuh_username = "wazuh"
    wazuh_password = "OgdHes6S57Y?L5HwU0dLB3tWtw.1.TUu"

    # 数据库配置
    db_host = "192.168.0.42"
    db_port = "5432"
    db_name = "AI-miniSOC-testdb"
    db_user = "postgres"
    db_password = "PostgreSQL@2026"

    # 获取Wazuh Token
    print("获取Wazuh Token...")
    auth_response = requests.post(
        f"{wazuh_api_url}/security/user/authenticate?raw=true",
        auth=(wazuh_username, wazuh_password),
        verify=False
    )
    token = auth_response.text
    headers = {"Authorization": f"Bearer {token}"}

    # 连接数据库
    print("连接数据库...")
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # 获取所有活跃agents
    print("获取所有agents...")
    agents_response = requests.get(
        f"{wazuh_api_url}/agents?limit=100",
        headers=headers,
        verify=False
    )
    agents = agents_response.json().get("data", {}).get("affected_items", [])

    active_agents = [a for a in agents if a.get("status") == "active"]
    print(f"找到 {len(active_agents)} 个活跃agents")

    stats = {
        "new_checks": 0,
        "new_results": 0,
        "updated_results": 0
    }

    for agent in active_agents:
        agent_id = agent.get("id")
        agent_name = agent.get("name")

        print(f"\n处理 Agent {agent_id} ({agent_name})...")

        # 获取资产ID
        cursor.execute(
            "SELECT id FROM soc_assets WHERE wazuh_agent_id = %s",
            (agent_id,)
        )
        asset_row = cursor.fetchone()

        if not asset_row:
            print(f"  跳过：资产不存在")
            continue

        asset_id = asset_row[0]

        # 获取SCA策略
        sca_response = requests.get(
            f"{wazuh_api_url}/sca/{agent_id}?limit=10",
            headers=headers,
            verify=False
        )
        policies = sca_response.json().get("data", {}).get("affected_items", [])

        for policy in policies:
            policy_id = policy.get("policy_id")
            policy_name = policy.get("name")
            end_scan = policy.get("end_scan")

            if not policy_id:
                continue

            print(f"  处理策略 {policy_id}...")

            # 获取检查项
            checks_response = requests.get(
                f"{wazuh_api_url}/sca/{agent_id}/checks/{policy_id}?limit=1000",
                headers=headers,
                verify=False
            )
            checks = checks_response.json().get("data", {}).get("affected_items", [])

            print(f"    找到 {len(checks)} 个检查项")

            for check in checks:
                check_id = check.get("id")
                if not check_id:
                    continue

                # 创建或更新检查项定义
                cursor.execute(
                    """
                    INSERT INTO soc_sca_checks (check_id, policy_id, title, description, rationale, remediation, compliance, rules, condition, command, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (check_id, policy_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        rationale = EXCLUDED.rationale,
                        remediation = EXCLUDED.remediation,
                        compliance = EXCLUDED.compliance,
                        rules = EXCLUDED.rules,
                        condition = EXCLUDED.condition,
                        command = EXCLUDED.command,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        check_id,
                        policy_id,
                        check.get("title", "")[:500],
                        check.get("description", ""),
                        check.get("rationale", ""),
                        check.get("remediation", ""),
                        json.dumps(check.get("compliance", [])),
                        json.dumps(check.get("rules", [])),
                        check.get("condition"),
                        check.get("command"),
                        datetime.now(),
                        datetime.now()
                    )
                )

                sca_check_id = cursor.fetchone()[0]

                # 创建或更新资产检查结果
                check_result = check.get("result", "not applicable")

                cursor.execute(
                    """
                    INSERT INTO soc_asset_sca_checks (asset_id, sca_check_id, result, reason, status, last_scan_time, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (asset_id, sca_check_id) DO UPDATE SET
                        result = EXCLUDED.result,
                        reason = EXCLUDED.reason,
                        last_scan_time = EXCLUDED.last_scan_time,
                        updated_at = NOW()
                    """,
                    (
                        asset_id,
                        sca_check_id,
                        check_result,
                        check.get("reason", ""),
                        "open",
                        end_scan or datetime.now(),
                        datetime.now(),
                        datetime.now()
                    )
                )

                stats["new_results"] += 1

    # 统计结果
    print("\n=== 同步完成 ===")
    print(f"新检查项: {stats['new_checks']}")
    print(f"新结果: {stats['new_results']}")
    print(f"更新结果: {stats['updated_results']}")

    # 查询最终统计
    cursor.execute("SELECT COUNT(*) FROM soc_sca_checks")
    total_checks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM soc_asset_sca_checks")
    total_results = cursor.fetchone()[0]

    cursor.execute("""
        SELECT result, COUNT(*)
        FROM soc_asset_sca_checks
        GROUP BY result
        ORDER BY result
    """)
    result_stats = cursor.fetchall()

    print(f"\n=== 数据库统计 ===")
    print(f"总检查项: {total_checks}")
    print(f"总检查结果: {total_results}")
    print("\n按结果统计:")
    for result, count in result_stats:
        print(f"  {result}: {count}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    try:
        sync_sca_data()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
