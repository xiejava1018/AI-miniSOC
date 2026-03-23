# 数据库配置切换说明

## 切换时间
$(date '+%Y-%m-%d %H:%M:%S')

## 切换概述
将本地开发环境和测试环境的数据源从 **AI-miniSOC-db** (生产数据库) 切换到 **AI-miniSOC-testdb** (测试数据库)。

## 配置变更

### 1. 后端配置
**文件**: `src/backend/app/core/config.py`
```python
# 修改前
DB_NAME: str = "AI-miniSOC-db"

# 修改后
DB_NAME: str = "AI-miniSOC-testdb"  # 使用测试数据库
```

### 2. 环境变量
**文件**: `.env`
```bash
# 修改前
DB_NAME=AI-miniSOC-db

# 修改后
DB_NAME=AI-miniSOC-testdb
```

### 3. 前端测试配置
**文件**: `src/frontend/.env.test`
```bash
# 已经是正确的配置，无需修改
TEST_DATABASE_NAME=AI-miniSOC-testdb
```

### 4. GitHub Actions
**文件**: `.github/workflows/e2e.yml`
```yaml
# 已经是正确的配置，无需修改
TEST_DATABASE_NAME: 'AI-miniSOC-testdb'
```

## 数据库信息

### AI-miniSOC-testdb (测试数据库)
- **主机**: 192.168.0.42
- **端口**: 5432
- **用户**: postgres
- **密码**: 见环境变量配置 (.env 文件中的 DB_PASSWORD)
- **表数量**: 17 个
- **状态**: ✅ 已同步最新结构

### 数据库连接测试
```bash
# 设置密码环境变量
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'

# 测试连接
psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb

# 查看表列表
\dt

# 查看数据库版本
SELECT version();
```

## 本地开发

### 启动后端
```bash
cd src/backend
# 确保 .env 文件中 DB_NAME=AI-miniSOC-testdb
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端
```bash
cd src/frontend
npm run dev
```

### 运行测试
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

## 注意事项

### ✅ 优势
1. **安全隔离**: 测试数据不会影响生产数据库
2. **独立测试**: 可以随意修改测试数据
3. **快速重置**: 可以随时清空或重建测试数据库
4. **并行开发**: 多个开发者可以使用不同的测试数据库

### ⚠️ 注意事项
1. **数据初始化**: 测试数据库需要手动导入种子数据
   ```bash
   export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
   psql -h 192.168.0.42 -p 5432 -U postgres -d AI-miniSOC-testdb -f src/frontend/tests/setup/test-seed.sql
   ```

2. **配置同步**: 生产环境部署时需要修改配置指向 AI-miniSOC-db

3. **定期同步**: 当生产数据库结构变更时，需要同步到测试数据库
   ```bash
   python3 scripts/database/compare_databases.py
   ```

## 回滚方案

如需切回生产数据库：
```bash
# 修改 src/backend/app/core/config.py
DB_NAME: str = "AI-miniSOC-db"

# 修改 .env
DB_NAME=AI-miniSOC-db

# 重启后端服务
```

## 数据库结构对比工具

使用对比工具检查两个数据库的差异：
```bash
python3 scripts/database/compare_databases.py
```

生成的迁移脚本位于：
- `scripts/database/migrate_testdb_from_source.sql` - 原始版本
- `scripts/database/migrate_testdb_v2.sql` - 简化版本（推荐）

## 相关文档

- 数据库设计: `docs/design/database-design.md`
- 数据库初始化指南: `docs/installation/database-init-guide.md`
- 迁移报告: `dbbackup/MIGRATION_REPORT_*.md`
- 备份说明: `dbbackup/README.md`

---
**配置切换完成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**状态**: ✅ 本地环境已切换到测试数据库

## ⚠️ 安全提示

**重要**: 本文档中的密码、密钥等敏感信息已移除，请查看 `.env` 文件或咨询数据库管理员获取实际凭证。

**切勿将包含敏感信息的 `.env` 文件提交到版本控制系统！**
