#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 - 纯Python实现（使用psycopg2）

功能：
1. 检查数据库连接
2. 查看现有表结构
3. 创建或更新soc_assets表
4. 添加新字段和约束
5. 创建索引和触发器

依赖：pip install psycopg2-binary
"""

import sys
import os
from datetime import datetime

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.0.42'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'AI-miniSOC-db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '<见环境变量配置>')
}

def check_psycopg2():
    """检查psycopg2是否安装"""
    try:
        import psycopg2
        import psycopg2.extras
        return True
    except ImportError:
        return False

def install_psycopg2():
    """安装psycopg2"""
    print("📦 正在安装 psycopg2-binary...")
    os.system('pip3 install psycopg2-binary -q')
    return check_psycopg2()

def get_connection():
    """获取数据库连接"""
    import psycopg2
    conn = psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    return conn

def check_tables(cursor):
    """检查现有表"""
    print("\n📊 检查现有表...")

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)

    tables = [row[0] for row in cursor.fetchall()]

    if tables:
        print(f"   发现 {len(tables)} 个表:")
        for table in tables:
            print(f"      • {table}")
    else:
        print("   📭 数据库为空")

    return tables

def create_soc_assets_table(cursor):
    """创建soc_assets表（如果不存在）"""
    print("\n🔨 创建soc_assets表...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS soc_assets (
            id TEXT PRIMARY KEY,
            asset_ip INET UNIQUE NOT NULL,
            name VARCHAR(255),
            asset_description TEXT,
            mac_address MACADDR,
            asset_type VARCHAR(50) DEFAULT 'other',
            criticality VARCHAR(20) DEFAULT 'medium',
            owner VARCHAR(255),
            business_unit VARCHAR(255),
            asset_status VARCHAR(20) DEFAULT '离线',
            wazuh_agent_id VARCHAR(100) UNIQUE,
            status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT soc_assets_asset_type_check
                CHECK (asset_type IN ('server', 'workstation', 'printer', 'router', 'switch', 'nas', 'firewall', 'other')),

            CONSTRAINT soc_assets_criticality_check
                CHECK (criticality IN ('critical', 'high', 'medium', 'low'))
        );
    """)

    print("   ✅ soc_assets表已创建")

def add_missing_columns(cursor):
    """添加缺失的列"""
    print("\n➕ 检查并添加缺失字段...")

    # 获取现有列
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'soc_assets';
    """)
    existing_columns = {row[0] for row in cursor.fetchall()}

    # 需要添加的列
    columns_to_add = {
        'name': 'VARCHAR(255)',
        'mac_address': 'MACADDR',
        'asset_type': "VARCHAR(50) DEFAULT 'other'",
        'criticality': "VARCHAR(20) DEFAULT 'medium'",
        'owner': 'VARCHAR(255)',
        'business_unit': 'VARCHAR(255)',
        'wazuh_agent_id': 'VARCHAR(100) UNIQUE',
        'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
    }

    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            sql = f"ALTER TABLE soc_assets ADD COLUMN {col_name} {col_def};"
            cursor.execute(sql)
            print(f"   ✅ 添加字段: {col_name}")
        else:
            print(f"   ⊙ 字段已存在: {col_name}")

def create_indexes(cursor):
    """创建索引"""
    print("\n📇 创建索引...")

    indexes = [
        ("idx_soc_assets_ip", "asset_ip"),
        ("idx_soc_assets_wazuh", "wazuh_agent_id"),
        ("idx_soc_assets_type", "asset_type"),
        ("idx_soc_assets_criticality", "criticality"),
        ("idx_soc_assets_status", "asset_status")
    ]

    for index_name, column_name in indexes:
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT FROM pg_indexes
                WHERE tablename = 'soc_assets' AND indexname = '{index_name}'
            );
        """)

        exists = cursor.fetchone()[0]

        if not exists:
            cursor.execute(f"CREATE INDEX {index_name} ON soc_assets({column_name});")
            print(f"   ✅ 创建索引: {index_name}")
        else:
            print(f"   ⊙ 索引已存在: {index_name}")

