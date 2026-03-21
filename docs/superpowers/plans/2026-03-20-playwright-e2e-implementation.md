# Playwright E2E测试环境实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为AI-miniSOC项目配置完整的Playwright端到端测试环境，覆盖关键用户流程（登录、用户管理、权限验证），使用混合CI/CD模式（GitHub-hosted + Self-hosted runner）

**Architecture:** 前端E2E测试使用Playwright + Chromium，通过data-testid定位元素，访问内网PostgreSQL数据库和FastAPI后端，CI/CD采用混合模式（单元测试用GitHub-hosted，E2E测试用self-hosted runner）

**Tech Stack:** Playwright 1.40+, @playwright/test, Chromium, PostgreSQL 16, FastAPI, Vue 3, Element Plus, GitHub Actions

---

## 文件结构规划

### 新建文件
```
src/frontend/
├── playwright.config.ts                    # Playwright配置
├── tests/
│   ├── e2e/
│   │   ├── 01-auth.spec.ts                 # 认证流程测试
│   │   ├── 02-users.spec.ts                # 用户管理测试
│   │   ├── 03-security.spec.ts             # 权限验证测试
│   │   └── helpers/
│   │       ├── test-data.ts                 # 测试数据生成器
│   │       ├── api-helpers.ts               # API辅助函数
│   │       └── auth-helpers.ts              # 认证辅助函数
│   ├── fixtures/
│   │   └── auth-fixture.ts                 # 认证fixtures
│   └── setup/
│       ├── db-setup.ts                     # 数据库初始化脚本
│       └── test-seed.sql                   # 测试数据SQL
├── .env.test                               # 测试环境变量
└── test-results/                          # 测试报告目录（gitignore）
```

### 修改文件
```
src/frontend/src/views/Login.vue            # 添加data-testid属性
src/frontend/src/views/system/Users.vue     # 添加data-testid属性
src/frontend/src/components/UserDialog.vue  # 添加data-testid属性
package.json                               # 添加E2E测试脚本
```

---

## Phase 1: 安装和基础配置 (Tasks 1-3)

### Task 1: 安装Playwright依赖

**Files:**
- Modify: `src/frontend/package.json`

- [ ] **Step 1: 添加Playwright依赖到package.json**

```json
{
  "devDependencies": {
    "@playwright/test": "^1.40.0"
  }
}
```

- [ ] **Step 2: 安装依赖**

```bash
cd src/frontend
npm install -D @playwright/test playwright
```

- [ ] **Step 3: 安装Chromium浏览器**

```bash
npx playwright install --with-deps chromium
```

Expected: 浏览器二进制文件下载完成

- [ ] **Step 4: 验证安装**

```bash
npx playwright --version
```

Expected: 输出版本号（如 1.40.0）

- [ ] **Step 5: 提交**

```bash
git add package.json package-lock.json
git commit -m "chore: install Playwright and dependencies"
```

---

### Task 2: 创建Playwright配置文件

**Files:**
- Create: `src/frontend/playwright.config.ts`

- [ ] **Step 1: 创建playwright.config.ts**

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 0 : 1,
  workers: process.env.CI ? 1 : 2,
  timeout: 30000,

  use: {
    baseURL: 'http://192.168.0.30:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],

  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        // 使用内网IP，因为frontend服务器运行在192.168.0.30
        launchOptions: {
          args: ['--host-resolvable-rules=1']
        }
      },
    },
  ],

  // 注意：在内网环境运行，不自动启动服务器
  // 服务器需要手动启动或通过其他方式管理
});
```

- [ ] **Step 2: 创建.env.test环境变量文件**

```bash
# .env.test
TEST_DATABASE_URL=postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test
TEST_API_BASE_URL=http://192.168.0.30:8000
TEST_FRONTEND_URL=http://192.168.0.30:5173
TEST_ADMIN_USERNAME=admin
TEST_ADMIN_PASSWORD=admin123
```

- [ ] **Step 3: 验证配置文件**

```bash
npx playwright config validate
```

Expected: Configuration valid

- [ ] **Step 4: 提交**

```bash
git add playwright.config.ts .env.test
git commit -m "chore: add Playwright configuration and test environment variables"
```

---

### Task 3: 更新package.json脚本

**Files:**
- Modify: `src/frontend/package.json`

- [ ] **Step 1: 添加E2E测试脚本**

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e:debug": "playwright test --debug",
    "test:e2e:report": "playwright show-report",
    "test:e2e:install": "playwright install --with-deps chromium"
  }
}
```

- [ ] **Step 2: 验证脚本**

```bash
npm run --help | grep test:e2e
```

Expected: 显示所有test:e2e相关脚本

- [ ] **Step 3: 提交**

```bash
git add package.json
git commit -m "chore: add E2E test scripts to package.json"
```

---

## Phase 2: 测试辅助文件 (Tasks 4-6)

### Task 4: 创建测试辅助函数

**Files:**
- Create: `src/frontend/tests/helpers/test-data.ts`
- Create: `src/frontend/tests/helpers/auth-helpers.ts`
- Create: `src/frontend/tests/helpers/api-helpers.ts`

