# 数据库初始化指南

## 📋 前提条件

1. **PostgreSQL服务器** - 192.168.0.42:5432
2. **数据库名称** - AI-miniSOC-db
3. **用户名** - postgres
4. **密码** - <见环境变量配置>

## 🚀 执行方法

### 方法1：从本地执行（需要安装PostgreSQL客户端）

```bash
# 安装PostgreSQL客户端
sudo apt-get update
sudo apt-get install -y postgresql-client

# 执行初始化脚本
PGPASSWORD='<见环境变量配置>' psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-db \
  -f scripts/database/init_soc_assets.sql
```

### 方法2：在数据库服务器上执行

```bash
# SSH登录到数据库服务器
ssh xiejava@192.168.0.42

# 复制SQL文件到服务器
scp scripts/database/init_soc_assets.sql xiejava@192.168.0.42:/tmp/

# 在服务器上执行
sudo -u postgres psql -d AI-miniSOC-db -f /tmp/init_soc_assets.sql
```

### 方法3：使用数据库管理工具

1. **pgAdmin**:
   - 连接到 192.168.0.42:5432
   - 打开 `AI-miniSOC-db` 数据库
   - 打开Query Tool
   - 复制并执行 `scripts/database/init_soc_assets.sql` 的内容

2. **DBeaver**:
   - 创建新连接：192.168.0.42:5432
   - 打开SQL编辑器
   - 执行脚本

3. **DataGrip**:
   - 类似pgAdmin的操作

## ✅ 验证安装

执行以下命令验证表已创建：

```sql
-- 查看所有表
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'soc_%'
ORDER BY table_name;

-- 应该看到：
-- soc_assets
-- soc_asset_ports

-- 查看soc_assets表结构
\d soc_assets

-- 查看soc_asset_ports表结构
\d soc_asset_ports
```

## 📊 创建的表

### soc_assets（资产表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 主键（UUID） |
| asset_ip | INET | IP地址（唯一） |
| mac_address | MACADDR | MAC地址 |
| name | VARCHAR(255) | 资产名称 |
| asset_description | TEXT | 资产描述 |
| asset_type | VARCHAR(50) | 资产类型 |
| criticality | VARCHAR(20) | 重要性等级 |
| owner | VARCHAR(255) | 负责人 |
| business_unit | VARCHAR(255) | 业务单元 |
| asset_status | VARCHAR(20) | 状态 |
| wazuh_agent_id | VARCHAR(100) | Wazuh Agent ID |
| status_updated_at | TIMESTAMP | 状态更新时间 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### soc_asset_ports（端口表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键 |
| asset_ip | INET | 关联资产IP |
| port | INTEGER | 端口号 |
| protocol | TEXT | 协议（tcp/udp） |
| service | TEXT | 服务名称 |
| version | TEXT | 服务版本 |
| status | TEXT | 状态 |
| scanned_at | TIMESTAMP | 扫描时间 |

## 🎯 命名规范

所有表遵循 `soc_` 前缀规范：

- ✅ `soc_assets`
- ✅ `soc_asset_ports`
- ✅ `soc_incidents`（未来）
- ✅ `soc_ai_analyses`（未来）

详细规范见：`docs/design/database-naming-conventions.md`

## 🔧 故障排除

### 问题1：连接被拒绝

```
connection refused
```

**解决**：
```bash
# 检查PostgreSQL服务是否运行
sudo systemctl status postgresql

# 检查防火墙
sudo ufw status
```

### 问题2：认证失败

```
password authentication failed
```

**解决**：
```bash
# 检查密码
echo $PGPASSWORD

# 重置密码（在服务器上）
sudo -u postgres psql
ALTER USER postgres PASSWORD 'new_password';
```

### 问题3：数据库不存在

```
database "AI-miniSOC-db" does not exist
```

**解决**：
```sql
-- 创建数据库
CREATE DATABASE "AI-miniSOC-db";
```

## 📚 相关文档

- 命名规范：`docs/design/database-naming-conventions.md`
- 产品路线图：`docs/design/product-vision-and-technical-roadmap.md`

---

**创建日期**: 2026-03-18
**版本**: v1.0
**作者**: Claude
