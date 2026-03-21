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
