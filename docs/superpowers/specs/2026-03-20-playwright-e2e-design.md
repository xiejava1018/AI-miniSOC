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

### 测试数据种子

- 1个管理员用户（admin/admin123）
- 3个普通用户
- 2个角色（admin、user）
- 1个示例部门

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

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
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

```typescript
// tests/helpers/pages/LoginPage.ts
export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page.locator('input[name="username"]');
    this.passwordInput = page.locator('input[type="password"]');
    this.loginButton = page.locator('button[type="submit"]');
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
      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: ./src/frontend
        run: npm ci

      - name: Install Playwright
        working-directory: ./src/frontend
        run: npx playwright install --with-deps chromium

      - name: Run E2E tests
        working-directory: ./src/frontend
        run: npm run test:e2e
        env:
          TEST_DATABASE_URL: postgresql://testuser:testpass@localhost:5432/ai_minisoc_test
```

### 触发条件

- **push到main分支** - 运行完整E2E测试
- **Pull Request** - 运行完整E2E测试
- **其他分支** - 本地运行，不自动触发

## 10. 测试用例示例

### 01-auth.spec.ts

```typescript
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should login successfully with valid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL('/dashboard');
    await expect(page.locator('text=欢迎')).toBeVisible();
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');

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
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
  });

  test('should create a new user', async ({ page }) => {
    await page.goto('/system/users');
    await page.click('button:has-text("添加用户")');

    // 填写表单
    await page.fill('input[name="username"]', 'newuser');
    await page.fill('input[type="password"]', 'Test123456');
    await page.fill('input[name="email"]', 'new@example.com');
    await page.fill('input[name="full_name"]', '新用户');
    await page.selectOption('select[name="role_id"]', '2');

    await page.click('button:has-text("确定")');

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible();
    await expect(page.locator('text=newuser')).toBeVisible();
  });

  test('should delete a user', async ({ page }) => {
    await page.goto('/system/users');

    // 找到测试用户并删除
    const userRow = page.locator('text=deletable_user').first();
    await userRow.locator('button:has-text("删除")').click();

    // 确认删除
    await page.click('button:has-text("确定")');

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
- ✅ 测试运行时间 < 5分钟
- ✅ 失败测试有清晰的截图和日志
- ✅ 覆盖关键用户流程（登录、用户CRUD、权限）

## 14. 注意事项

1. **测试隔离** - 每个测试必须独立，不依赖其他测试
2. **数据清理** - 每次测试后清理数据，避免污染
3. **异步等待** - 使用waitForSelector而不是固定sleep
4. **选择器稳定** - 使用data-testid而不是CSS类名
5. **错误信息** - 失败时提供清晰的错误信息

## 15. 后续优化

- 添加视觉回归测试
- 增加性能监控
- 集成Allure测试报告
- 添加API响应时间验证
