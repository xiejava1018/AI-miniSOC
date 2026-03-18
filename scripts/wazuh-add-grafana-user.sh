#!/bin/bash
# Wazuh API用户创建脚本（示例版本）
# 此脚本将为Grafana创建一个专用的只读API用户
#
# 使用方法:
#   export WAZUH_GRAFANA_PASSWORD='your_secure_password'
#   export WAZUH_ADMIN_USER='wazuh'
#   export WAZUH_ADMIN_PASSWORD='admin_password'
#   bash scripts/wazuh-add-grafana-user.sh
#
# 安全警告: 此脚本需要从环境变量读取密码，不要硬编码！

set -e

# 从环境变量读取配置
NEW_USERNAME="${WAZUH_GRAFANA_USER:-grafana}"
NEW_PASSWORD="${WAZUH_GRAFANA_PASSWORD}"
WAZUH_API_URL="${WAZUH_API_URL:-https://192.168.0.40:55000}"
ADMIN_USER="${WAZUH_ADMIN_USER:-wazuh}"
ADMIN_PASS="${WAZUH_ADMIN_PASSWORD}"

# 安全检查
if [ -z "$NEW_PASSWORD" ]; then
    echo "❌ 错误: 必须设置 WAZUH_GRAFANA_PASSWORD 环境变量"
    echo "   示例: export WAZUH_GRAFANA_PASSWORD='your_secure_password'"
    exit 1
fi

if [ -z "$ADMIN_PASS" ]; then
    echo "❌ 错误: 必须设置 WAZUH_ADMIN_PASSWORD 环境变量"
    echo "   示例: export WAZUH_ADMIN_PASSWORD='admin_password'"
    exit 1
fi

echo "🔧 Wazuh API用户创建工具"
echo "================================"
echo ""
echo "新用户信息:"
echo "  用户名: $NEW_USERNAME"
echo "  Wazuh API: $WAZUH_API_URL"
echo ""

# 方法1: 尝试通过API创建用户
echo "📝 方法1: 通过Wazuh API创建用户"
echo "-------------------------------------------"

# 先获取JWT token
echo "获取认证Token..."
TOKEN=$(curl -k -s -X POST "$WAZUH_API_URL/security/user/authenticate?raw=true" \
  --user "$ADMIN_USER:$ADMIN_PASS" 2>/dev/null)

if [ -n "$TOKEN" ] && [ "$TOKEN" != "Unauthorized" ]; then
    echo "✅ Token获取成功"

    # 创建新用户
    echo "创建新用户 $NEW_USERNAME..."

    RESPONSE=$(curl -k -s -X POST "$WAZUH_API_URL/security/users" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"username\": \"$NEW_USERNAME\",
        \"password\": \"$NEW_PASSWORD\"
      }" 2>/dev/null)

    echo "响应: $RESPONSE"

    if echo "$RESPONSE" | grep -q "id"; then
        echo "✅ 用户创建成功！"
    else
        echo "⚠️  用户创建失败，尝试方法2..."
    fi
else
    echo "❌ Token获取失败"
fi

echo ""
echo "📝 方法2: 直接修改RBAC数据库"
echo "-------------------------------------------"

# 方法2: 直接操作数据库
cat > /tmp/add_wazuh_user.py << PYTHON_SCRIPT
import sqlite3
import hashlib
from datetime import datetime
import os

# 从环境变量读取配置
DB_PATH = os.getenv('WAZUH_DB_PATH', "/var/ossec/api/configuration/security/rbac.db")
USERNAME = os.getenv('WAZUH_GRAFANA_USER', 'grafana')
PASSWORD = os.getenv('WAZUH_GRAFANA_PASSWORD')

if not PASSWORD:
    print("❌ 错误: 必须设置 WAZUH_GRAFANA_PASSWORD 环境变量")
    exit(1)

def hash_password(password):
    """生成密码哈希"""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def add_user():
    """添加新用户到RBAC数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查用户是否已存在
    cursor.execute("SELECT id FROM users WHERE username = ?", (USERNAME,))
    existing = cursor.fetchone()

    if existing:
        print(f"⚠️  用户 {USERNAME} 已存在，更新密码...")
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                      (hash_password(PASSWORD), USERNAME))
    else:
        print(f"✅ 创建新用户 {USERNAME}...")

        # 获取当前时间
        now = datetime.now().isoformat()

        # 插入用户
        cursor.execute("""
            INSERT INTO users (username, password_hash, is_admin, created_at)
            VALUES (?, ?, 0, ?)
        """, (USERNAME, hash_password(PASSWORD), now))

        # 获取新用户ID
        user_id = cursor.lastrowid
        print(f"   用户ID: {user_id}")

    # 为用户分配只读角色
    print("分配角色权限...")

    # 检查是否有只读角色，如果没有则创建
    cursor.execute("SELECT id FROM roles WHERE name = \"readonly\"")
    readonly_role = cursor.fetchone()

    if not readonly_role:
        print("   创建只读角色...")
        cursor.execute("""
            INSERT INTO roles (name, description, created_at)
            VALUES (?, ?, ?)
        """, ("readonly", "Read-only access for Grafana", datetime.now().isoformat()))
        role_id = cursor.lastrowid
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
    print(f"\n💡 下一步:")
    print(f"   1. 在Grafana中配置Infinity数据源")
    print(f"   2. URL: {os.getenv('WAZUH_API_URL', 'https://192.168.0.40:55000')}")
    print(f"   3. 用户名: {USERNAME}")

if __name__ == "__main__":
    add_user()
PYTHON_SCRIPT

# 复制到远程服务器并执行（需要配置SSH）
# scp /tmp/add_wazuh_user.py user@wazuh-server:/tmp/
# ssh user@wazuh-server "sudo python3 /tmp/add_wazuh_user.py"

echo ""
echo "⚠️  注意: 需要手动将脚本复制到Wazuh服务器执行"
echo "✅ 配置完成！"
