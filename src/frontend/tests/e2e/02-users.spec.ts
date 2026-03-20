import { test, expect } from '@playwright/test';

test.describe('User Management', () => {
  test.beforeEach(async ({ page }) => {
    // 登录为管理员
    await page.goto('http://192.168.0.128:5173/login');
    await page.getByTestId('username-input').fill('admin');
    await page.getByTestId('password-input').fill('admin123');
    await page.getByTestId('login-button').click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });
  });

  test('should display user list page', async ({ page }) => {
    // 导航到用户管理页面
    await page.goto('http://192.168.0.128:5173/system/users');

    // 验证页面标题
    await expect(page.locator('h1')).toContainText('用户管理');

    // 验证用户列表容器存在
    await expect(page.getByTestId('user-list-container')).toBeVisible();
  });

  test('should display list of users', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 等待用户列表加载
    await expect(page.getByTestId('user-list-container')).toBeVisible();

    // 验证用户列表不为空
    const userRows = page.getByTestId('user-row');
    await expect(userRows.first()).toBeVisible();

    // 验证至少有默认管理员用户
    await expect(page.getByRole('cell', { name: 'admin' })).toBeVisible();
  });

  test('should search users by username', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 使用搜索框
    await page.getByTestId('user-search-input').fill('admin');

    // 等待搜索结果
    await page.waitForTimeout(500);

    // 验证搜索结果
    const userRows = page.getByTestId('user-row');
    const count = await userRows.count();

    expect(count).toBeGreaterThan(0);

    // 验证所有结果都包含搜索词
    for (let i = 0; i < count; i++) {
      const row = userRows.nth(i);
      await expect(row).toContainText('admin', { ignoreCase: true });
    }
  });

  test('should create a new user successfully', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 点击添加用户按钮
    await page.getByTestId('add-user-button').click();

    // 验证对话框打开
    await expect(page.getByTestId('user-dialog')).toBeVisible();

    // 填写用户信息
    const timestamp = Date.now();
    const newUsername = `testuser_${timestamp}`;

    await page.getByTestId('username-input').fill(newUsername);
    await page.getByTestId('password-input').fill('Test123!');
    await page.getByTestId('confirm-password-input').fill('Test123!');
    await page.getByTestId('email-input').fill(`test${timestamp}@example.com`);
    await page.getByTestId('phone-input').fill('13800138000');

    // 选择角色
    await page.getByTestId('role-select').click();
    await page.getByRole('option', { name: '查看者' }).click();

    // 提交表单
    await page.getByTestId('submit-user-button').click();

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible();

    // 验证对话框关闭
    await expect(page.getByTestId('user-dialog')).not.toBeVisible();

    // 验证新用户出现在列表中
    await expect(page.getByRole('cell', { name: newUsername })).toBeVisible();
  });

  test('should edit existing user', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 找到第一个非admin用户
    const userRows = page.getByTestId('user-row');
    const firstRow = userRows.first();

    // 点击编辑按钮
    await firstRow.getByTestId('edit-user-button').click();

    // 验证对话框打开
    await expect(page.getByTestId('user-dialog')).toBeVisible();

    // 修改邮箱
    const newEmail = `updated_${Date.now()}@example.com`;
    await page.getByTestId('email-input').clear();
    await page.getByTestId('email-input').fill(newEmail);

    // 提交表单
    await page.getByTestId('submit-user-button').click();

    // 验证成功消息
    await expect(page.locator('.el-message--success')).toBeVisible();

    // 验证邮箱已更新（刷新页面）
    await page.reload();
    await expect(page.getByText(newEmail)).toBeVisible();
  });

  test('should delete user successfully', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 首先创建一个测试用户
    await page.getByTestId('add-user-button').click();
    const timestamp = Date.now();
    const testUsername = `delete_test_${timestamp}`;

    await page.getByTestId('username-input').fill(testUsername);
    await page.getByTestId('password-input').fill('Test123!');
    await page.getByTestId('confirm-password-input').fill('Test123!');
    await page.getByTestId('email-input').fill(`delete${timestamp}@example.com`);
    await page.getByTestId('role-select').click();
    await page.getByRole('option', { name: '查看者' }).click();
    await page.getByTestId('submit-user-button').click();

    // 等待用户创建成功
    await expect(page.getByRole('cell', { name: testUsername })).toBeVisible();

    // 刷新页面以确保用户列表更新
    await page.reload();
    await expect(page.getByTestId('user-list-container')).toBeVisible();

    // 找到刚创建的用户并删除
    const userRows = page.getByTestId('user-row');
    const count = await userRows.count();

    for (let i = 0; i < count; i++) {
      const row = userRows.nth(i);
      const text = await row.textContent();
      if (text && text.includes(testUsername)) {
        await row.getByTestId('delete-user-button').click();

        // 确认删除
        await page.getByTestId('confirm-delete-button').click();

        // 验证成功消息
        await expect(page.locator('.el-message--success')).toBeVisible();

        // 验证用户已从列表中删除
        await expect(page.getByRole('cell', { name: testUsername })).not.toBeVisible();
        break;
      }
    }
  });

  test('should lock and unlock user', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 创建一个测试用户
    await page.getByTestId('add-user-button').click();
    const timestamp = Date.now();
    const testUsername = `lock_test_${timestamp}`;

    await page.getByTestId('username-input').fill(testUsername);
    await page.getByTestId('password-input').fill('Test123!');
    await page.getByTestId('confirm-password-input').fill('Test123!');
    await page.getByTestId('email-input').fill(`lock${timestamp}@example.com`);
    await page.getByTestId('role-select').click();
    await page.getByRole('option', { name: '查看者' }).click();
    await page.getByTestId('submit-user-button').click();

    // 等待用户创建并刷新
    await page.reload();
    await expect(page.getByTestId('user-list-container')).toBeVisible();

    // 找到用户并锁定
    const userRows = page.getByTestId('user-row');
    const count = await userRows.count();

    for (let i = 0; i < count; i++) {
      const row = userRows.nth(i);
      const text = await row.textContent();
      if (text && text.includes(testUsername)) {
        // 锁定用户
        await row.getByTestId('lock-user-button').click();
        await expect(page.locator('.el-message--success')).toBeVisible();

        // 验证状态变为"已锁定"
        await expect(row.getByTestId('user-status')).toContainText('已锁定');

        // 解锁用户
        await row.getByTestId('unlock-user-button').click();
        await expect(page.locator('.el-message--success')).toBeVisible();

        // 验证状态变为"正常"
        await expect(row.getByTestId('user-status')).toContainText('正常');
        break;
      }
    }
  });

  test('should reset user password', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 创建一个测试用户
    await page.getByTestId('add-user-button').click();
    const timestamp = Date.now();
    const testUsername = `reset_test_${timestamp}`;

    await page.getByTestId('username-input').fill(testUsername);
    await page.getByTestId('password-input').fill('Test123!');
    await page.getByTestId('confirm-password-input').fill('Test123!');
    await page.getByTestId('email-input').fill(`reset${timestamp}@example.com`);
    await page.getByTestId('role-select').click();
    await page.getByRole('option', { name: '查看者' }).click();
    await page.getByTestId('submit-user-button').click();

    // 等待用户创建并刷新
    await page.reload();
    await expect(page.getByTestId('user-list-container')).toBeVisible();

    // 找到用户并重置密码
    const userRows = page.getByTestId('user-row');
    const count = await userRows.count();

    for (let i = 0; i < count; i++) {
      const row = userRows.nth(i);
      const text = await row.textContent();
      if (text && text.includes(testUsername)) {
        // 点击重置密码按钮
        await row.getByTestId('reset-password-button').click();

        // 验证重置密码对话框打开
        await expect(page.getByTestId('reset-password-dialog')).toBeVisible();

        // 输入新密码
        const newPassword = 'NewTest123!';
        await page.getByTestId('new-password-input').fill(newPassword);
        await page.getByTestId('confirm-new-password-input').fill(newPassword);

        // 提交
        await page.getByTestId('confirm-reset-button').click();

        // 验证成功消息
        await expect(page.locator('.el-message--success')).toBeVisible();
        break;
      }
    }
  });

  test('should filter users by role', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 使用角色筛选器
    await page.getByTestId('role-filter-select').click();

    // 选择"管理员"角色
    await page.getByRole('option', { name: '管理员' }).click();

    // 等待筛选结果
    await page.waitForTimeout(500);

    // 验证结果
    const userRows = page.getByTestId('user-row');
    const count = await userRows.count();

    expect(count).toBeGreaterThan(0);

    // 验证所有显示的用户都是管理员
    for (let i = 0; i < count; i++) {
      const row = userRows.nth(i);
      await expect(row.getByTestId('user-role')).toContainText('管理员');
    }
  });

  test('should show validation errors when creating user with invalid data', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 点击添加用户按钮
    await page.getByTestId('add-user-button').click();

    // 验证对话框打开
    await expect(page.getByTestId('user-dialog')).toBeVisible();

    // 不填写任何字段，直接提交
    await page.getByTestId('submit-user-button').click();

    // 验证表单验证错误
    await expect(page.getByText('请输入用户名')).toBeVisible();
    await expect(page.getByText('请输入密码')).toBeVisible();
  });

  test('should show error when passwords do not match', async ({ page }) => {
    await page.goto('http://192.168.0.128:5173/system/users');

    // 点击添加用户按钮
    await page.getByTestId('add-user-button').click();

    // 填写不匹配的密码
    await page.getByTestId('username-input').fill('testuser');
    await page.getByTestId('password-input').fill('Password123!');
    await page.getByTestId('confirm-password-input').fill('DifferentPassword123!');

    // 提交表单
    await page.getByTestId('submit-user-button').click();

    // 验证错误消息
    await expect(page.getByText('两次输入的密码不一致')).toBeVisible();
  });
});