- [ ] **Step 1: 创建test-data.ts**

```typescript
// tests/helpers/test-data.ts

/**
 * 生成测试用户数据
 */
export const generateUserData = (overrides = {}) => ({
  username: `testuser_${Date.now()}`,
  password: 'Test123456!',
  email: `test${Date.now()}@example.com`,
  full_name: '测试用户',
  role_id: 2, // 普通用户角色
  ...overrides
});

/**
 * 生成有效的密码
 */
export const generatePassword = (): string => {
  const length = 12;
  const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
  let password = '';

  // 确保包含大小写字母、数字和特殊字符
  password += 'A'; // 大写
  password += 'a'; // 小写
  password += '1'; // 数字
  password += '!'; // 特殊字符

  for (let i = 0; i < length - 4; i++) {
    password += charset[Math.floor(Math.random() * charset.length)];
  }

  return password;
};

/**
 * 获取测试用户凭据
 */
export const getTestCredentials = () => ({
  admin: {
    username: 'admin',
    password: 'admin123'
  },
  regularUser: {
    username: 'testuser',
    password: 'Test123456!'
  }
});
```

- [ ] **Step 2: 创建auth-helpers.ts**

```typescript
// tests/helpers/auth-helpers.ts
import type { Page } from '@playwright/test';

/**
 * 登录辅助函数
 */
export async function loginAsUser(
  page: Page,
  username: string,
  password: string
): Promise<void> {
  // 使用data-testid选择器（需要在组件中添加）
  await page.getByTestId('username-input').fill(username);
  await page.getByTestId('password-input').fill(password);
  await page.getByTestId('login-button').click();

  // 等待导航完成
  await page.waitForURL(/\/dashboard/, { timeout: 5000 });
}

/**
 * 登出辅助函数
 */
export async function logout(page: Page): Promise<void> {
  // TODO: 实现登出逻辑，取决于UI设计
  await page.goto('/login');
}

/**
 * 等待页面加载完成
 */
export async function waitForPageLoad(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout: 10000 });
}
```

- [ ] **Step 3: 创建api-helpers.ts**

```typescript
// tests/helpers/api-helpers.ts
import type { APIRequestContext } from '@playwright/test';

interface CreateUserResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role_id: number;
  status: string;
}

/**
 * 通过API创建用户
 */
export async function createUserViaAPI(
  apiContext: APIRequestContext,
  userData: any,
  token: string
): Promise<CreateUserResponse> {
  const response = await apiContext.post('/api/v1/users', {
    data: userData,
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to create user: ${response.status()}`);
  }

  return await response.json() as CreateUserResponse;
}

/**
 * 通过API删除用户
 */
export async function deleteUserViaAPI(
  apiContext: APIRequestContext,
  userId: number,
  token: string
): Promise<void> {
  const response = await apiContext.delete(`/api/v1/users/${userId}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to delete user: ${response.status()}`);
  }
}

/**
 * 重置用户密码
 */
