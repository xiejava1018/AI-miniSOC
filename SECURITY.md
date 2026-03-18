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
- [ ] **审查所有文档文件（.md、.txt等）**
- [ ] 运行 `bash scripts/security-check.sh` 验证

## 📝 安全事件案例研究

### 事件1: 文档文件敏感信息泄露 (2026-03-18)

**问题描述**:
在提交代码时，多个文档文件（.md）中包含了硬编码的敏感信息：
- Grafana管理员密码
- Wazuh管理员密码
- 系统sudo密码

**根本原因**:
1. 只检查了代码文件，忽略了文档文件
2. 安全检查脚本未包含文档文件类型
3. 文档中使用了真实密码作为示例

**影响范围**:
- 6个文档文件包含硬编码密码
- 1个安全事件报告文件包含真实密码
- 敏感信息在公共仓库暴露约1小时

**处理措施**:
1. ✅ 立即从文档中移除所有硬编码密码
2. ✅ 使用git filter-branch从Git历史中彻底清除
3. ✅ 强制推送重写远程仓库历史
4. ✅ 更新安全检查脚本，包含文档文件
5. ✅ 记录事件并作为安全教训

**教训总结**:
- ⚠️ **文档文件也可能包含敏感信息**
- ⚠️ **即使是"示例"或"临时"密码也不应使用真实凭证**
- ⚠️ **提交前必须检查所有文件类型，包括文档**
- ⚠️ **安全检查应覆盖所有文件类型**

**预防措施**:
```bash
# 更新安全检查脚本，包含文档文件
grep -rn "password\|token\|api_key\|secret" \
  --include="*.py" --include="*.sh" \
  --include="*.md" --include="*.txt" \
  --include="*.yml" --include="*.yaml" \
  --include="*.json" .
```

## 🛡️ 推荐工具

- **git-secrets**: 自动检测提交中的敏感信息
- **truffleHog**: 扫描Git历史中的密钥
- **gitleaks**: 检测仓库中的敏感信息

---
**重要**: 此策略应被所有项目成员严格遵守！

**最后更新**: 2026-03-18
**版本**: v1.1
**安全事件**: 已记录1起敏感信息泄露事件（见案例研究）
