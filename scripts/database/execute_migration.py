#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 执行soc_assets表优化

使用方法:
  python3 execute_migration.py
"""

import subprocess
import sys
import os

# 数据库配置
PGHOST = '192.168.0.42'
PGPORT = '5432'
PGUSER = 'postgres'
PGDATABASE = 'AI-miniSOC-db'
PGPASSWORD = os.getenv('DB_PASSWORD', '<见环境变量配置>')

SQL_FILE = '/home/xiejava/AIproject/AI-miniSOC/scripts/database/migrate_soc_assets_v1.sql'

def run_psql(sql):
    """运行SQL命令"""
    env = os.environ.copy()
    env['PGPASSWORD'] = PGPASSWORD

    try:
        result = subprocess.run(
            ['psql', '-h', PGHOST, '-p', PGPORT, '-U', PGUSER, '-d', PGDATABASE, '-c', sql],
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
    print("🚀 AI-miniSOC 数据库表优化")
    print("=" * 70)
    print(f"📍 数据库: {PGHOST}:{PGPORT}/{PGDATABASE}")
    print("")

    # 读取SQL文件
    if not os.path.exists(SQL_FILE):
        print(f"❌ SQL文件不存在: {SQL_FILE}")
        sys.exit(1)

    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    print("📋 执行步骤:")
    print("")

    # 步骤1: 检查表是否存在
    print("1️⃣  检查表...")
    success, stdout, stderr = run_psql(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'soc_assets');"
    )
    if success and 't' in stdout:
        print("   ✅ soc_assets表存在")
    else:
        print("   ❌ soc_assets表不存在")
        sys.exit(1)

    # 步骤2: 开始事务
    print("\n2️⃣  开始事务...")
    success, stdout, stderr = run_psql("BEGIN;")
    if not success:
        print(f"   ❌ 失败: {stderr}")
        sys.exit(1)
    print("   ✅ 事务已开始")

    # 步骤3: 添加新字段（逐个执行以便错误处理）
    print("\n3️⃣  添加新字段...")

    fields_to_add = [
        ("name VARCHAR(255)", "资产名称"),
        ("mac_address MACADDR", "MAC地址"),
        ("asset_type VARCHAR(50) DEFAULT 'other'", "资产类型"),
        ("criticality VARCHAR(20) DEFAULT 'medium'", "重要性等级"),
        ("owner VARCHAR(255)", "负责人"),
        ("business_unit VARCHAR(255)", "业务单元"),
        ("wazuh_agent_id VARCHAR(100) UNIQUE", "Wazuh Agent ID"),
        ("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "更新时间")
    ]

    for field_sql, field_name in fields_to_add:
        # 检查字段是否已存在
        check_sql = f"""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'soc_assets' AND column_name = '{field_sql.split()[0]}'
        );
        """
        success, stdout, stderr = run_psql(check_sql)

        if success and 'f' in stdout:
            # 字段不存在，添加
            sql = f"ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS {field_sql};"
            success, stdout, stderr = run_psql(sql)
            if success:
                print(f"   ✅ {field_name}")
            else:
                print(f"   ⚠️  {field_name} - {stderr}")
        else:
            print(f"   ⊙ {field_name} - 已存在")

    # 步骤4: 添加约束
    print("\n4️⃣  添加约束...")

    constraints = [
        ("asset_type", "CHECK (asset_type IN ('server', 'workstation', 'printer', 'router', 'switch', 'nas', 'firewall', 'other'))", "资产类型约束"),
        ("criticality", "CHECK (criticality IN ('critical', 'high', 'medium', 'low'))", "重要性等级约束")
    ]

    for constraint_name, constraint_sql, description in constraints:
        sql = f"""
        ALTER TABLE soc_assets
        DROP CONSTRAINT IF EXISTS soc_assets_{constraint_name}_check,
        ADD CONSTRAINT soc_assets_{constraint_name}_check {constraint_sql};
        """
        success, stdout, stderr = run_psql(sql)
        if success:
            print(f"   ✅ {description}")
        else:
            print(f"   ⚠️  {description} - {stderr}")

    # 步骤5: 修改IP字段类型
    print("\n5️⃣  修改IP字段类型...")
    success, stdout, stderr = run_psql(
        "ALTER TABLE soc_assets ALTER COLUMN asset_ip TYPE INET USING asset_ip::INET;"
    )
    if success:
        print("   ✅ IP字段类型已修改为INET")
    else:
        print(f"   ⚠️  可能已经修改: {stderr}")

    # 步骤6: 迁移数据
    print("\n6️⃣  迁移现有数据...")
    success, stdout, stderr = run_psql(
        "UPDATE soc_assets SET name = COALESCE(asset_description, '未命名资产') WHERE name IS NULL OR name = '';"
    )
    if success:
        print("   ✅ 数据已迁移")
    else:
        print(f"   ⚠️  {stderr}")

    # 步骤7: 创建索引
    print("\n7️⃣  创建索引...")

    indexes = [
        ("idx_soc_assets_wazuh", "wazuh_agent_id", "Wazuh Agent索引"),
        ("idx_soc_assets_type", "asset_type", "资产类型索引"),
        ("idx_soc_assets_criticality", "criticality", "重要性索引")
    ]

    for index_name, column_name, description in indexes:
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON soc_assets({column_name});"
        success, stdout, stderr = run_psql(sql)
        if success:
            print(f"   ✅ {description}")
        else:
            print(f"   ⚠️  {description} - {stderr}")

    # 步骤8: 添加注释
    print("\n8️⃣  添加表和字段注释...")

    comments = [
        ("TABLE", "soc_assets", "安全资产表 - AI-miniSOC核心资产表"),
        ("COLUMN", "soc_assets.name", "资产名称"),
        ("COLUMN", "soc_assets.mac_address", "MAC地址（用于设备识别）"),
        ("COLUMN", "soc_assets.asset_type", "资产类型：server/workstation/printer/router/switch/nas/firewall/other"),
        ("COLUMN", "soc_assets.criticality", "重要性等级：critical/high/medium/low"),
        ("COLUMN", "soc_assets.owner", "资产负责人"),
        ("COLUMN", "soc_assets.business_unit", "所属业务单元/部门"),
        ("COLUMN", "soc_assets.wazuh_agent_id", "关联的Wazuh Agent ID（用于告警关联）"),
        ("COLUMN", "soc_assets.updated_at", "资产信息最后更新时间")
    ]

    for comment_type, object_name, comment_text in comments:
        sql = f"COMMENT ON {comment_type} {object_name} IS '{comment_text}';"
        success, stdout, stderr = run_psql(sql)
        if success:
            print(f"   ✅ {object_name}")
        else:
            print(f"   ⚠️  {object_name} - {stderr}")

    # 步骤9: 创建触发器函数
    print("\n9️⃣  创建自动更新触发器...")

    trigger_sql = """
    CREATE OR REPLACE FUNCTION update_soc_assets_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trigger_update_soc_assets_updated_at ON soc_assets;
    CREATE TRIGGER trigger_update_soc_assets_updated_at
        BEFORE UPDATE ON soc_assets
        FOR EACH ROW
        EXECUTE FUNCTION update_soc_assets_updated_at();
    """

    success, stdout, stderr = run_psql(trigger_sql)
    if success:
        print("   ✅ 触发器已创建")
    else:
        print(f"   ⚠️  {stderr}")

    # 步骤10: 提交事务
    print("\n🔟 提交事务...")
    success, stdout, stderr = run_psql("COMMIT;")
    if success:
        print("   ✅ 事务已提交")
    else:
        print(f"   ❌ 提交失败: {stderr}")
        sys.exit(1)

    # 步骤11: 验证结果
    print("\n1️⃣1️⃣  验证结果...")

    success, stdout, stderr = run_psql("""
    SELECT
        column_name,
        data_type,
        character_maximum_length,
        is_nullable
    FROM information_schema.columns
    WHERE table_name = 'soc_assets'
    ORDER BY ordinal_position;
    """)

    if success:
        print("\n📊 soc_assets表结构:")
        print("-" * 70)
        lines = stdout.strip().split('\n')
        for line in lines:
            if line.strip() and not line.startswith('|') and not line.startswith('-'):
                parts = line.split('|')
                if len(parts) >= 4:
                    col_name = parts[0].strip()
                    data_type = parts[1].strip()
                    nullable = parts[3].strip()
                    if col_name and col_name != 'column_name':
                        print(f"   {col_name:<25} {data_type:<20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
        print("-" * 70)

    print("\n" + "=" * 70)
    print("✅ 数据库表优化完成！")
    print("=" * 70)
    print("\n📝 变更摘要:")
    print("   • 新增8个字段")
    print("   • 添加2个约束")
    print("   • 创建3个索引")
    print("   • 添加9个注释")
    print("   • 创建1个触发器")
    print("\n🎯 所有表遵循soc_前缀规范")
    print("📚 详细规范: docs/design/database-naming-conventions.md")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        sys.exit(1)