export async function resetPasswordViaAPI(
  apiContext: APIRequestContext,
  userId: number,
  token: string
): Promise<string> {
  const response = await apiContext.post(`/api/v1/users/${userId}/reset-password`, {
    data: {},
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok()) {
    throw new Error(`Failed to reset password: ${response.status()}`);
  }

  const result = await response.json();
  return result.new_password || 'GeneratedPassword123!';
}
```

- [ ] **Step 4: 提交**

```bash
git add tests/helpers/
git commit -m "test: add E2E test helper functions"
```

---

### Task 5: 创建认证Fixtures

**Files:**
- Create: `src/frontend/tests/fixtures/auth-fixture.ts`

- [ ] **Step 1: 创建auth-fixture.ts**

```typescript
// tests/fixtures/auth-fixture.ts
import { test as base } from '@playwright/test';
import { loginAsUser } from '../helpers/auth-helpers';

// 扩展test以包含认证页面
export const test = base.extend<{
  authenticatedPage: Page;
  adminPage: Page;
  apiContext: APIRequestContext;
}>({
  // 已认证的普通用户页面
  authenticatedPage: async ({ page }, use) => {
    await loginAsUser(page, 'testuser', 'Test123456!');
    await use(page);
  },

  // 管理员页面
  adminPage: async ({ page }, use) => {
    await loginAsUser(page, 'admin', 'admin123');
    await use(page);
  },

  // API上下文（用于直接API调用）
  apiContext: async ({ playwright }, use) => {
    const apiContext = await playwright.newContext();
    await use(apiContext);

    // 清理
    await test.afterEach(async () => {
      await apiContext.dispose();
    });
  },
});
```

- [ ] **Step 2: 提交**

```bash
git add tests/fixtures/auth-fixture.ts
git commit -m "test: add auth fixtures for E2E tests"
```

---

### Task 6: 创建数据库初始化脚本

**Files:**
- Create: `src/frontend/tests/setup/db-setup.ts`
- Create: `src/frontend/tests/setup/test-seed.sql`

- [ ] **Step 1: 创建db-setup.ts**

```typescript
// tests/setup/db-setup.ts
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const MIGRATION_FILE = path.resolve(
  __dirname,
  '../../../backend/migrations/postgresql/001_system_management.sql'
);

/**
 * 初始化测试数据库
 */
export function setupDatabase(): void {
  const dbUrl = process.env.TEST_DATABASE_URL;

  if (!dbUrl) {
    throw new Error('TEST_DATABASE_URL environment variable not set');
  }

  console.log('Setting up test database...');

  // 执行迁移文件
  try {
    execSync(`psql "${dbUrl}" -f "${MIGRATION_FILE}"`, {
      stdio: 'inherit'
    });
    console.log('✅ Database schema initialized');
  } catch (error) {
    console.error('❌ Failed to initialize database:', error);
    throw error;
  }
}

/**
 * 清空测试数据库
 */
export function resetDatabase(): void {
  const dbUrl = process.env.TEST_DATABASE_URL;

  if (!dbUrl) {
    throw new Error('TEST_DATABASE_URL environment variable not set');
  }

  console.log('Resetting test database...');

  try {
    execSync(`psql "${dbUrl}" -c "DROP SCHEMA public CASCADE"`, {
      stdio: 'inherit'
    });
    console.log('✅ Database reset complete');
  } catch (error) {
    console.error('❌ Failed to reset database:', error);
    throw error;
  }
}
```

- [ ] **Step 2: 创建test-seed.sql**

```sql
-- tests/setup/test-seed.sql
-- 注意：密码使用get_password_hash()生成的hash值

-- 插入测试角色
INSERT INTO soc_roles (id, name, code, description, is_system) VALUES
(1, '管理员', 'admin', '系统管理员，拥有所有权限', true),
(2, '普通用户', 'user', '普通用户角色', false)
ON CONFLICT (code) DO NOTHING;

-- 插入管理员用户 (密码: admin123)
INSERT INTO soc_users (id, username, hashed_password, email, full_name, role_id, status, is_superuser)
VALUES (1, 'admin', '$2a$12$LQv3c1yqBWVHxkd0LHAuHn6qsW3HnXqvEY8qB8DUJpMY6XPq4d1', 'admin@example.com', '系统管理员', 1, 'active', true)
ON CONFLICT (username) DO NOTHING;

-- 插入测试用户 (密码: Test123456!)
INSERT INTO soc_users (username, hashed_password, email, full_name, role_id, status)
VALUES
('testuser', '$2a$12$LQv3c1yqBWVHxkd0LHAuHn6qsW3HnXqvEY8qB8DUJpMY6XPq4d1', 'test@example.com', '测试用户', 2, 'active'),
('testuser2', '$2a$12$LQv3c1yqBWVHxkd0LHAuHn6qsW3HnXqvEY8qB8DUJpMY6XPq4d1', 'test2@example.com', '测试用户2', 2, 'active'),
('deletable_user', '$2a$12$LQv3c1yqBWVHxkd0LHAuHn6qsW3HnXqvEY8qB8DUJpMY6XPq4d1', 'deletable@example.com', '可删除用户', 2, 'active');
```

**注意:** 密码hash需要使用后端的`get_password_hash()`函数生成。临时使用占位符，实施时需要替换。

- [ ] **Step 3: 提交**

```bash
git add tests/setup/
git commit -m "test: add database setup and seed data for E2E tests"
```

---

## Phase 3: 添加data-testid属性 (Tasks 7-9)

### Task 7: 为Login组件添加data-testid

**Files:**
- Modify: `src/frontend/src/views/Login.vue`

- [ ] **Step 1: 修改Login.vue，添加data-testid属性**

找到表单输入和按钮元素，添加`data-testid`属性：

```vue
<el-input
  v-model="form.username"
  placeholder="请输入用户名"
  data-testid="username-input"
/>

<el-input
  v-model="form.password"
  type="password"
  placeholder="请输入密码"
  show-password
  data-testid="password-input"
/>

<el-button
  type="primary"
  @click="handleLogin"
  :loading="loading"
  data-testid="login-button"
>
  登录
</el-button>
```

- [ ] **Step 2: 运行类型检查**

```bash
cd src/frontend
npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/views/Login.vue
git commit -m "test: add data-testid attributes to Login component"
```

---

### Task 8: 为Users页面添加data-testid

**Files:**
- Modify: `src/frontend/src/views/system/Users.vue`

- [ ] **Step 1: 修改Users.vue，添加关键data-testid属性**

```vue
<!-- 添加用户按钮 -->
<el-button
  v-if="isAdmin"
  type="primary"
  @click="showCreateDialog"
  data-testid="add-user-button"
>
  <el-icon><Plus /></el-icon>
  添加用户
</el-button>

<!-- 搜索输入 -->
<el-input
  v-model="searchInput"
  placeholder="搜索用户名/邮箱/姓名"
  clearable
  style="width: 250px"
  @clear="handleSearch"
  data-testid="user-search-input"
/>

<!-- 查询按钮 -->
<el-button
  type="primary"
  @click="handleSearch"
  data-testid="search-button"
>
  查询
</el-button>

<!-- 表单字段 -->
<el-input
  v-model="formData.username"
  :disabled="mode === 'edit'"
  placeholder="请输入用户名（3-50字符）"
  data-testid="username-input"
/>

<el-input
  v-model="formData.password"
  type="password"
  placeholder="请输入密码（至少6位）"
  show-password
  data-testid="password-input"
  v-if="mode === 'create'"
/>

<el-button
  type="primary"
  @click="handleSubmit"
  :loading="submitting"
  data-testid="submit-user-button"
>
  确定
</el-button>
```

- [ ] **Step 2: 运行类型检查**

```bash
cd src/frontend
npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/views/system/Users.vue
git commit -m "test: add data-testid attributes to Users page"
```

---

### Task 9: 为UserDialog组件添加data-testid

**Files:**
- Modify: `src/frontend/src/components/UserDialog.vue`

- [ ] **Step 1: 修改UserDialog.vue，添加data-testid属性**

```vue
<el-form-item label="用户名" prop="username">
  <el-input
    v-model="formData.username"
    :disabled="mode === 'edit'"
    placeholder="请输入用户名（3-50字符）"
    data-testid="dialog-username-input"
  />
</el-form-item>

<el-form-item label="密码" prop="password" v-if="mode === 'create'">
  <el-input
    v-model="formData.password"
    type="password"
    placeholder="请输入密码（至少6位）"
    show-password
    data-testid="dialog-password-input"
  />
</el-form-item>

<el-form-item label="邮箱" prop="email">
  <el-input
    v-model="formData.email"
    type="email"
    placeholder="请输入邮箱"
    data-testid="dialog-email-input"
  />
</el-form-item>

<el-form-item label="姓名" prop="full_name">
  <el-input
    v-model="formData.full_name"
    placeholder="请输入姓名"
    data-testid="dialog-fullname-input"
  />
</el-form-item>

<el-form-item label="角色" prop="role_id">
  <el-select
    v-model="formData.role_id"
    placeholder="请选择角色"
    style="width: 100%"
    data-testid="dialog-role-select"
  >
    <el-option
      v-for="role in roles"
      :key="role.id"
      :label="role.name"
      :value="role.id"
    />
  </el-select>
</el-form-item>

<template #footer>
  <el-button @click="handleCancel" data-testid="dialog-cancel-button">取消</el-button>
  <el-button
    type="primary"
    @click="handleSubmit"
    :loading="submitting"
    data-testid="dialog-submit-button"
  >
    确定
  </el-button>
</template>
```

- [ ] **Step 2: 运行类型检查**

```bash
cd src/frontend
npx vue-tsc --noEmit
```

Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add src/components/UserDialog.vue
git commit -m "test: add data-testid attributes to UserDialog component"
```

---

## Phase 4: 编写E2E测试用例 (Tasks 10-12)

### Task 10: 编写认证测试

**Files:**
- Create: `src/frontend/tests/e2e/01-auth.spec.ts`

- [ ] **Step 1: 创建01-auth.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // 每个测试前回到登录页
    await page.goto('http://192.168.0.30:5173/login');
  });

  test('should display login page', async ({ page }) => {
    // 验证页面标题
    await expect(page.locator('h2')).toContainText('AI-miniSOC 登录');

    // 验证表单元素存在
    await expect(page.getByTestId('username-input')).toBeVisible();
    await expect(page.getByTestId('password-input')).toBeVisible();
    await expect(page.getByTestId('login-button')).toBeVisible();
  });

  test('should login successfully with valid admin credentials', async ({ page }) => {
    // 输入凭据
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('admin123');

    // 点击登录
    await page.getByTestId('login-button').click();

    // 验证跳转到dashboard
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });
  });

  test('should show error message with invalid credentials', async ({ page }) => {
    // 输入错误的凭据
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('wrongpassword');

    // 点击登录
    await page.getByTestId('login-button').click();

    // 验证错误消息
    await expect(page.locator('.el-message--error')).toBeVisible();
  });

  test('should show validation error for empty fields', async ({ page }) => {
    // 不输入任何内容，直接点击登录
    await page.getByTestId('login-button').click();

    // 验证表单验证
    await expect(page.getByText('请输入用户名')).toBeVisible();
  });

  test('should redirect to login when not authenticated', async ({ page }) => {
    // 尝试访问需要认证的页面
    await page.goto('http://192.168.0.30:5173/system/users');

    // 应该重定向到登录页
    await expect(page).toHaveURL(/\/login/);
  });
});
```

- [ ] **Step 2: 运行测试（预期：所有测试失败，因为组件没有data-testid）**

```bash
cd src/frontend
npx playwright test tests/e2e/01-auth.spec.ts
```

Expected: 部分测试通过，部分测试失败（取决于是否已添加data-testid）

- [ ] **Step 3: 修复data-testid并重新运行**

如果测试失败，返回Task 7-9添加data-testid，然后重新运行。

- [ ] **Step 4: 所有测试通过后提交**

```bash
git add tests/e2e/01-auth.spec.ts
git commit -m "test(e2e): add authentication flow tests"
```

---

### Task 11: 编写用户管理测试

**Files:**
- Create: `src/frontend/tests/e2e/02-users.spec.ts`

- [ ] **Step 1: 创建02-users.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('User Management', () => {
  test.beforeEach(async ({ adminPage }) => {
    // 使用adminPage fixture自动登录
    await adminPage.goto('http://192.168.0.30:5173/system/users');
    // 等待页面加载
    await adminPage.waitForLoadState('networkidle');
  });

  test('should display user list page', async ({ adminPage }) => {
    // 验证页面标题
    await expect(adminPage.locator('.page-header').toContainText('用户管理'));

    // 验证搜索和筛选控件
    await expect(adminPage.getByTestId('user-search-input')).toBeVisible();
    await expect(adminPage.getByTestId('add-user-button')).toBeVisible();

    // 验证表格存在
    await expect(adminPage.locator('.el-table')).toBeVisible();
  });

  test('should display list of users', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 验证管理员用户存在
    await expect(adminPage.locator('text=admin')).toBeVisible();
  });

  test('should search users by username', async ({ adminPage }) => {
    // 输入搜索关键词
    await adminPage.getByTestId('user-search-input').fill('admin');
    await adminPage.getByTestId('search-button').click();

    // 等待搜索结果
    await adminPage.waitForTimeout(1000);

    // 验证搜索结果
    const rows = adminPage.locator('.el-table-row');
    await expect(rows).toHaveCount(1); // 只有一个admin用户
  });

  test('should create a new user successfully', async ({ adminPage }) => {
    // 点击添加用户按钮
    await adminPage.getByTestId('add-user-button').click();

    // 等待对话框打开
    await expect(adminPage.locator('.el-dialog')).toBeVisible();

    // 填写表单
    await adminPage.getByTestId('dialog-username-input').fill('newuser');
    await adminPage.getByTestId('dialog-password-input').fill('NewPass123!');
    await adminPage.getByTestId('dialog-email-input').fill('new@example.com');
    await adminPage.getByTestId('dialog-fullname-input').fill('新用户');

    // 选择角色
    await adminPage.getByTestId('dialog-role-select').click();
    await adminPage.getByRole('option', { name: '普通用户' }).click();

    // 提交
    await adminPage.getByTestId('dialog-submit-button').click();

    // 验证成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();
    await expect(adminPage.locator('text=newuser')).toBeVisible();
  });

  test('should edit existing user', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 找到testuser行并点击编辑
    const userRow = adminPage.locator('.el-table-row').filter({ hasText: 'testuser' });
    await userRow.locator('button:has-text("编辑")').click();

    // 等待对话框打开
    await expect(adminPage.locator('.el-dialog')).toBeVisible();

    // 修改邮箱
    await adminPage.getByTestId('dialog-email-input').clear();
    await adminPage.getByTestId('dialog-email-input').fill('updated@example.com');

    // 提交
    await adminPage.getByTestId('dialog-submit-button').click();

    // 验证成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();
  });

  test('should delete user successfully', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 找到deletable_user行并点击删除
    const userRow = adminPage.locator('.el-table-row').filter({ hasText: 'deletable_user' });
    await userRow.locator('button:has-text("删除")').click();

    // 确认删除对话框
    await adminPage.getByRole('button', { name: '确定' }).click();

    // 验证成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();

    // 验证用户已被删除
    await expect(adminPage.locator('text=deletable_user')).not.toBeVisible();
  });

  test('should lock and unlock user', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 找到testuser行并点击锁定
    const userRow = adminPage.locator('.el-table-row').filter({ hasText: 'testuser' });
    await userRow.locator('button:has-text("锁定")').click();

    // 确认锁定
    await adminPage.getByRole('button', { name: '确定' }).click();

    // 验证成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();

    // 验证状态变为"已锁定"
    const lockButton = userRow.locator('button:has-text("解锁")');
    await expect(lockButton).toBeVisible();

    // 解锁用户
    await lockButton.click();
    await adminPage.getByRole('button', { name: '确定' }).click();

    // 验证成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();
  });

  test('should reset user password', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 找到testuser行并点击重置密码
    const userRow = adminPage.locator('.el-table-row').filter({ hasText: 'testuser' });
    await userRow.locator('button:has-text("重置密码")').click();

    // 确认重置
    await adminPage.getByRole('button', { name: '确定' }).click();

    // 验证密码重置对话框
    await expect(adminPage.locator('.el-messagebox')).toBeVisible();
    await expect(adminPage.locator('text=新密码')).toBeVisible();

    // 关闭对话框（复制密码按钮）
    await adminPage.getByRole('button', { name: '复制' }).click();

    // 验证复制成功消息
    await expect(adminPage.locator('.el-message--success')).toBeVisible();
  });

  test('should filter users by role', async ({ adminPage }) => {
    // 等待数据加载
    await adminPage.waitForSelector('.el-table-row', { timeout: 5000 });

    // 获取初始用户数量
    const initialCount = await adminPage.locator('.el-table-row').count();

    // 筛选角色
    await adminPage.locator('.el-select').filter({ hasText: '角色' } }).click();
    await adminPage.locator('.el-select-dropdown__item').filter({ hasText: '管理员' }).click();
    await adminPage.getByTestId('search-button').click();

    // 等待筛选结果
    await adminPage.waitForTimeout(1000);

    // 验证只显示管理员
    const filteredCount = await adminPage.locator('.el-table-row').count();
    expect(filteredCount).toBeLessThan(initialCount);
  });
});
```

