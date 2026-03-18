-- ============================================================================
-- soc_asset_ports表结构检查脚本（本地执行版）
-- ============================================================================
-- 功能：检查soc_asset_ports表的当前结构
-- 使用方法：在数据库服务器上执行
-- ============================================================================

import subprocess
import os

PGHOST = '192.168.0.42'
PGPORT = '5432'
PGUSER = 'postgres'
PGPASSWORD = os.getenv('DB_PASSWORD', '<见环境变量配置>')
PGDATABASE = 'AI-miniSOC-db'

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

print("=" * 80)
print("🔍 检查soc_asset_ports表结构")
print("=" * 80)
print("")

# 1. 查看字段
print("📋 当前字段:")
print("-" * 80)
success, stdout, stderr = run_psql("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'soc_asset_ports'
    ORDER BY ordinal_position;
""")

if success:
    lines = stdout.strip().split('\n')
    for line in lines:
        if line.strip():
            parts = line.split('|')
            if len(parts) >= 2:
                print(f"   {parts[0].strip():<25} {parts[1].strip()}")
else:
    print(f"错误: {stderr}")

print("")

# 2. 查看索引
print("📇 当前索引:")
print("-" * 80)
success, stdout, stderr = run_psql("""
    SELECT indexname
    FROM pg_indexes
    WHERE tablename = 'soc_asset_ports'
    AND schemaname = 'public';
""")

if success:
    indexes = stdout.strip().split('\n')
    for idx in indexes:
        if idx.strip():
            print(f"   • {idx.strip()}")
else:
    print(f"错误: {stderr}")

print("")

# 3. 查看约束
print("🔒 当前约束:")
print("-" * 80)
success, stdout, stderr = run_psql("""
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'soc_asset_ports'::regclass;
""")

if success:
    constraints = stdout.strip().split('\n')
    for constr in constraints:
        if constr.strip():
            print(f"   • {constr.strip()}")
else:
    print(f"错误: {stderr}")

print("")
print("=" * 80)
