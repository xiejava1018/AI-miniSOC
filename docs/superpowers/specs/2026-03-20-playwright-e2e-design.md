# Playwright E2E测试环境设计文档

**日期:** 2026-03-20
**状态:** 设计阶段
**作者:** Claude (with human approval)

## 1. 概述

为AI-miniSOC项目配置Playwright端到端测试环境，专注于覆盖关键用户流程，使用独立测试数据库，验证前后端完整集成。

## 2. 设计目标

- **覆盖关键用户流程** - 登录、用户CRUD、权限验证
- **真实集成测试** - 使用独立PostgreSQL测试数据库
- **快速反馈** - 专注于Chromium浏览器，优化测试速度
- **CI/CD集成** - GitHub Actions自动化测试

## 3. 整体架构

```
┌─────────────────────────────────────────┐
│     Playwright Test Runner              │
│  (tests/e2e/*.spec.ts)                  │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼─────┐   ┌──────▼──────────┐
│  Frontend   │   │   Backend API   │
│  (Vite Dev) │   │  (FastAPI)      │
└──────┬──────┘   └──────┬──────────┘
       │                │
       └────────┬───────┘
                │
        ┌───────▼──────────┐
        │  Test Database   │
        │  (PostgreSQL)    │
        └──────────────────┘
```

**工作流程：**
1. Playwright启动Vite开发服务器（前端）
2. Playwright启动FastAPI服务器（后端）
3. 每个测试前重置测试数据库
4. 运行E2E测试，模拟真实用户操作
5. 测试完成后清理并关闭服务

## 4. 文件结构

```
src/frontend/
├── tests/
│   ├── e2e/
│   │   ├── 01-auth.spec.ts          # 认证流程测试
│   │   ├── 02-users.spec.ts         # 用户管理测试
│   │   ├── 03-security.spec.ts      # 权限验证测试
│   │   └── helpers/
│   │       ├── test-data.ts         # 测试数据生成器
│   │       ├── api-helpers.ts       # API辅助函数
│   │       └── auth-helpers.ts      # 认证辅助函数
│   ├── fixtures/                    # 测试fixtures
│   │   ├── db-fixture.ts           # 数据库fixture
│   │   └── server-fixture.ts       # 服务器fixture
│   └── setup/
│       ├── db-setup.ts             # 数据库初始化脚本
│       └── test-seed.sql           # 测试数据SQL
├── playwright.config.ts             # Playwright配置
├── .env.test                       # 测试环境变量
└── package.json                     # 添加e2e脚本
```

**测试优先级：**
1. **01-auth.spec.ts** - 登录、登出、token刷新（最重要）
2. **02-users.spec.ts** - 用户CRUD完整流程（核心业务）
3. **03-security.spec.ts** - 权限验证、锁定/解锁（安全相关）

## 5. 测试数据库配置

### 环境变量

```env
# .env.test
TEST_DATABASE_URL=postgresql://testuser:testpass@localhost:5433/ai_minisoc_test
TEST_API_BASE_URL=http://localhost:8000
TEST_FRONTEND_URL=http://localhost:5173
```

### 数据管理策略

- 每个测试套件前清空并重建表结构
- 每个测试前插入基础测试数据
- 测试间相互独立，可并行运行

### 数据库初始化策略

使用现有的数据库迁移文件初始化测试数据库：

```bash
# 从项目根目录执行
psql $TEST_DATABASE_URL -f src/backend/migrations/postgresql/001_system_management.sql
```

### 测试数据种子

基于实际数据库schema (`soc_roles`, `soc_users`, `soc_user_roles`)：

**SQL种子文件 (tests/setup/test-seed.sql):**
```sql
-- 插入测试角色
INSERT INTO soc_roles (id, name, code, description, is_system) VALUES
(1, '管理员', 'admin', '系统管理员，拥有所有权限', true),
(2, '普通用户', 'user', '普通用户角色', false)
ON CONFLICT (code) DO NOTHING;

-- 插入管理员用户
INSERT INTO soc_users (id, username, password_hash, email, full_name, role_id, status, is_superuser)
VALUES (1, 'admin', '$2b$12$...', 'admin@example.com', '系统管理员', 1, 'active', true)
ON CONFLICT (username) DO NOTHING;

-- 插入测试用户
INSERT INTO soc_users (username, password_hash, email, full_name, role_id, status)
VALUES
('testuser1', '$2b$12$...', 'test1@example.com', '测试用户1', 2, 'active'),
('testuser2', '$2b$12$...', 'test2@example.com', '测试用户2', 2, 'active'),
('testuser3', '$2b$12$...', 'test3@example.com', '测试用户3', 2, 'active');
```

**注意事项：**
- 密码使用bcrypt hash（`$2b$12$...`占位符，实际测试时使用固定hash）
- 所有测试用户密码统一为：`Test123456!`
- 管理员账号：`admin` / `admin123`