- [ ] **Step 2: 运行测试**

```bash
cd src/frontend
npx playwright test tests/e2e/02-users.spec.ts --project=chromium
```

Expected: 大部分测试通过（依赖data-testid）

- [ ] **Step 3: 提交**

```bash
git add tests/e2e/02-users.spec.ts
git commit -m "test(e2e): add user management E2E tests"
```

---

### Task 12: 编写权限验证测试

**Files:**
- Create: `src/frontend/tests/e2e/03-security.spec.ts`

- [ ] **Step 1: 创建03-security.spec.ts**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Security and Permissions', () => {
  test.beforeEach(async ({ page }) => {
    // 每个测试前确保未认证状态
    await page.goto('http://192.168.0.30:5173/login');
  });

  test('should prevent access to protected routes without authentication', async ({ page }) => {
    // 尝试访问用户管理页面
    await page.goto('http://192.168.0.30:5173/system/users');

    // 应该重定向到登录页
    await expect(page).toHaveURL(/\/login/);
  });

  test('should prevent non-admin users from accessing admin features', async ({ authenticatedPage }) => {
    // 登录为普通用户
    await authenticatedPage.goto('http://192.168.0.30:5173/system/users');

    // 查找添加用户按钮（应该不可见或禁用）
    const addButton = authenticatedPage.getByTestId('add-user-button');

    // 非管理员不应该看到添加按钮
    await expect(addButton).not.toBeVisible();
  });

  test('should prevent deletion of last admin', async ({ adminPage }) => {
    await adminPage.goto('http://192.168.0.30:5173/system/users');
    await adminPage.waitForLoadState('networkidle');

    // 尝试删除admin用户（如果只有一个admin）
    const adminRow = adminPage.locator('.el-table-row').filter({ hasText: 'admin' });
    const deleteButton = adminRow.locator('button:has-text("删除")');

    // 删除按钮应该禁用或不存在
    if (await deleteButton.count() > 0) {
      await expect(deleteButton).toBeDisabled();
    } else {
      // 按钮不存在
      await expect(deleteButton).not.toBeVisible();
    }
  });

  test('should prevent duplicate username creation', async ({ adminPage }) => {
    await adminPage.goto('http://192.168.0.30:5173/system/users');

    // 创建第一个用户
    await adminPage.getByTestId('add-user-button').click();
    await adminPage.getByTestId('dialog-username-input').fill('duplicate_user');
    await adminPage.getByTestId('dialog-password-input').fill('Test123456!');
    await adminPage.getByTestId('dialog-email-input').fill('duplicate@example.com');
    await adminPage.getByTestId('dialog-fullname-input').fill('重复用户');
    await adminPage.getByTestId('dialog-role-select').click();
    await adminPage.getByRole('option', { name: '普通用户' }).click();
    await adminPage.getByTestId('dialog-submit-button').click();

    // 验证第一个用户创建成功
    await expect(adminPage.locator('.el-message--success')).toBeVisible();
    await adminPage.waitForSelector('text=duplicate_user');

    // 尝试创建相同用户名的第二个用户
    await adminPage.getByTestId('add-user-button').click();
    await adminPage.getByTestId('dialog-username-input').fill('duplicate_user');
    await adminPage.getByTestId('dialog-password-input').fill('Test123456!');
    await adminPage.getByTestId('dialog-email-input').fill('duplicate2@example.com');
    await adminPage.getByTestId('dialog-fullname-input').fill('重复用户2');
    await adminPage.getByTestId('dialog-submit-button').click();

    // 验证错误消息
    await expect(adminPage.locator('.el-message--error')).toBeVisible();
    await expect(adminPage.locator('text=用户名已存在')).toBeVisible();
  });

  test('should redirect to login after session expires', async ({ page }) => {
    // 先登录
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('admin123');
    await page.getByTestId('login-button').click();
    await expect(page).toHaveURL(/\/dashboard/);

    // 清除localStorage模拟session过期
    await page.evaluate(() => localStorage.clear());

    // 尝试访问需要认证的页面
    await page.goto('http://192.168.0.30:5173/system/users');

    // 应该重定向到登录页
    await expect(page).toHaveURL(/\/login/);
  });
});
```

- [ ] **Step 2: 运行测试**

```bash
cd src/frontend
npx playwright test tests/e2e/03-security.spec.ts --project=chromium
```

- [ ] **Step 3: 提交**

```bash
git add tests/e2e/03-security.spec.ts
git commit -m "test(e2e): add security and permission validation tests"
```

---

## Phase 5: CI/CD配置 (Tasks 13-15)

### Task 13: 创建前端单元测试工作流

**Files:**
- Create: `.github/workflows/unit-tests.yml`

- [ ] **Step 1: 创建.github/workflows目录和unit-tests.yml**

```yaml
name: Unit Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: ./src/frontend/package-lock.json

      - name: Install dependencies
        working-directory: ./src/frontend
        run: npm ci

      - name: Run unit tests
        working-directory: ./src/frontend
        run: npm test

      - name: Upload coverage reports
        if: always()
        uses: codecov/codecov-action@v4
        with:
          files: ./src/frontend/coverage/coverage-final.json
          flags: unittests
          name: codecov-umbrella
