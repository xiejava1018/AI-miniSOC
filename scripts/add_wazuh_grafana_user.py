#!/usr/bin/env python3
"""
Wazuh API用户创建脚本
为Grafana创建专用的只读API用户

安全警告: 此脚本需要密码作为环境变量或命令行参数传入
"""

import sqlite3
import hashlib
import sys
import os
from datetime import datetime

# 配置
DB_PATH = os.getenv('WAZUH_DB_PATH', "/var/ossec/api/configuration/security/rbac.db")
USERNAME = os.getenv('WAZUH_GRAFANA_USER', 'grafana')
PASSWORD = os.getenv('WAZUH_GRAFANA_PASSWORD')

if not PASSWORD:
    print("❌ 错误: 必须设置 WAZUH_GRAFANA_PASSWORD 环境变量")
    print("   示例: export WAZUH_GRAFANA_PASSWORD='your_secure_password'")
    print(f"   或: WAZUH_GRAFANA_PASSWORD='your_password' {sys.argv[0]}")
    sys.exit(1)

def hash_password(password):
    """生成密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

def add_user():
    """添加新用户到RBAC数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 检查用户是否已存在
        cursor.execute("SELECT id FROM users WHERE username = ?", (USERNAME,))
        existing = cursor.fetchone()

        if existing:
            print(f"⚠️  用户 {USERNAME} 已存在，更新密码...")
            cursor.execute("UPDATE users SET password = ? WHERE username = ?",
                          (hash_password(PASSWORD), USERNAME))
            user_id = existing[0]
        else:
            print(f"✅ 创建新用户 {USERNAME}...")

            # 获取当前时间
            now = datetime.now().isoformat()

            # 插入用户
            cursor.execute("""
                INSERT INTO users (username, password, allow_run_as, created_at)
                VALUES (?, ?, 0, ?)
            """, (USERNAME, hash_password(PASSWORD), now))

            user_id = cursor.lastrowid
            print(f"   用户ID: {user_id}")

        # 分配只读角色
        print("分配角色权限...")

        # 检查是否有只读角色
        cursor.execute("SELECT id, name FROM roles WHERE name = \"readonly\"")
        readonly_role = cursor.fetchone()

        if not readonly_role:
            print("   创建只读角色...")
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO roles (name, description, created_at)
                VALUES (?, ?, ?)
            """, ("readonly", "Read-only access for Grafana", now))
            role_id = cursor.lastrowid
            print(f"   角色ID: {role_id}")
        else:
            role_id = readonly_role[0]
            print(f"   使用现有角色ID: {role_id}")

        # 将用户映射到角色
        cursor.execute("SELECT id FROM user_roles WHERE user_id = ? AND role_id = ?", (user_id, role_id))
        existing_mapping = cursor.fetchone()

        if not existing_mapping:
            cursor.execute("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES (?, ?)
            """, (user_id, role_id))
            print("✅ 角色分配成功")
        else:
            print("✅ 角色已存在")

        conn.commit()
        conn.close()

        print(f"\n✅ 用户创建成功！")
        print(f"   用户名: {USERNAME}")
        print(f"   密码: {PASSWORD}")
        print(f"\n💡 在Grafana Infinity中使用:")
        print(f"   URL: https://192.168.0.40:55000")
        print(f"   用户名: {USERNAME}")
        print(f"   密码: {PASSWORD}")
        print(f"\n📊 可用的API端点:")
        print(f"   - GET  /agents")
        print(f"   - GET  /agents/summary/status")
        print(f"   - GET  /agents/:id")

        return True

    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Wazuh API用户创建工具")
    print("=" * 50)
    print()
    add_user()
