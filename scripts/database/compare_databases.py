#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库差异对比工具 - 比较AI-miniSOC-db和AI-miniSOC-testdb的结构差异
生成Bytebase兼容的迁移脚本
"""

import subprocess
import sys
import os
from typing import Dict, List, Tuple, Set
from datetime import datetime

# 数据库配置
PGHOST = '192.168.0.42'
PGPORT = '5432'
PGUSER = 'postgres'
PGPASSWORD = os.getenv('DB_PASSWORD', '<见环境变量配置>')

SOURCE_DB = 'AI-miniSOC-db'      # 源数据库（生产/主数据库）
TARGET_DB = 'AI-miniSOC-testdb'  # 目标数据库（测试数据库）

class DatabaseComparator:
    """数据库结构对比器"""

    def __init__(self, host: str, port: str, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def run_psql(self, database: str, sql: str) -> Tuple[bool, str, str]:
        """运行SQL命令"""
        env = os.environ.copy()
        env['PGPASSWORD'] = self.password

        try:
            result = subprocess.run(
                ['psql', '-h', self.host, '-p', self.port, '-U', self.user,
                 '-d', database, '-c', sql, '-t', '-A'],
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)

    def get_tables(self, database: str) -> Set[str]:
        """获取数据库所有表"""
        success, stdout, stderr = self.run_psql(database, """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)

        if success:
            return set(t.strip() for t in stdout.strip().split('\n') if t.strip())
        return set()

    def get_table_columns(self, database: str, table: str) -> Dict[str, Dict]:
        """获取表的所有列信息"""
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)

        columns = {}
        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 8:
                    col_name = parts[0].strip()
                    data_type = parts[1].strip()
                    max_length = parts[2].strip() if parts[2].strip() else None
                    precision = parts[3].strip() if parts[3].strip() else None
                    scale = parts[4].strip() if parts[4].strip() else None

                    # 构建完整类型
                    full_type = data_type
                    if max_length:
                        full_type = f"{data_type}({max_length})"
                    elif precision and scale:
                        full_type = f"{data_type}({precision},{scale})"
                    elif precision:
                        full_type = f"{data_type}({precision})"

                    columns[col_name] = {
                        'name': col_name,
                        'type': data_type,
                        'full_type': full_type,
                        'max_length': max_length,
                        'precision': precision,
                        'scale': scale,
                        'nullable': parts[5].strip() == 'YES',
                        'default': parts[6].strip() if parts[6].strip() else None,
                        'position': int(parts[7].strip())
                    }
        return columns

    def get_table_constraints(self, database: str, table: str) -> Dict[str, Dict]:
        """获取表的约束信息（非主键）"""
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                con.conname AS constraint_name,
                con.contype AS constraint_type,
                pg_get_constraintdef(con.oid) AS constraint_definition
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = '{table}'
              AND con.contype IN ('c', 'f', 'u')  -- CHECK, FOREIGN KEY, UNIQUE
            ORDER BY con.contype, con.conname;
        """)

        constraints = {}
        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    name = parts[0].strip()
                    constraint_type = parts[1].strip()
                    definition = parts[2].strip()

                    constraints[name] = {
                        'name': name,
                        'type': 'CHECK' if constraint_type == 'c' else ('FOREIGN KEY' if constraint_type == 'f' else 'UNIQUE'),
                        'definition': definition
                    }
        return constraints

    def get_table_indexes(self, database: str, table: str) -> Dict[str, Dict]:
        """获取表的索引信息（非主键索引）"""
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                i.relname AS index_name,
                a.attname AS column_name,
                ix.indisunique AS is_unique,
                am.amname AS index_type,
                ix.indkey::text AS indkey
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = '{table}'
              AND NOT ix.indisprimary
            ORDER BY i.relname, a.attnum;
        """)

        indexes = {}
        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 5:
                    name = parts[0].strip()
                    if name not in indexes:
                        indexes[name] = {
                            'name': name,
                            'columns': [],
                            'unique': parts[2].strip() == 't',
                            'type': parts[3].strip()
                        }
                    indexes[name]['columns'].append(parts[1].strip())
        return indexes

    def get_table_comments(self, database: str, table: str) -> Dict[str, str]:
        """获取表和列的注释"""
        comments = {}

        # 获取表注释
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT obj_description('{table}'::regclass, 'pg_class') AS table_comment;
        """)

        if success and stdout.strip():
            comments['table'] = stdout.strip()

        # 获取列注释
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                a.attname AS column_name,
                pg_catalog.col_description(a.attrelid, a.attnum) AS comment
            FROM pg_attribute a
            WHERE a.attrelid = '{table}'::regclass
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND pg_catalog.col_description(a.attrelid, a.attnum) IS NOT NULL;
        """)

        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 2:
                    col_name = parts[0].strip()
                    comment = parts[1].strip()
                    if comment:
                        comments[f'column:{col_name}'] = comment

        return comments

    def get_table_triggers(self, database: str, table: str) -> Dict[str, Dict]:
        """获取表的触发器信息"""
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                t.tgname AS trigger_name,
                p.proname AS function_name,
                pg_get_triggerdef(t.oid) AS trigger_definition
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_proc p ON p.oid = t.tgfoid
            WHERE c.relname = '{table}'
              AND NOT t.tgisinternal
            ORDER BY t.tgname;
        """)

        triggers = {}
        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|')
                if len(parts) >= 3:
                    name = parts[0].strip()
                    triggers[name] = {
                        'name': name,
                        'function': parts[1].strip(),
                        'definition': parts[2].strip()
                    }
        return triggers

    def get_table_functions(self, database: str) -> Dict[str, str]:
        """获取数据库中的自定义函数"""
        success, stdout, stderr = self.run_psql(database, f"""
            SELECT
                p.proname AS function_name,
                pg_get_functiondef(p.oid) AS function_definition
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
            ORDER BY p.proname;
        """)

        functions = {}
        if success:
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|', 1)
                if len(parts) >= 2:
                    name = parts[0].strip()
                    # 合并剩余部分（因为定义中可能包含|）
                    definition = '|'.join(parts[1:])
                    functions[name] = definition
        return functions

    def compare_databases(self) -> Dict:
        """比较两个数据库的结构差异"""
        print("🔍 开始比较数据库结构...")
        print(f"📍 源数据库: {SOURCE_DB}")
        print(f"📍 目标数据库: {TARGET_DB}")
        print()

        differences = {
            'tables_only_in_source': [],
            'tables_only_in_target': [],
            'table_differences': {},
            'functions_only_in_source': [],
            'functions_only_in_target': []
        }

        # 比较表
        print("📊 比较表列表...")
        source_tables = self.get_tables(SOURCE_DB)
        target_tables = self.get_tables(TARGET_DB)

        differences['tables_only_in_source'] = sorted(source_tables - target_tables)
        differences['tables_only_in_target'] = sorted(target_tables - source_tables)

        common_tables = source_tables & target_tables
        print(f"   • 源数据库独有表: {len(differences['tables_only_in_source'])}")
        print(f"   • 目标数据库独有表: {len(differences['tables_only_in_target'])}")
        print(f"   • 共同表: {len(common_tables)}")
        print()

        # 比较函数
        print("📊 比较自定义函数...")
        source_functions = self.get_table_functions(SOURCE_DB)
        target_functions = self.get_table_functions(TARGET_DB)

        differences['functions_only_in_source'] = sorted(set(source_functions.keys()) - set(target_functions.keys()))
        differences['functions_only_in_target'] = sorted(set(target_functions.keys()) - set(source_functions.keys()))

        print(f"   • 源数据库独有函数: {len(differences['functions_only_in_source'])}")
        print(f"   • 目标数据库独有函数: {len(differences['functions_only_in_target'])}")
        print()

        # 比较每个共同表的结构
        print("🔍 比较共同表的结构...")
        for table in sorted(common_tables):
            table_diff = {
                'columns_only_in_source': [],
                'columns_only_in_target': [],
                'column_type_diffs': [],
                'column_nullable_diffs': [],
                'column_default_diffs': [],
                'constraints_only_in_source': [],
                'constraints_only_in_target': [],
                'indexes_only_in_source': [],
                'indexes_only_in_target': [],
                'triggers_only_in_source': [],
                'triggers_only_in_target': [],
                'comments_diff': []
            }

            # 比较列
            source_columns = self.get_table_columns(SOURCE_DB, table)
            target_columns = self.get_table_columns(TARGET_DB, table)

            source_col_names = set(source_columns.keys())
            target_col_names = set(target_columns.keys())

            table_diff['columns_only_in_source'] = sorted(source_col_names - target_col_names)
            table_diff['columns_only_in_target'] = sorted(target_col_names - source_col_names)

            # 比较列属性
            for col in source_col_names & target_col_names:
                src_col = source_columns[col]
                tgt_col = target_columns[col]

                # 比较数据类型
                if src_col['full_type'] != tgt_col['full_type']:
                    table_diff['column_type_diffs'].append({
                        'column': col,
                        'source_type': src_col['full_type'],
                        'target_type': tgt_col['full_type']
                    })

                # 比较可空性
                if src_col['nullable'] != tgt_col['nullable']:
                    table_diff['column_nullable_diffs'].append({
                        'column': col,
                        'source_nullable': src_col['nullable'],
                        'target_nullable': tgt_col['nullable']
                    })

                # 比较默认值
                src_default = src_col['default'] or ''
                tgt_default = tgt_col['default'] or ''
                if src_default != tgt_default:
                    table_diff['column_default_diffs'].append({
                        'column': col,
                        'source_default': src_default,
                        'target_default': tgt_default
                    })

            # 比较约束
            source_constraints = self.get_table_constraints(SOURCE_DB, table)
            target_constraints = self.get_table_constraints(TARGET_DB, table)

            table_diff['constraints_only_in_source'] = sorted(
                set(source_constraints.keys()) - set(target_constraints.keys())
            )
            table_diff['constraints_only_in_target'] = sorted(
                set(target_constraints.keys()) - set(source_constraints.keys())
            )

            # 比较索引
            source_indexes = self.get_table_indexes(SOURCE_DB, table)
            target_indexes = self.get_table_indexes(TARGET_DB, table)

            table_diff['indexes_only_in_source'] = sorted(
                set(source_indexes.keys()) - set(target_indexes.keys())
            )
            table_diff['indexes_only_in_target'] = sorted(
                set(target_indexes.keys()) - set(source_indexes.keys())
            )

            # 比较触发器
            source_triggers = self.get_table_triggers(SOURCE_DB, table)
            target_triggers = self.get_table_triggers(TARGET_DB, table)

            table_diff['triggers_only_in_source'] = sorted(
                set(source_triggers.keys()) - set(target_triggers.keys())
            )
            table_diff['triggers_only_in_target'] = sorted(
                set(target_triggers.keys()) - set(source_triggers.keys())
            )

            # 比较注释
            source_comments = self.get_table_comments(SOURCE_DB, table)
            target_comments = self.get_table_comments(TARGET_DB, table)

            all_comment_keys = set(source_comments.keys()) | set(target_comments.keys())
            for key in all_comment_keys:
                if source_comments.get(key) != target_comments.get(key):
                    table_diff['comments_diff'].append({
                        'key': key,
                        'source': source_comments.get(key, '(无)'),
                        'target': target_comments.get(key, '(无)')
                    })

            # 如果有差异，添加到结果中
            if any(table_diff.values()):
                differences['table_differences'][table] = table_diff
                print(f"   ✓ {table} - 发现差异")

        return differences

    def generate_bytebase_migration(self, differences: Dict) -> str:
        """生成Bytebase兼容的迁移脚本"""
        lines = [
            "-- ============================================================================ ",
            "-- AI-miniSOC 数据库迁移脚本 (Bytebase兼容)",
            f"-- 源数据库: {SOURCE_DB}",
            f"-- 目标数据库: {TARGET_DB}",
            f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "-- ",
            "-- 说明: 同步目标数据库的结构与源数据库一致",
            "-- 警告: 执行前请备份目标数据库！",
            "-- ",
            "-- Bytebase兼容性说明:",
            "-- - 不使用 DROP IF EXISTS",
            "-- - 不使用 psql 元命令",
            "-- - 明确的事务控制",
            "-- ============================================================================ ",
            "",
            "SET search_path TO public;",
            "",
            "-- 开始事务",
            "BEGIN;",
            "",
        ]

        # 1. 创建源数据库独有的函数
        if differences['functions_only_in_source']:
            lines.append("-- ============================================================================ ")
            lines.append("-- 步骤 1: 创建缺失的自定义函数")
            lines.append("-- ============================================================================ ")
            lines.append("")

            source_functions = self.get_table_functions(SOURCE_DB)
            for func_name in differences['functions_only_in_source']:
                func_def = source_functions[func_name]
                # 清理函数定义，移除 CREATE OR REPLACE
                func_def_clean = func_def.replace('CREATE OR REPLACE', 'CREATE')
                lines.append(f"-- 创建函数: {func_name}")
                lines.append(func_def_clean)
                lines.append("")

        # 2. 创建源数据库独有的表
        if differences['tables_only_in_source']:
            lines.append("-- ============================================================================ ")
            lines.append("-- 步骤 2: 创建源数据库独有的表")
            lines.append("-- ============================================================================ ")
            lines.append("")
            lines.append("-- 注意: 这些表需要使用 pg_dump 导出完整DDL")
            lines.append("-- 建议命令:")
            for table in differences['tables_only_in_source']:
                lines.append(f"-- pg_dump -h {self.host} -U {self.user} -d {SOURCE_DB} -t {table} --schema-only --no-owner --no-acl")
            lines.append("")

        # 3. 处理共同表的差异
        if differences['table_differences']:
            lines.append("-- ============================================================================ ")
            lines.append("-- 步骤 3: 同步共同表的结构")
            lines.append("-- ============================================================================ ")
            lines.append("")

            for table, diff in sorted(differences['table_differences'].items()):
                # 获取源数据库的详细信息
                source_columns = self.get_table_columns(SOURCE_DB, table)
                source_constraints = self.get_table_constraints(SOURCE_DB, table)
                source_indexes = self.get_table_indexes(SOURCE_DB, table)
                source_triggers = self.get_table_triggers(SOURCE_DB, table)
                source_functions = self.get_table_functions(SOURCE_DB)

                lines.append(f"-- ============================================================================ ")
                lines.append(f"-- 表: {table}")
                lines.append(f"-- ============================================================================ ")
                lines.append("")

                # 3.1 添加缺失的列
                if diff['columns_only_in_source']:
                    lines.append(f"-- 添加源数据库独有的列")
                    for column in diff['columns_only_in_source']:
                        col_info = source_columns[column]
                        col_type = col_info['full_type']
                        null_clause = "" if col_info['nullable'] else "NOT NULL"
                        default_clause = f"DEFAULT {col_info['default']}" if col_info['default'] else ""

                        lines.append(f"ALTER TABLE {table} ADD COLUMN {column} {col_type} {null_clause} {default_clause};")
                    lines.append("")

                # 3.2 修改列类型
                if diff['column_type_diffs']:
                    lines.append(f"-- 修改列类型")
                    for type_diff in diff['column_type_diffs']:
                        col = type_diff['column']
                        src_type = type_diff['source_type']
                        lines.append(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {src_type} USING {col}::{src_type};")
                    lines.append("")

                # 3.3 修改列的可空性
                if diff['column_nullable_diffs']:
                    lines.append(f"-- 修改列的可空性")
                    for nullable_diff in diff['column_nullable_diffs']:
                        col = nullable_diff['column']
                        if not nullable_diff['source_nullable']:
                            lines.append(f"ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL;")
                        else:
                            lines.append(f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL;")
                    lines.append("")

                # 3.4 修改默认值
                if diff['column_default_diffs']:
                    lines.append(f"-- 修改列默认值")
                    for default_diff in diff['column_default_diffs']:
                        col = default_diff['column']
                        src_default = default_diff['source_default']
                        if src_default:
                            lines.append(f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT {src_default};")
                        else:
                            lines.append(f"ALTER TABLE {table} ALTER COLUMN {col} DROP DEFAULT;")
                    lines.append("")

                # 3.5 添加约束
                if diff['constraints_only_in_source']:
                    lines.append(f"-- 添加源数据库独有的约束")
                    for constraint_name in diff['constraints_only_in_source']:
                        constraint = source_constraints[constraint_name]
                        lines.append(f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} {constraint['definition']};")
                    lines.append("")

                # 3.6 创建索引
                if diff['indexes_only_in_source']:
                    lines.append(f"-- 创建源数据库独有的索引")
                    for index_name in diff['indexes_only_in_source']:
                        index = source_indexes[index_name]
                        unique = "UNIQUE " if index['unique'] else ""
                        columns = ", ".join(index['columns'])
                        lines.append(f"CREATE {unique}INDEX {index_name} ON {table}({columns});")
                    lines.append("")

                # 3.7 创建触发器
                if diff['triggers_only_in_source']:
                    lines.append(f"-- 创建源数据库独有的触发器")
                    for trigger_name in diff['triggers_only_in_source']:
                        trigger = source_triggers[trigger_name]
                        # 提取触发器定义中的关键部分
                        trigger_def = trigger['definition']
                        # 简化触发器定义
                        lines.append(f"-- 触发器: {trigger_name}")
                        lines.append(trigger_def + ";")
                    lines.append("")

                # 3.8 同步注释
                if diff['comments_diff']:
                    lines.append(f"-- 同步表和列注释")
                    source_comments = self.get_table_comments(SOURCE_DB, table)

                    for comment_diff in diff['comments_diff']:
                        key = comment_diff['key']
                        source = comment_diff['source']
                        if source != '(无)':
                            escaped_comment = source.replace("'", "''")
                            if key == 'table':
                                lines.append(f"COMMENT ON TABLE {table} IS '{escaped_comment}';")
                            elif key.startswith('column:'):
                                col = key.replace('column:', '')
                                lines.append(f"COMMENT ON COLUMN {table}.{col} IS '{escaped_comment}';")
                    lines.append("")

        # 4. 提交事务
        lines.append("-- ============================================================================ ")
        lines.append("-- 提交事务")
        lines.append("-- ============================================================================ ")
        lines.append("")
        lines.append("-- 验证变更后，取消下面注释并执行")
        lines.append("-- COMMIT;")
        lines.append("")
        lines.append("-- 如果发现问题，执行回滚")
        lines.append("-- ROLLBACK;")
        lines.append("")

        return '\n'.join(lines)


def main():
    """主函数"""
    print("=" * 80)
    print("🔍 AI-miniSOC 数据库结构对比工具")
    print("生成Bytebase兼容迁移脚本")
    print("=" * 80)
    print()

    # 创建对比器
    comparator = DatabaseComparator(PGHOST, PGPORT, PGUSER, PGPASSWORD)

    # 比较数据库
    differences = comparator.compare_databases()

    # 显示差异摘要
    print("\n" + "=" * 80)
    print("📊 差异摘要")
    print("=" * 80)

    print(f"\n源数据库独有的表: {len(differences['tables_only_in_source'])}")
    for table in differences['tables_only_in_source']:
        print(f"   • {table}")

    print(f"\n目标数据库独有的表: {len(differences['tables_only_in_target'])}")
    for table in differences['tables_only_in_target']:
        print(f"   • {table}")

    print(f"\n源数据库独有的函数: {len(differences['functions_only_in_source'])}")
    for func in differences['functions_only_in_source']:
        print(f"   • {func}")

    print(f"\n有结构差异的表: {len(differences['table_differences'])}")
    for table, diff in differences['table_differences'].items():
        print(f"\n   表: {table}")
        if diff['columns_only_in_source']:
            print(f"      + 源数据库独有的列: {', '.join(diff['columns_only_in_source'])}")
        if diff['columns_only_in_target']:
            print(f"      - 目标数据库独有的列: {', '.join(diff['columns_only_in_target'])}")
        if diff['column_type_diffs']:
            for d in diff['column_type_diffs']:
                print(f"      ~ 类型差异 {d['column']}: {d['target_type']} -> {d['source_type']}")
        if diff['constraints_only_in_source']:
            print(f"      + 缺失约束: {', '.join(diff['constraints_only_in_source'])}")
        if diff['indexes_only_in_source']:
            print(f"      + 缺失索引: {', '.join(diff['indexes_only_in_source'])}")
        if diff['triggers_only_in_source']:
            print(f"      + 缺失触发器: {', '.join(diff['triggers_only_in_source'])}")
        if diff['comments_diff']:
            print(f"      ~ 注释差异: {len(diff['comments_diff'])} 项")

    # 生成迁移脚本
    print("\n" + "=" * 80)
    print("📝 生成Bytebase迁移脚本")
    print("=" * 80)

    migration_script = comparator.generate_bytebase_migration(differences)

    # 保存到文件
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_dir, 'migrate_testdb_from_source.sql')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(migration_script)

    print(f"✅ 迁移脚本已保存: {output_file}")

    # 也保存一份到 /tmp
    tmp_file = '/tmp/migrate_testdb_from_source.sql'
    with open(tmp_file, 'w', encoding='utf-8') as f:
        f.write(migration_script)
    print(f"✅ 迁移脚本副本: {tmp_file}")

    print("\n" + "=" * 80)
    print("✅ 对比完成！")
    print("=" * 80)
    print("\n📋 执行迁移:")
    print(f"   1. 查看脚本: cat {output_file}")
    print(f"   2. 测试执行:")
    print(f"      PGPASSWORD='{PGPASSWORD}' psql -h {PGHOST} -p {PGPORT} -U {PGUSER} -d {TARGET_DB} -f {output_file}")
    print(f"   3. 验证无误后，修改脚本取消 COMMIT 的注释")
    print(f"   4. 在Bytebase中创建迁移任务，粘贴脚本内容")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