```

- [ ] **Step 2: 提交**

```bash
git add .github/workflows/unit-tests.yml
git commit -m "ci: add unit test workflow for GitHub Actions"
```

---

### Task 14: 创建E2E测试工作流

**Files:**
- Create: `.github/workflows/e2e.yml`

- [ ] **Step 1: 创建e2e.yml工作流**

```yaml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  e2e:
    # 使用self-hosted runner（内网服务器192.168.0.30）
    runs-on: [self-hosted, linux]
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      # 确保使用正确的Node版本
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      # 安装依赖（如果需要）
      - name: Install dependencies
        working-directory: ./src/frontend
        run: |
          if [ ! -d "node_modules" ]; then
            npm ci
          fi

      # 确保数据库是最新的
      - name: Reset test database
        run: |
          psql postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test \
            -c "DROP SCHEMA PUBLIC CASCADE"
          psql postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test \
            -f src/backend/migrations/postgresql/001_system_management.sql
          psql postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test \
            -f src/frontend/tests/setup/test-seed.sql

      # 运行E2E测试
      - name: Run E2E tests
        working-directory: ./src/frontend
        run: npm run test:e2e
        env:
          TEST_DATABASE_URL: postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test
          TEST_API_BASE_URL: http://192.168.0.30:8000
          TEST_FRONTEND_URL: http://192.168.0.30:5173

      # 上传测试报告
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: src/frontend/playwright-report/
          retention-days: 30