## 6. Playwright配置

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: 1,
  workers: process.env.CI ? 2 : 4,

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  reporter: [
    ['html', { open: 'never' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  // 同时启动前端和后端服务器
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
    },
    {
      command: 'cd ../backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000',
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
    },
  ],
});
```

**关键特性：**
- 自动启动Vite开发服务器
- 失败时自动截图和录屏
- CI环境减少并发worker
- 失败重试机制

## 7. 测试辅助函数和Fixtures

### 核心Fixtures

```typescript
// tests/fixtures/auth-fixture.ts
import { test as base } from '@playwright/test';

export const test = base.extend<{
  authenticatedPage: Page;
  adminPage: Page;
}>({
  authenticatedPage: async ({ page }, use) => {
    await loginAsUser(page, 'testuser', 'password123');
    await use(page);
  },

  adminPage: async ({ page }, use) => {
    await loginAsUser(page, 'admin', 'admin123');
    await use(page);
  },
});
```

### 辅助函数

- `loginAsUser(page, username, password)` - 登录辅助
- `createUser(page, userData)` - 创建用户
- `resetDatabase()` - 重置数据库
- `seedTestData()` - 插入测试数据

### Page Objects模式

由于使用Element Plus组件，推荐使用`data-testid`属性提高测试稳定性：

**方式1：添加data-testid（推荐）**
```vue
<!-- Login.vue 需要修改 -->
<el-input v-model="form.username" data-testid="username-input" />
<el-input v-model="form.password" type="password" data-testid="password-input" />
<el-button type="primary" @click="handleLogin" data-testid="login-button">登录</el-button>
```

```typescript
// tests/helpers/pages/LoginPage.ts
export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.getByTestId('username-input');
    this.passwordInput = page.getByTestId('password-input');
    this.loginButton = page.getByTestId('login-button');
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }
}
```

**方式2：使用Element Plus选择器（无需修改代码）**
```typescript
// 如果不能修改组件，使用Element Plus内部类名
export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.locator('.el-input__inner').first();
    this.passwordInput = page.locator('.el-input__inner[type="password"]');
    this.loginButton = page.locator('.el-button--primary');
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }
}
```

## 8. 错误处理

### 测试失败处理

```typescript
test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status !== testInfo.expectedStatus) {
    await page.screenshot({
      path: `screenshots/${testInfo.title}.png`
    });
    await page.context().close();
  }
});
```

### 常见错误场景

- **网络错误** - API超时、连接失败
- **认证错误** - Token过期、权限不足
- **数据错误** - 违反约束、数据冲突
- **UI错误** - 元素未找到、操作失败

## 9. CI/CD集成

### GitHub Actions配置

```yaml
# .github/workflows/e2e.yml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: ai_minisoc_test
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      # Setup Backend
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install Python dependencies
        working-directory: ./src/backend
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt

      # Setup Frontend
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: ./src/frontend/package-lock.json

      - name: Install frontend dependencies
        working-directory: ./src/frontend
        run: npm ci

      - name: Install Playwright
        working-directory: ./src/frontend
        run: npx playwright install --with-deps chromium

      - name: Initialize test database
        working-directory: ./src/backend
        run: |
          psql ${{ secrets.TEST_DATABASE_URL }} -f migrations/postgresql/001_system_management.sql
          psql ${{ secrets.TEST_DATABASE_URL }} -f ../frontend/tests/setup/test-seed.sql

      - name: Run E2E tests
        working-directory: ./src/frontend
        run: npm run test:e2e
        env:
          TEST_DATABASE_URL: ${{ secrets.TEST_DATABASE_URL }}

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: src/frontend/playwright-report/
          retention-days: 30
```

### 触发条件

- **push到main分支** - 运行完整E2E测试
- **Pull Request** - 运行完整E2E测试
- **其他分支** - 本地运行，不自动触发

## 10. 测试用例示例

### 01-auth.spec.ts

**注意：** 需要先在Login.vue中添加`data-testid`属性

```typescript
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('/login');

    // 使用data-testid选择器
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('admin123');
    await page.getByTestId('login-button').click();

    // 验证跳转到dashboard
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/login');

    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('wrongpassword');
    await page.getByTestId('login-button').click();

    // Element Plus错误消息
    await expect(page.locator('.el-message--error')).toBeVisible();
  });
});
```

### 02-users.spec.ts

```typescript
import { test, expect } from '@playwright/test';

