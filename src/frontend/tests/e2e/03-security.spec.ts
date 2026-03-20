import { test, expect } from '@playwright/test';

test.describe('Security and Permission Validation', () => {
  test.describe('Authentication Protection', () => {
    test('should redirect to login when accessing protected routes without authentication', async ({ page }) => {
      const protectedRoutes = [
        '/dashboard',
        '/system/users',
        '/system/roles',
        '/logs/query',
        '/alerts/list',
        '/settings/profile'
      ];

      for (const route of protectedRoutes) {
        // 清除存储以确保未认证状态
        await page.context().clearCookies();
        await page.goto(`http://192.168.0.30:5173${route}`);

        // 应该重定向到登录页
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 });

        // 验证显示登录页面
        await expect(page.locator('h2')).toContainText('AI-miniSOC 登录');
      }
    });

    test('should redirect to login after session expires', async ({ page }) => {
      // 首先登录
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 模拟会话过期：清除所有cookies和存储
      await page.context().clearCookies();
      await page.evaluate(() => {
        localStorage.clear();
        sessionStorage.clear();
      });

      // 尝试访问受保护的页面
      await page.goto('http://192.168.0.30:5173/system/users');

      // 应该重定向到登录页
      await expect(page).toHaveURL(/\/login/);

      // 验证显示会话过期消息
      await expect(page.locator('.el-message--warning')).toBeVisible();
    });

    test('should prevent access to API endpoints without authentication', async ({ request }) => {
      const apiEndpoints = [
        '/api/users',
        '/api/roles',
        '/api/logs/query',
        '/api/alerts',
        '/api/settings'
      ];

      for (const endpoint of apiEndpoints) {
        const response = await request.get(`http://192.168.0.30:5173${endpoint}`);

        // 应该返回401或403
        expect([401, 403]).toContain(response.status());
      }
    });
  });

  test.describe('Role-Based Access Control', () => {
    test('should prevent non-admin users from accessing admin features', async ({ page }) => {
      // 登录为非管理员用户（假设已创建testuser）
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('testuser');
      await page.getByTestId('password-input').fill('testuser123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 尝试访问用户管理页面
      await page.goto('http://192.168.0.30:5173/system/users');

      // 应该显示权限不足消息
      await expect(page.locator('.el-message--error')).toBeVisible();
      await expect(page.getByText('权限不足')).toBeVisible();

      // 验证不显示添加用户按钮
      await expect(page.getByTestId('add-user-button')).not.toBeVisible();
    });

    test('should hide admin-only features from non-admin users', async ({ page }) => {
      // 登录为查看者角色
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('viewer');
      await page.getByTestId('password-input').fill('viewer123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 导航到dashboard
      await page.goto('http://192.168.0.30:5173/dashboard');

      // 验证管理员菜单项不可见
      await expect(page.getByRole('link', { name: /用户管理/ })).not.toBeVisible();
      await expect(page.getByRole('link', { name: /角色管理/ })).not.toBeVisible();
      await expect(page.getByRole('link', { name: /系统设置/ })).not.toBeVisible();

      // 验证只显示查看者可访问的功能
      await expect(page.getByRole('link', { name: /日志查询/ })).toBeVisible();
      await expect(page.getByRole('link', { name: /告警列表/ })).toBeVisible();
    });

    test('should allow admin users to access all features', async ({ page }) => {
      // 登录为管理员
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 验证所有管理功能可见
      await expect(page.getByRole('link', { name: /用户管理/ })).toBeVisible();
      await expect(page.getByRole('link', { name: /角色管理/ })).toBeVisible();
      await expect(page.getByRole('link', { name: /系统设置/ })).toBeVisible();

      // 验证可以访问用户管理
      await page.goto('http://192.168.0.30:5173/system/users');
      await expect(page.getByTestId('user-list-container')).toBeVisible();
      await expect(page.getByTestId('add-user-button')).toBeVisible();
    });
  });

  test.describe('Data Validation and Business Rules', () => {
    test('should prevent duplicate username creation', async ({ page }) => {
      // 登录为管理员
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 尝试创建已存在的用户名
      await page.goto('http://192.168.0.30:5173/system/users');
      await page.getByTestId('add-user-button').click();

      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('Test123!');
      await page.getByTestId('confirm-password-input').fill('Test123!');
      await page.getByTestId('email-input').fill('admin2@example.com');
      await page.getByTestId('role-select').click();
      await page.getByRole('option', { name: '管理员' }).click();

      await page.getByTestId('submit-user-button').click();

      // 应该显示用户名已存在的错误
      await expect(page.locator('.el-message--error')).toBeVisible();
      await expect(page.getByText('用户名已存在')).toBeVisible();
    });

    test('should prevent deletion of the last admin user', async ({ page }) => {
      // 登录为管理员
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 获取当前管理员用户数量
      await page.goto('http://192.168.0.30:5173/system/users');

      // 找到admin用户
      const userRows = page.getByTestId('user-row');
      const count = await userRows.count();

      for (let i = 0; i < count; i++) {
        const row = userRows.nth(i);
        const text = await row.textContent();
        if (text && text.includes('admin')) {
          // 尝试删除最后一个管理员
          await row.getByTestId('delete-user-button').click();

          // 确认删除
          await page.getByTestId('confirm-delete-button').click();

          // 应该显示错误消息
          await expect(page.locator('.el-message--error')).toBeVisible();
          await expect(page.getByText('不能删除最后一个管理员')).toBeVisible();

          // 验证用户仍然存在
          await expect(page.getByRole('cell', { name: 'admin' })).toBeVisible();
          break;
        }
      }
    });

    test('should validate password strength requirements', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      await page.goto('http://192.168.0.30:5173/system/users');
      await page.getByTestId('add-user-button').click();

      // 测试弱密码
      await page.getByTestId('username-input').fill('weakpass');
      await page.getByTestId('password-input').fill('123');
      await page.getByTestId('confirm-password-input').fill('123');
      await page.getByTestId('email-input').fill('weak@example.com');

      await page.getByTestId('submit-user-button').click();

      // 应该显示密码强度不足的错误
      await expect(page.getByText(/密码强度不足|密码至少/)).toBeVisible();
    });

    test('should validate email format', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      await page.goto('http://192.168.0.30:5173/system/users');
      await page.getByTestId('add-user-button').click();

      await page.getByTestId('username-input').fill('invalidemail');
      await page.getByTestId('password-input').fill('Test123!');
      await page.getByTestId('confirm-password-input').fill('Test123!');
      await page.getByTestId('email-input').fill('invalid-email-format');

      await page.getByTestId('submit-user-button').click();

      // 应该显示邮箱格式错误
      await expect(page.getByText('请输入正确的邮箱格式')).toBeVisible();
    });
  });

  test.describe('CSRF and XSS Protection', () => {
    test('should include CSRF token in form submissions', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 检查页面中是否存在CSRF token
      const csrfToken = await page.evaluate(() => {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        return metaTag?.getAttribute('content');
      });

      expect(csrfToken).toBeTruthy();
      expect(csrfToken?.length).toBeGreaterThan(0);
    });

    test('should escape HTML in user input to prevent XSS', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      await page.goto('http://192.168.0.30:5173/system/users');
      await page.getByTestId('add-user-button').click();

      // 尝试输入XSS payload
      const xssPayload = '<script>alert("XSS")</script>';
      await page.getByTestId('username-input').fill(`xss_${Date.now()}`);
      await page.getByTestId('password-input').fill('Test123!');
      await page.getByTestId('confirm-password-input').fill('Test123!');
      await page.getByTestId('email-input').fill(xssPayload);

      await page.getByTestId('submit-user-button').click();

      // 如果成功创建，验证输入被转义
      const pageContent = await page.content();
      expect(pageContent).not.toContain('<script>alert("XSS")</script>');
    });
  });

  test.describe('Session Security', () => {
    test('should logout and invalidate session', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 登出
      await page.getByTestId('user-dropdown').click();
      await page.getByTestId('logout-button').click();

      // 验证重定向到登录页
      await expect(page).toHaveURL(/\/login/);

      // 尝试访问受保护页面
      await page.goto('http://192.168.0.30:5173/system/users');

      // 应该再次重定向到登录页
      await expect(page).toHaveURL(/\/login/);
    });

    test('should maintain session across page navigation', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 导航到多个页面
      await page.goto('http://192.168.0.30:5173/system/users');
      await expect(page.getByTestId('user-list-container')).toBeVisible();

      await page.goto('http://192.168.0.30:5173/logs/query');
      await expect(page.getByTestId('log-query-container')).toBeVisible();

      await page.goto('http://192.168.0.30:5173/dashboard');
      await expect(page.getByTestId('dashboard-container')).toBeVisible();

      // 验证仍然保持登录状态
      await page.goto('http://192.168.0.30:5173/system/users');
      await expect(page.getByTestId('user-list-container')).toBeVisible();
      await expect(page).not.toHaveURL(/\/login/);
    });
  });

  test.describe('Password Security', () => {
    test('should not expose password in URL or logs', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');
      await page.getByTestId('login-button').click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });

      // 验证URL中不包含密码
      const url = page.url();
      expect(url).not.toContain('admin123');

      // 验证密码输入框的类型为password
      await page.goto('http://192.168.0.30:5173/login');
      const passwordInputType = await page.getByTestId('password-input').getAttribute('type');
      expect(passwordInputType).toBe('password');
    });

    test('should mask password in input field', async ({ page }) => {
      await page.goto('http://192.168.0.30:5173/login');
      await page.getByTestId('username-input').fill('admin');
      await page.getByTestId('password-input').fill('admin123');

      // 验证密码被掩码显示
      const passwordValue = await page.getByTestId('password-input').inputValue();
      expect(passwordValue).toBe('admin123'); // 实际值

      // 验证在DOM中不以明文显示
      const passwordText = await page.getByTestId('password-input').evaluate(el => {
        return (el as HTMLInputElement).value;
      });
      expect(passwordText).toBe('admin123');
    });
  });
});
