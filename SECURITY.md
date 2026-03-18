# AI-miniSOC 安全策略

## 🔒 核心原则

**绝不将以下信息提交到Git仓库**：
- ❌ 用户名和密码
- ❌ API Token和密钥
- ❌ 数据库连接字符串
- ❌ 第三方服务凭证
- ❌ 私钥和证书
- ❌ 包含敏感信息的配置文件

## ✅ 安全实践

### 1. 环境变量
所有敏感配置必须使用环境变量：
```python
# ✅ 正确
password = os.getenv('DB_PASSWORD')
if not password:
    raise ValueError("DB_PASSWORD environment variable required")

# ❌ 错误
password = "hardcoded_password_123"
```

### 2. 配置文件
- 使用 `.env` 文件存储本地配置
- 将 `.env` 添加到 `.gitignore`
- 提供 `.env.example` 作为模板
- 确保生产环境使用密钥管理系统

### 3. 脚本文件
- 避免在脚本中硬编码凭证
- 使用命令行参数或环境变量
- 在脚本头部添加安全警告

### 4. 示例文件
```bash
# .env.example - 可以提交
WAZUH_URL=https://192.168.0.40:55000
WAZUH_USER=wazuh
WAZUH_PASSWORD=your_password_here

# .env - 不提交
WAZUH_PASSWORD=actual_password_123
```

## 🚨 事故处理

如果敏感信息已提交到GitHub：

1. **立即更改密码**：所有暴露的凭证
2. **从Git历史中清除**：
   ```bash
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch path/to/sensitive/file' \
     --prune-empty --tag-name-filter cat -- --all
   git push origin --force --all
   ```
3. **通知相关方**：如果凭证已被他人访问
4. **审查访问日志**：检查是否有未授权访问

## 📋 提交前检查清单

- [ ] 搜索所有 "password"、"token"、"api_key"、"secret"
- [ ] 确认没有硬编码凭证
- [ ] 验证 .gitignore 包含所有敏感文件
- [ ] 检查备份文件是否包含敏感信息
- [ ] 审查所有新增的配置文件
- [ ] 运行 `bash scripts/security-check.sh` 验证

## 🛡️ 推荐工具

- **git-secrets**: 自动检测提交中的敏感信息
- **truffleHog**: 扫描Git历史中的密钥
- **gitleaks**: 检测仓库中的敏感信息

---
**重要**: 此策略应被所有项目成员严格遵守！

**最后更新**: 2026-03-18
**版本**: v1.0
