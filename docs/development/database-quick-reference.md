# 🗄️ 数据库配置快速参考

## 当前配置

### 本地开发环境
```
📍 数据库: AI-miniSOC-testdb (测试数据库)
🌐 地址:   192.168.0.42:5432
👤 用户:   postgres
🔑 密码:   见环境变量配置 (.env 文件中的 DB_PASSWORD)
```

### 生产环境
```
📍 数据库: AI-miniSOC-db (生产数据库)
🌐 地址:   192.168.0.42:5432
👤 用户:   postgres
🔑 密码:   见环境变量配置 (.env 文件中的 DB_PASSWORD)
```

## 快速命令

### 连接数据库
```bash
# 设置密码环境变量
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'

# 测试数据库
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb

# 生产数据库
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-db
```

### 查看表列表
```bash
\dt
```

### 查看表结构
```bash
\d table_name
```

### 退出数据库
```bash
\q
```

## 数据库对比

### 对比两个数据库结构
```bash
python3 scripts/database/compare_databases.py
```

### 同步数据库结构
```bash
# 生成迁移脚本
python3 scripts/database/compare_databases.py

# 执行迁移脚本
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -f scripts/database/migrate_testdb_v2.sql
```

## 备份与恢复

### 备份测试数据库
```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
pg_dump -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb \
  --no-owner --no-acl -f "dbbackup/testdb_backup_${TIMESTAMP}.sql"
```

### 恢复测试数据库
```bash
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -f dbbackup/testdb_backup_YYYYMMDD_HHMMSS.sql
```

## 开发工作流

### 1. 启动开发环境
```bash
# 终端1: 启动后端
cd src/backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 终端2: 启动前端
cd src/frontend
npm run dev
```

### 2. 运行测试
```bash
# 后端单元测试
cd src/backend
pytest

# 前端单元测试
cd src/frontend
npm run test:unit

# E2E测试
cd src/frontend
npm run test:e2e
```

### 3. 查看日志
```bash
# 测试数据库日志
tail -f /var/log/postgresql/postgresql-16-main.log

# 或在数据库中查看
SELECT * FROM soc_audit_logs ORDER BY created_at DESC LIMIT 10;
```

## 环境切换

### 切换到生产数据库
```bash
# 修改 src/backend/app/core/config.py
DB_NAME: str = "AI-miniSOC-db"

# 修改 .env
DB_NAME=AI-miniSOC-db

# 重启后端
```

### 切换到测试数据库
```bash
# 修改 src/backend/app/core/config.py
DB_NAME: str = "AI-miniSOC-testdb"

# 修改 .env
DB_NAME=AI-miniSOC-testdb

# 重启后端
```

## 常见问题

### Q: 如何重置测试数据库？
```bash
# 删除并重建测试数据库
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
psql -h 192.168.0.42 -p 5432 -U postgres -c "DROP DATABASE IF EXISTS \"AI-miniSOC-testdb\";"
psql -h 192.168.0.42 -p 5432 -U postgres -c "CREATE DATABASE \"AI-miniSOC-testdb\";"

# 执行迁移脚本
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -f src/backend/migrations/postgresql/001_system_management.sql
```

### Q: 如何导入种子数据？
```bash
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -f src/frontend/tests/setup/test-seed.sql
```

### Q: 如何清空测试数据？
```bash
# 清空所有表的数据（保留结构）
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -c "TRUNCATE TABLE soc_asset_ports, soc_assets, soc_menus, soc_role_menus, soc_roles, soc_users CASCADE;"
```

## 相关文档

- 📖 数据库设计: `docs/design/database-design.md`
- 📖 初始化指南: `docs/installation/database-init-guide.md`
- 📖 配置切换: `docs/development/database-switch-to-testdb.md`
- 📖 备份说明: `dbbackup/README.md`
- 📖 迁移报告: `dbbackup/MIGRATION_REPORT_*.md`

---
**更新时间**: $(date '+%Y-%m-%d %H:%M:%S')
**维护者**: AI-miniSOC Team

## ⚠️ 安全提示

**重要**: 本文档中的密码、密钥等敏感信息已移除，请查看 `.env` 文件或咨询数据库管理员获取实际凭证。

**切勿将包含敏感信息的 `.env` 文件提交到版本控制系统！**