def create_trigger(cursor):
    """创建更新时间戳触发器"""
    print("\n⚙️  创建自动更新触发器...")

    # 创建函数
    cursor.execute("""
        CREATE OR REPLACE FUNCTION update_soc_assets_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 创建触发器
    cursor.execute("""
        DROP TRIGGER IF EXISTS trigger_update_soc_assets_updated_at ON soc_assets;
        CREATE TRIGGER trigger_update_soc_assets_updated_at
            BEFORE UPDATE ON soc_assets
            FOR EACH ROW
            EXECUTE FUNCTION update_soc_assets_updated_at();
    """)

    print("   ✅ 触发器已创建")

def add_comments(cursor):
    """添加注释"""
    print("\n📝 添加表和字段注释...")

    comments = [
        ("TABLE", "soc_assets", "安全资产表 - AI-miniSOC核心资产表"),
        ("COLUMN", "soc_assets.id", "资产唯一标识（UUID格式）"),
        ("COLUMN", "soc_assets.asset_ip", "资产IP地址（INET类型）"),
        ("COLUMN", "soc_assets.name", "资产名称"),
        ("COLUMN", "soc_assets.asset_description", "资产描述"),
        ("COLUMN", "soc_assets.mac_address", "MAC地址"),
        ("COLUMN", "soc_assets.asset_type", "资产类型"),
        ("COLUMN", "soc_assets.criticality", "重要性等级"),
        ("COLUMN", "soc_assets.owner", "资产负责人"),
        ("COLUMN", "soc_assets.business_unit", "所属业务单元"),
        ("COLUMN", "soc_assets.asset_status", "在线状态"),
        ("COLUMN", "soc_assets.wazuh_agent_id", "关联的Wazuh Agent ID"),
        ("COLUMN", "soc_assets.updated_at", "最后更新时间")
    ]

    for comment_type, object_name, comment_text in comments:
        sql = f"COMMENT ON {comment_type} {object_name} IS '{comment_text}';"
        cursor.execute(sql)

    print(f"   ✅ 已添加 {len(comments)} 条注释")

def show_table_structure(cursor):
    """显示表结构"""
    print("\n📋 soc_assets表结构:")
    print("=" * 80)

    cursor.execute("""
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = 'soc_assets'
        ORDER BY ordinal_position;
    """)

    columns = cursor.fetchall()

    print(f"{'字段名':<25} {'类型':<20} {'可空':<8} {'默认值':<20}")
    print("-" * 80)

    for col in columns:
        col_name = col[0]
        data_type = col[1]
        max_len = col[2]
        nullable = col[3]
        default = str(col[4]) if col[4] else ""

        if max_len:
            data_type += f"({max_len})"

        nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
        default_str = default[:20]

        print(f"{col_name:<25} {data_type:<20} {nullable_str:<8} {default_str:<20}")

    print("=" * 80)

def main():
    print("=" * 80)
    print("🚀 AI-miniSOC 数据库初始化/迁移")
    print("=" * 80)
    print(f"📍 数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print(f"👤 用户: {DB_CONFIG['user']}")
    print("")

    # 检查psycopg2
    if not check_psycopg2():
        print("⚠️  psycopg2未安装，正在安装...")
        if not install_psycopg2():
            print("❌ 无法安装psycopg2，请手动安装: pip3 install psycopg2-binary")
            sys.exit(1)

    import psycopg2

    try:
        # 连接数据库
        print("🔗 连接数据库...")
        conn = get_connection()
        cursor = conn.cursor()
        print("   ✅ 连接成功")

        # 检查现有表
        tables = check_tables(cursor)

        # 创建或更新soc_assets表
        if 'soc_assets' in tables:
            print("\n✨ soc_assets表已存在，执行更新...")
            add_missing_columns(cursor)
        else:
            create_soc_assets_table(cursor)

        # 创建索引
        create_indexes(cursor)

        # 创建触发器
        create_trigger(cursor)

        # 添加注释
        add_comments(cursor)

        # 提交事务
        conn.commit()

        # 显示表结构
        show_table_structure(cursor)

        print("\n" + "=" * 80)
        print("✅ 数据库初始化/迁移完成！")
        print("=" * 80)
        print("\n📝 变更摘要:")
        print("   • soc_assets表已创建/更新")
        print("   • 13个字段")
        print("   • 5个索引")
        print("   • 2个约束")
        print("   • 1个触发器")
        print("\n🎯 所有表遵循soc_前缀规范")
        print("📚 详细规范: docs/design/database-naming-conventions.md")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  操作已取消")
        sys.exit(1)
