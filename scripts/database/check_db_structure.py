#!/usr/bin/env python3
"""
检查数据库中的表结构
"""

import subprocess
import os

PGHOST = '192.168.0.42'
PGPORT = '5432'
PGUSER = 'postgres'
PGDATABASE = 'AI-miniSOC-db'
PGPASSWORD = os.getenv('DB_PASSWORD', '<见环境变量配置>')

def run_psql(sql):
    """运行SQL命令"""
    env = os.environ.copy()
    env['PGPASSWORD'] = PGPASSWORD

    try:
        result = subprocess.run(
            ['psql', '-h', PGHOST, '-p', PGPORT, '-U', PGUSER, '-d', PGDATABASE,
             '-c', sql, '-t', '-A'],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

print("=" * 70)
print("🔍 检查数据库表结构")
print("=" * 70)
print(f"📍 数据库: {PGHOST}:{PGPORT}/{PGDATABASE}")
print("")

# 1. 查看所有表
print("📊 数据库中的所有表:")
print("-" * 70)

success, stdout, stderr = run_psql("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
""")

if success:
    tables = [t.strip() for t in stdout.strip().split('\n') if t.strip()]
    if tables:
        for table in tables:
            print(f"   • {table}")
    else:
        print("   (空)")
else:
    print(f"❌ 查询失败: {stderr}")
    exit(1)

print("")

# 2. 如果有表，查看其中一个的结构
if tables:
    # 查找最可能的主表
    main_table = None
    for table in tables:
        if 'asset' in table.lower() or 'soc' in table.lower():
            main_table = table
            break

    if not main_table:
        main_table = tables[0]

    print(f"📋 {main_table} 表结构:")
    print("-" * 70)

    success, stdout, stderr = run_psql(f"""
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable
        FROM information_schema.columns
        WHERE table_name = '{main_table}'
        ORDER BY ordinal_position;
    """)

    if success:
        lines = stdout.strip().split('\n')
        print(f"{'字段名':<25} {'类型':<20} {'可空':<8}")
        print("-" * 70)
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 4:
                col_name = parts[0].strip()
                data_type = parts[1].strip()
                nullable = parts[3].strip()
                if col_name:
                    max_length = parts[2].strip() if parts[2].strip() else ''
                    if max_length:
                        data_type += f'({max_length})'
                    print(f"{col_name:<25} {data_type:<20} {nullable:<8}")
    else:
        print(f"❌ 查询失败: {stderr}")

print("\n" + "=" * 70)
