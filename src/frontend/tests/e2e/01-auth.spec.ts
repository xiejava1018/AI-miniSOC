import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // 每个测试前回到登录页
    await page.goto('http://192.168.0.42:5173/login');
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
    await page.goto('http://192.168.0.42:5173/system/users');

    // 应该重定向到登录页
    await expect(page).toHaveURL(/\/login/);
  });
});