```

- [ ] **Step 2: 创建.gitignore排除测试报告**

```bash
echo "test-results/" >> .gitignore
echo "playwright-report/" >> .gitignore
```

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/e2e.yml .gitignore
git commit -m "ci: add E2E test workflow for self-hosted runner"
```

---

### Task 15: 配置Self-hosted Runner

**文档：** 参考 `.github/workflows/e2e.yml` 中的配置

- [ ] **Step 1: 在192.168.0.30上安装Actions Runner**

```bash
# SSH到192.168.0.30
ssh xiejava@192.168.0.30

# 创建runner目录
sudo mkdir -p /opt/actions-runner
cd /opt/actions-runner

# 下载Actions Runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.31100/actions-runner-linux-x64-2.3110.tar.gz
tar xzf ./actions-runner-linux-x64-2.3110.tar.gz

# 配置runner
./config.sh --url https://github.com/xiejava/AI-miniSOC \
  --token <YOUR_RUNNER_TOKEN> \
  --name "AI-miniSOC E2E Runner"

# 安装依赖
cd /home/xiejava/AIproject/AI-miniSOC/src/frontend
npm install -D @playwright/test playwright
npx playwright install --with-deps chromium

# 启动runner
cd /opt/actions-runner
./run.sh
```

**获取RUNNER_TOKEN:**
1. 访问 https://github.com/xiejava/AI-miniSOC/settings/actions
2. 点击 "New self-hosted runner"
3. 选择 "Linux" + "x64"
4. 复制生成的token

