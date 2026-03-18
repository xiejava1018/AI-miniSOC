#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 使用subprocess调用psql

依赖：系统需要安装psql客户端
"""

import subprocess
import os
import sys
from pathlib import Path

# 添加network-scan目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'skills' / 'network-scan'))

# 导入网络扫描脚本的配置加载函数
from network_scan_unified import load_config

def run_psql(sql):
    """运行SQL命令 - 从network_scan脚本借用"""
    config = load_config()

    env = os.environ.copy()
    env['PGPASSWORD'] = config['PGPASSWORD']

    try:
        result = subprocess.run(
            ['psql', '-h', config['PGHOST'], '-p', config['PGPORT'],
             '-U', config['PGUSER'], '-d', config['PGDATABASE'],
             '-c', sql],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    print("=" * 70)
    print("🔍 AI-miniSOC 数据库检查")
    print("=" * 70)
    print("")

    # 测试数据库连接
    print("1️⃣  测试数据库连接...")
    success, stdout, stderr = run_psql("SELECT version();")
    if success:
        print("   ✅ 数据库连接成功")
        version = stdout.split('\n')[0].strip()
        print(f"   📌 {version[:50]}...")
    else:
        print(f"   ❌ 数据库连接失败")
        print(f"   错误: {stderr}")
        print("\n💡 请确保:")
        print("   1. PostgreSQL服务器可访问")
        print("   2. psql客户端已安装")
        print("   3. .env文件配置正确")
        sys.exit(1)

    # 查看所有表
    print("\n2️⃣  查看所有表...")
    success, stdout, stderr = run_psql("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)

    if success:
        tables = [t.strip() for t in stdout.strip().split('\n') if t.strip() and t.strip() != 'table_name']
        if tables:
            print(f"   发现 {len(tables)} 个表:")
            for table in tables:
                print(f"      • {table}")
        else:
            print("   📭 数据库为空，没有表")
            print("\n💡 建议先运行网络扫描脚本创建表:")
            print("   cd skills/network-scan")
            print("   python3 network_scan_unified.py")
    else:
        print(f"   ❌ 查询失败: {stderr}")

    print("\n" + "=" * 70)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
