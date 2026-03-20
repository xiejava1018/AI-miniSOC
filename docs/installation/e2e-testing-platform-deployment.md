# E2E测试平台部署指南

## 架构概览

**E2E测试平台统一部署在 192.168.0.42**

```
192.168.0.42 (E2E Testing Platform)
├── 前端开发服务器: http://192.168.0.42:5173
├── 后端API服务: http://192.168.0.42:8000
├── PostgreSQL数据库: 192.168.0.42:5432/AI-miniSOC-testdb
└── GitHub Actions Runner (待安装)
```

## 数据库配置

### 连接信息
```bash
# 使用密码连接
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb
```

### 环境变量
```bash
TEST_DATABASE_HOST=192.168.0.42
TEST_DATABASE_PORT=5432
TEST_DATABASE_USER=postgres
TEST_DATABASE_PASSWORD=PostgreSQL@2026
TEST_DATABASE_NAME=AI-miniSOC-testdb
```

### 初始化测试数据库
```bash
# 1. 创建测试数据库
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -c "CREATE DATABASE \"AI-miniSOC-testdb\";"

# 2. 执行迁移文件
cd /path/to/AI-miniSOC
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb -f src/backend/migrations/postgresql/001_system_management.sql

# 3. 加载测试数据
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb -f src/frontend/tests/setup/test-seed.sql
```

## 服务启动

### 1. 启动后端API服务
```bash
cd /path/to/AI-miniSOC/src/backend
# 设置环境变量
export DATABASE_HOST=192.168.0.42
export DATABASE_PORT=5432
export DATABASE_USER=postgres
export DATABASE_PASSWORD=PostgreSQL@2026
export DATABASE_NAME=AI-miniSOC-testdb

# 启动服务
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 启动前端开发服务器
```bash
cd /path/to/AI-miniSOC/src/frontend
# 设置API地址
export VITE_API_BASE_URL=http://192.168.0.42:8000

# 启动开发服务器
npm run dev
```

## 本地运行E2E测试

### 前置条件
1. ✅ PostgreSQL测试数据库已创建并初始化
2. ✅ 后端API服务运行在 http://192.168.0.42:8000
3. ✅ 前端开发服务器运行在 http://192.168.0.42:5173

### 运行所有E2E测试
```bash
cd src/frontend
npm run test:e2e
```

### 运行特定测试文件
```bash
cd src/frontend
npx playwright test tests/e2e/01-auth.spec.ts
```

### 调试模式
```bash
cd src/frontend
npm run test:e2e:debug
```

### 查看测试报告
```bash
cd src/frontend
npm run test:e2e:report
```

## GitHub Actions Runner配置

### 在192.168.0.42上安装Runner

#### 1. 创建runner目录
```bash
ssh user@192.168.0.42
sudo mkdir -p /opt/actions-runner
cd /opt/actions-runner
sudo chown -R $USER:$USER /opt/actions-runner
```

#### 2. 下载Actions Runner
```bash
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
```

#### 3. 配置runner
```bash
./config.sh \
  --url https://github.com/xiejava/AI-miniSOC \
  --token <YOUR_RUNNER_TOKEN> \
  --name "AI-miniSOC-E2E-Runner" \
  --labels "self-hosted,linux,e2e"
```

**获取RUNNER_TOKEN:**
1. 访问 https://github.com/xiejava/AI-miniSOC/settings/actions
2. 点击 "New self-hosted runner"
3. 选择 "Linux" + "x64"
4. 复制生成的token

#### 4. 安装Playwright浏览器
```bash
cd /path/to/AI-miniSOC/src/frontend
npm install -D @playwright/test playwright
npx playwright install --with-deps chromium
```

#### 5. 启动runner
```bash
cd /opt/actions-runner
./run.sh
```

#### 6. 配置自动启动（可选）
```bash
# 创建systemd服务
sudo ./svc.sh install
sudo ./svc.sh start
```

### 验证Runner状态

在GitHub仓库的Actions页面应该看到runner在线：
- Name: AI-miniSOC-E2E-Runner
- Status: Online
- Labels: self-hosted, linux, e2e

## 测试数据

### 默认测试用户

| 用户名 | 密码 | 角色 | 状态 |
|--------|------|------|------|
| admin | admin123 | 管理员 | active |
| testuser | Test123456! | 普通用户 | active |
| testuser2 | Test123456! | 普通用户 | active |
| deletable_user | Test123456! | 普通用户 | active |
| locked_user | Test123456! | 普通用户 | locked |
| disabled_user | Test123456! | 普通用户 | disabled |

### 重置测试数据
```bash
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb -f src/frontend/tests/setup/test-seed.sql
```

## 故障排查

### 测试失败: connection refused
**原因**: 服务未启动
**解决**:
```bash
# 检查前端
curl http://192.168.0.42:5173

# 检查后端
curl http://192.168.0.42:8000/docs

# 检查数据库
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb -c "SELECT 1"
```

### 数据库认证失败
**原因**: 密码错误或用户不存在
**解决**:
```bash
# 测试连接
PGPASSWORD='PostgreSQL@2026' psql -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb

# 检查用户
\du
```

### Runner未显示在线
**原因**: Runner未启动或网络问题
**解决**:
```bash
# 检查runner进程
ps aux | grep actions-runner

# 重启runner
cd /opt/actions-runner
./run.sh
```

### 测试超时
**原因**: 网络延迟或服务响应慢
**解决**:
1. 检查服务日志
2. 增加超时时间（playwright.config.ts中的timeout设置）
3. 检查防火墙规则

## CI/CD工作流

### 单元测试（GitHub-hosted）
- **触发**: push/PR到master或develop分支
- **Runner**: GitHub托管的ubuntu-latest
- **命令**: `npm test` (vitest单元测试)

### E2E测试（Self-hosted）
- **触发**: push/PR到master/develop分支 + 手动触发
- **Runner**: AI-miniSOC-E2E-Runner on 192.168.0.42
- **命令**: `npm run test:e2e`
- **环境**: 访问内网服务，重置测试数据库

### 查看测试结果
1. 访问GitHub Actions页面
2. 选择对应的workflow run
3. 下载artifacts查看详细报告

## 维护

### 更新Playwright版本
```bash
cd src/frontend
npm install -D @playwright/test@latest
npx playwright install --with-deps chromium
```

### 清理测试报告
```bash
cd src/frontend
rm -rf playwright-report/ test-results/
```

### 备份测试数据库
```bash
PGPASSWORD='PostgreSQL@2026' pg_dump -h 192.168.0.42 -U postgres -d AI-miniSOC-testdb > backup.sql
```

## 相关文档

- [Playwright E2E设计文档](../superpowers/specs/2026-03-20-playwright-e2e-design.md)
- [Playwright E2E实施计划](../superpowers/plans/2026-03-20-playwright-e2e-implementation.md)
- [项目主README](../../README.md)

---

**最后更新**: 2026-03-20
**维护者**: AI-miniSOC Team