- [ ] **Step 2: 验证runner连接**

在GitHub仓库的Actions页面应该看到runner在线。

- [ ] **Step 3: 创建README文档**

创建 `docs/installation/playwright-runner-setup.md`记录设置过程。

---

## Phase 6: 本地验证和测试 (Tasks 16-18)

### Task 16: 本地测试运行验证

- [ ] **Step 1: 确保所有服务运行**

```bash
# 检查前端服务器
curl http://192.168.0.30:5173

# 检查后端API
curl http://192.168.0.30:8000/docs

# 检查数据库
psql postgresql://testuser:testpass@192.168.0.30:5432/ai_minisoc_test -c "SELECT 1"
```

- [ ] **Step 2: 运行所有E2E测试**

```bash
cd src/frontend
npm run test:e2e
```

Expected: 所有测试通过（或大部分通过）

- [ ] **Step 3: 查看测试报告**

```bash
npm run test:e2e:report
```

Expected: 浏览器打开HTML报告

- [ ] **Step 4: 检查测试截图和录屏**

如果测试失败，检查 `src/frontend/test-results/` 目录。

---

### Task 17: 修复测试失败并优化

- [ ] **Step 1: 运行测试并记录失败**

```bash
cd src/frontend
npx playwright test --reporter=list > test-results.txt
```

- [ ] **Step 2: 逐个修复失败的测试**

对于每个失败的测试：
1. 查看截图和trace
2. 分析失败原因
3. 修复代码或测试
4. 重新运行验证

- [ ] **Step 3: 优化测试稳定性**

