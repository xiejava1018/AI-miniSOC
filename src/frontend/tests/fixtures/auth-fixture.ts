// tests/fixtures/auth-fixture.ts
import { test as base } from '@playwright/test';
import type { Page, APIRequestContext } from '@playwright/test';
import { loginAsUser } from '../helpers/auth-helpers';
import { getTestCredentials } from '../helpers/test-data';

/**
 * Extended test fixture with authentication support
 *
 * Provides pre-authenticated page instances and API context for testing.
 *
 * @example
 * ```typescript
 * import { test, expect } from './fixtures/auth-fixture';
 *
 * test('user can access dashboard', async ({ authenticatedPage }) => {
 *   await authenticatedPage.goto('/dashboard');
 *   await expect(authenticatedPage.getByText('Welcome')).toBeVisible();
 * });
 *
 * test('admin can manage users', async ({ adminPage }) => {
 *   await adminPage.goto('/users');
 *   await expect(adminPage.getByRole('button', { name: 'Add User' })).toBeVisible();
 * });
 *
 * test('direct API call', async ({ apiContext }) => {
 *   const response = await apiContext.get('/api/users');
 *   expect(response.ok()).toBeTruthy();
 * });
 * ```
 */
export const test = base.extend<{
  authenticatedPage: Page;
  adminPage: Page;
  apiContext: APIRequestContext;
}>({
  /**
   * Authenticated page fixture for regular user
   *
   * Provides a Page instance that is already logged in as a regular user.
   * The fixture handles login before yielding the page and ensures the
   * login was successful by waiting for the dashboard URL.
   *
   * @param page - Playwright page object
   * @returns Page instance authenticated as regular user
   *
   * @example
   * ```typescript
   * test('regular user test', async ({ authenticatedPage }) => {
   *   // Page is already logged in as testuser
   *   await authenticatedPage.goto('/profile');
   *   // Test regular user functionality...
   * });
   * ```
   */
  authenticatedPage: async ({ page }, use) => {
    const credentials = getTestCredentials().regularUser;
    await loginAsUser(page, credentials.username, credentials.password);
    await use(page);
  },

  /**
   * Authenticated page fixture for admin user
   *
   * Provides a Page instance that is already logged in as an admin user.
   * The fixture handles login before yielding the page and ensures the
   * login was successful by waiting for the dashboard URL.
   *
   * @param page - Playwright page object
   * @returns Page instance authenticated as admin user
   *
   * @example
   * ```typescript
   * test('admin user test', async ({ adminPage }) => {
   *   // Page is already logged in as admin
   *   await adminPage.goto('/admin/users');
   *   // Test admin functionality...
   * });
   * ```
   */
  adminPage: async ({ page }, use) => {
    const credentials = getTestCredentials().admin;
    await loginAsUser(page, credentials.username, credentials.password);
    await use(page);
  },

  /**
   * API request context fixture
   *
   * Provides an APIRequestContext for making direct HTTP API calls
   * without going through the UI. Useful for testing API endpoints
   * directly or setting up test data via API.
   *
   * The context is automatically disposed after the test completes.
   *
   * @param playwright - Playwright instance
   * @returns APIRequestContext for making HTTP requests
   *
   * @example
   * ```typescript
   * test('API endpoint test', async ({ apiContext }) => {
   *   // Direct API call without UI
   *   const response = await apiContext.post('/api/users', {
   *     data: { username: 'newuser', password: 'pass123' }
   *   });
   *   expect(response.ok()).toBeTruthy();
   * });
   * ```
   */
  apiContext: async ({ playwright }, use) => {
    const apiContext = await playwright.request.newContext();
    await use(apiContext);

    // Cleanup: dispose of the API context
    await apiContext.dispose();
  },
});
