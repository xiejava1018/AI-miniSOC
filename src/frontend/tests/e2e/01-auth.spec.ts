import { test, expect } from '@playwright/test';

// 使用新的浏览器上下文，确保每个测试都从干净状态开始
test.use({ storageState: undefined });

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // 每个测试前回到登录页
    await page.goto('http://192.168.0.128:5173/login');
  });

  test('should display login page', async ({ page }) => {
    // 验证页面标题 - 使用更具体的选择器
    await expect(page.locator('.login-card h2')).toContainText('AI-miniSOC 登录');

    // 验证表单元素存在 - 使用label text定位
    await expect(page.getByRole('textbox', { name: /用户名/ })).toBeVisible();
    await expect(page.getByRole('textbox', { name: /密码/ })).toBeVisible();
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible();
  });

  test('should login successfully with valid admin credentials', async ({ page }) => {
    // 输入凭据 - 使用label text定位
    await page.getByRole('textbox', { name: /用户名/ }).fill('admin');
    await page.getByRole('textbox', { name: /密码/ }).fill('admin123');

    // 点击登录
    await page.getByRole('button', { name: '登录' }).click();

    // 验证跳转到dashboard
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });
  });

  test('should show error message with invalid credentials', async ({ page }) => {
    // 输入错误的凭据
    await page.getByRole('textbox', { name: /用户名/ }).fill('admin');
    await page.getByRole('textbox', { name: /密码/ }).fill('wrongpassword');

    // 点击登录
    await page.getByRole('button', { name: '登录' }).click();

    // 验证错误消息 - Element Plus使用.el-message类
    await expect(page.locator('.el-message')).toBeVisible({ timeout: 3000 });
  });

  test('should show validation error for empty fields', async ({ page }) => {
    // 不输入任何内容，直接点击登录
    await page.getByRole('button', { name: '登录' }).click();

    // 验证表单验证
    await expect(page.getByText('请输入用户名')).toBeVisible();
  });

  test('should redirect to login when not authenticated', async ({ page, context }) => {
    // 清除所有cookies和存储
    await context.clearCookies();
    await page.goto('http://192.168.0.128:5173');

    // 清除localStorage
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    // 尝试访问需要认证的页面
    await page.goto('http://192.168.0.128:5173/system/users');

    // 验证：应该重定向到登录页或显示登录页面元素
    const url = page.url();
    const hasLoginHeading = await page.locator('.login-card h2').isVisible().catch(() => false);
    const hasLoginButton = await page.getByRole('button', { name: '登录' }).isVisible().catch(() => false);

    // 如果URL包含/login，或者能看到登录页面的标题或按钮，就认为测试通过
    expect(url.includes('/login') || hasLoginHeading || hasLoginButton).toBeTruthy();
  });
});