test.describe('User Management', () => {
  test.beforeEach(async ({ page }) => {
    // 登录为管理员
    await page.goto('/login');
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('admin123');
    await page.getByTestId('login-button').click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test('should display user list', async ({ page }) => {
    await page.goto('/system/users');

    // 验证表格存在
    await expect(page.locator('.el-table')).toBeVisible();

    // 验证管理员用户存在
    await expect(page.locator('text=admin')).toBeVisible();
  });

  test('should create a new user', async ({ page }) => {
    await page.goto('/system/users');
    await page.getByRole('button', { name: '添加用户' }).click();

    // 填写表单
    await page.getByTestId('username-input').fill('newuser');
    await page.getByTestId('password-input').fill('Test123456!');
    await page.getByTestId('email-input').fill('new@example.com');
    await page.getByTestId('full-name-input').fill('新用户');

    // 选择角色
    await page.getByRole('combobox').click();
    await page.getByRole('option', { name: '普通用户' }).click();

    // 提交
    await page.getByRole('button', { name: '确定' }).click();

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible();
  });

  test('should delete a user', async ({ page }) => {
    await page.goto('/system/users');

    // 找到测试用户行
    const userRow = page.locator('.el-table-row').filter({ hasText: 'testuser1' });
    await userRow.locator('button:has-text("删除")').click();

    // 确认删除对话框
    await page.getByRole('button', { name: '确定' }).click();

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible();
  });
});
```

## 11. package.json脚本

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:debug": "playwright test --debug",
    "test:e2e:report": "playwright show-report"
  }
}
```

## 12. 实施步骤

1. **安装依赖** - `npm install -D @playwright/test playwright`
2. **创建配置** - playwright.config.ts
3. **创建辅助文件** - fixtures, helpers, page objects
4. **编写测试** - 从auth.spec.ts开始
5. **配置CI/CD** - 添加GitHub Actions workflow
6. **验证运行** - 本地和CI都成功运行

## 13. 成功标准

- ✅ 所有E2E测试在本地通过
- ✅ 所有E2E测试在CI/CD中通过
- ✅ 测试运行时间 < 10分钟（冷启动）
- ✅ 失败测试有清晰的截图和日志
- ✅ 覆盖关键用户流程（登录、用户CRUD、权限）
- ✅ 测试数据与实际schema匹配

## 14. 注意事项

1. **测试隔离** - 每个测试必须独立，不依赖其他测试
2. **数据清理** - 每次测试后清理数据，避免污染
3. **异步等待** - 使用`await expect(locator).toBeVisible()`而不是固定sleep
4. **选择器稳定** - 优先使用`data-testid`，其次是Role和Text
5. **错误信息** - 失败时提供清晰的错误信息
6. **路由验证** - 使用实际的路由路径（/login, /dashboard, /system/users）
7. **Element Plus** - 注意组件的异步加载和交互

## 15. 后续优化

- 添加视觉回归测试
- 增加性能监控
- 集成Allure测试报告
- 添加API响应时间验证

## 16. 本地开发指南

### 16.1 首次运行设置

```bash
# 1. 创建测试数据库
docker run -d --name test-db \
  -p 5433:5432 \
  -e POSTGRES_DB=ai_minisoc_test \
  -e POSTGRES_USER=testuser \
  -e POSTGRES_PASSWORD=testpass \
  postgres:16

# 2. 初始化数据库schema
psql postgresql://testuser:testpass@localhost:5433/ai_minisoc_test \
  -f src/backend/migrations/postgresql/001_system_management.sql

# 3. 安装Playwright
cd src/frontend
npm install -D @playwright/test playwright
npx playwright install --with-deps chromium
```

### 16.2 运行测试

```bash
# 运行所有E2E测试
npm run test:e2e

# 运行特定测试文件
npm run test:e2e -- tests/e2e/01-auth.spec.ts

# 使用UI模式运行
npm run test:e2e:ui

# 调试模式
npm run test:e2e:debug

# 查看测试报告
npm run test:e2e:report
```

### 16.3 添加data-testid属性

为提高测试稳定性，需要在关键组件上添加`data-testid`属性：

```vue
<!-- Login.vue -->
<el-input v-model="form.username" data-testid="username-input" />
<el-input v-model="form.password" type="password" data-testid="password-input" />
<el-button type="primary" @click="handleLogin" data-testid="login-button">
  登录
</el-button>

<!-- Users.vue - 对话框按钮 -->
<el-button type="primary" @click="showCreateDialog" data-testid="add-user-button">
  添加用户
</el-button>

<!-- UserDialog.vue -->
<el-input v-model="formData.username" data-testid="username-input" />
<el-input v-model="formData.password" type="password" data-testid="password-input" />
```

### 16.4 常见问题

**问题1：后端连接失败**
```bash
# 检查后端是否运行
curl http://localhost:8000/docs

# 手动启动后端
cd src/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**问题2：数据库连接失败**
```bash
# 检查数据库是否运行
docker ps | grep test-db

# 重启数据库
docker start test-db
```

**问题3：测试超时**
```bash
# 增加超时时间
TEST_TIMEOUT=60000 npm run test:e2e
```
