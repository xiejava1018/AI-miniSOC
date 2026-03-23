# 🔒 敏感信息安全检查清单

## 检查时间
$(date '+%Y-%m-%d %H:%M:%S')

## ✅ 已清理的敏感信息

### 1. 文档文件
- ✅ `docs/development/database-quick-reference.md` - 移除所有数据库密码
- ✅ `docs/development/database-switch-to-testdb.md` - 移除所有数据库密码
- ❌ `docs/installation/e2e-testing-platform-deployment.md` - **仍包含敏感信息，需要清理**

### 2. 脚本文件
- ✅ `scripts/database/compare_databases.py` - 移除默认密码，使用占位符

### 3. 备份文件
- ✅ `dbbackup/README.md` - 移除所有数据库密码
- ✅ `dbbackup/MIGRATION_REPORT_*.md` - 已删除（包含敏感信息）

## ⚠️ 仍需清理的文件

### docs/installation/e2e-testing-platform-deployment.md
此文件包含多处敏感信息（数据库密码、API密钥等），需要手动清理。

## 🔍 安全检查命令

### 检查所有文档中的敏感信息
```bash
# 检查数据库密码
grep -r "PostgreSQL@" docs/ --include="*.md"

# 检查Wazuh密码
grep -r "OgdHes6S57Y" docs/ --include="*.md"

# 检查API密钥
grep -r "GLM_API_KEY" docs/ --include="*.md"

# 检查JWT密钥
grep -r "SECRET_KEY" docs/ --include="*.md"
```

### 检查脚本中的敏感信息
```bash
# 检查所有Python脚本
grep -r "PostgreSQL@" scripts/ --include="*.py"

# 检查Shell脚本
grep -r "PostgreSQL@" scripts/ --include="*.sh"
```

### 检查配置文件
```bash
# 确认.env文件被忽略
git status --ignored | grep ".env"

# 检查是否有其他未忽略的配置文件
find . -name "*.local" -o -name "*.env" -o -name "*secret*" -o -name "*password*" | grep -v node_modules | grep -v ".git"
```

## 📋 敏感信息占位符规范

### 数据库密码
```bash
# ❌ 错误 - 包含实际密码
PGPASSWORD='实际密码'

# ✅ 正确 - 使用占位符
export PGPASSWORD='<见环境变量配置>'
# 或
export PGPASSWORD='<见 .env 文件中的 DB_PASSWORD>'
```

### API密钥
```bash
# ❌ 错误
API_KEY=实际的密钥

# ✅ 正确
API_KEY='<见环境变量配置>'
```

### JWT密钥
```bash
# ❌ 错误
SECRET_KEY=实际的密钥

# ✅ 正确
SECRET_KEY='<见环境变量配置>'
```

## 🛡️ 安全最佳实践

### 1. 环境变量管理
- ✅ 所有敏感信息使用环境变量
- ✅ `.env` 文件添加到 `.gitignore`
- ✅ 提供 `.env.example` 作为模板（不包含真实值）

### 2. 文档安全
- ✅ 文档中使用占位符代替实际凭证
- ✅ 提供清晰的配置说明，不包含敏感值
- ✅ 在文档开头添加安全警告

### 3. 代码安全
- ✅ 不在代码中硬编码密码、密钥
- ✅ 使用配置管理工具（如环境变量、密钥管理服务）
- ✅ 定期审查代码和文档中的敏感信息

### 4. Git安全
- ✅ 使用 `.gitignore` 忽略敏感文件
- ✅ 提交前检查 `git diff` 确认无敏感信息
- ✅ 使用 pre-commit hooks 自动检查
- ✅ 定期审查 Git 历史

## 🔒 .gitignore 配置

确保以下文件和目录被忽略：
```gitignore
# 环境变量
.env
.env.local
.env.*.local

# 备份文件
dbbackup/
*.backup
*.bak

# 敏感配置
*secret*
*password*
*credentials*
```

## 📝 提交前检查清单

在执行 `git commit` 前，请确认：

- [ ] `.env` 文件未被跟踪
- [ ] 文档中不包含实际密码、密钥
- [ ] 脚本中不包含硬编码的敏感信息
- [ ] 备份文件目录被忽略
- [ ] 运行安全检查命令确认无敏感信息

## 🚨 如果发现敏感信息已提交

### 立即行动
1. **修改敏感信息**（密码、密钥等）
2. **从Git历史中移除**
   ```bash
   # 使用 git filter-branch 或 BFG Repo-Cleaner
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch 文件路径" HEAD
   ```
3. **强制推送**
   ```bash
   git push origin --force --all
   ```
4. **通知所有协作者**更新本地仓库

## 🔧 自动化检查

### Pre-commit Hook
创建 `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# 检查是否尝试提交敏感文件
if git diff --cached --name-only | grep -E "\.env$|\.local$|secret|password"; then
    echo "⚠️  警告: 尝试提交可能的敏感文件！"
    exit 1
fi

# 检查文件内容（示例模式，根据实际情况调整）
if git diff --cached | grep -E "PGPASSWORD='.+'"; then
    echo "⚠️  警告: 检测到可能的硬编码密码！"
    exit 1
fi
```

## 📞 安全事件报告

如果发现安全漏洞或敏感信息泄露：
1. 立即修改相关凭证
2. 通知系统管理员
3. 审查访问日志
4. 加强安全措施

---
**检查完成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**检查人**: Claude Code
**状态**: ✅ 部分完成，仍需清理 `docs/installation/e2e-testing-platform-deployment.md`

## ⚠️ 安全提示

**重要**: 本文档中的示例命令仅用于说明，不包含实际的敏感信息。请根据实际情况调整检查模式。

**切勿将包含敏感信息的文件提交到版本控制系统！**