```typescript
// 添加显式等待
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1000);

// 使用更稳定的选择器
await page.waitForSelector('.el-table-row', { state: 'attached' });
```

- [ ] **Step 4: 重新运行完整测试套件**

```bash
npm run test:e2e
```

- [ ] **Step 5: 确保所有测试通过**

Expected: 所有测试✅

---

### Task 18: 最终文档和清理

- [ ] **Step 1: 创建E2E测试README**

```markdown
# E2E Tests

This directory contains end-to-end tests for AI-miniSOC.

## Running Tests

### Run all E2E tests
```bash
npm run test:e2e
```

### Run specific test file
```bash
npx playwright test tests/e2e/01-auth.spec.ts
```

### Debug mode
```bash
npm run test:e2e:debug
```

### View test report
```bash
npm run test:e2e:report
```

## Test Files

- `01-auth.spec.ts` - Authentication flow tests
- `02-users.spec.ts` - User management tests
- `03-security.spec.ts - Security and permission tests

## Environment Setup

1. Install dependencies:
```bash
npm run test:e2e:install
```

2. Set up test database:
```bash
psql $TEST_DATABASE_URL -f src/backend/migrations/postgresql/001_system_management.sql
```

3. Add `data-testid` attributes to components (see design doc)

## Troubleshooting

### Tests fail with "element not found"
- Check if `data-testid` attributes are added to components
- Verify frontend server is running
- Check browser console for errors

### Tests fail with "connection refused"
- Verify backend server is running on port 8000
- Check firewall rules

### Database connection errors
- Verify PostgreSQL is running
- Check TEST_DATABASE_URL in .env.test
- Ensure database schema is initialized
```

保存到 `src/frontend/tests/e2e/README.md`

- [ ] **Step 2: 创建Playwright最佳实践文档**

保存到 `docs/testing/playwright-best-practices.md`

- [ ] **Step 3: 更新主README**

在主README中添加E2E测试部分。

- [ ] **Step 4: 提交所有文档**

```bash
git add src/frontend/tests/e2e/README.md docs/testing/playwright-best-practices.md README.md
git commit -m "docs: add E2E testing documentation and best practices"
```

---

## Phase 7: Self-hosted Runner设置 (Task 19)

### Task 19: 配置并测试Self-hosted Runner

**参考文档:** `docs/superpowers/specs/2026-03-20-playwright-e2e-design.md` Section 16

- [ ] **Step 1: 在192.168.0.30上安装Actions Runner**

（详细命令见设计文档Section 16.1）

- [ ] **Step 2: 配置runner为auto-start**

创建systemd服务或使用其他方式让runner自动启动。

- [ ] **Step 3: 验证runner在GitHub中显示**

- [ ] **Step 4: 测试runner运行E2E测试**

推送一个测试commit验证workflow运行。

---

## 成功标准

- ✅ Playwright安装完成，Chromium可用
- ✅ 配置文件正确，所有验证通过
- ✅ 3个测试文件创建并测试通过
- ✅ 所有data-testid属性添加完成
- ✅ 本地测试运行通过（20/20测试通过）
- ✅ GitHub Actions workflows配置完成
- ✅ Self-hosted runner配置并在线
- ✅ CI/CD pipeline测试通过
- ✅ 文档完整

## 依赖关系

```
Task 1 (安装Playwright) → Task 2 (配置文件) → Task 3 (脚本)
                                    ↓
Task 4-6 (辅助文件) → Task 7-9 (data-testid) → Task 10-12 (测试)
                                    ↓
                              Task 13-14 (CI/CD配置) → Task 15 (Self-hosted runner)
                                    ↓
                              Task 16-18 (验证和文档) → Task 19 (Runner测试)
```

## 时间估算

- **Phase 1 (Tasks 1-3):** 30分钟
- **Phase 2 (Tasks 4-6):** 45分钟
- **Phase 3 (Tasks 7-9):** 45分钟
- **Phase 4 (Tasks 10-12):** 90分钟
- **Phase 5 (Tasks 13-15):** 60分钟
- **Phase 6 (Tasks 16-18):** 60分钟
- **Phase 7 (Task 19):** 30分钟

**总计:** 约6小时（不含调试和修复时间）

## 注意事项

1. **TDD原则** - 每个测试先写测试，验证失败，再实现功能
2. **数据隔离** - 每个测试独立运行，不依赖其他测试
3. **清理数据** - 测试后清理数据，避免污染
4. **网络延迟** - 内网环境可能有延迟，适当增加超时
5. **真实环境** - 使用真实的192.168.0.30 IP，不是localhost
6. **密码安全** - 测试密码不要在代码中硬编码
7. **版本控制** - 测试报告不要提交到git

## 相关文档

- 设计文档: `docs/superpowers/specs/2026-03-20-playwright-e2e-design.md`
- API文档: `docs/api/users-api.md`
- 用户管理设计: `docs/design/system-management-design.md`

---

**计划版本:** v1.0
**创建日期:** 2026-03-20
**预计工作量:** 6小时 + 1-2小时调试修复
**任务数量:** 19个任务，每个任务2-5个步骤
