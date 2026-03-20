import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Testing Configuration
 *
 * Configured for AI-miniSOC local E2E testing (192.168.0.128)
 *
 * Test platform runs on local machine:
 * - Frontend: http://192.168.0.128:5173
 * - API: http://192.168.0.128:8000
 * - Database: postgresql://192.168.0.42:5432/AI-miniSOC-testdb (remote)
 */
export default defineConfig({
  // Test directory
  testDir: './tests/e2e',

  // Run tests in parallel
  fullyParallel: true,

  // Retry on failure (no retries in CI)
  retries: process.env.CI ? 0 : 1,

  // Limit workers in CI
  workers: process.env.CI ? 1 : 2,

  // Test timeout
  timeout: 30000,

  // Reporter configuration
  reporter: [
    ['html'],
    ['json', { outputFile: 'test-results/results.json' }]
  ],

  // Browser projects
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Base URL for tests (local E2E testing platform)
        baseURL: 'http://192.168.0.128:5173',
        // Trace on first retry
        trace: 'on-first-retry',
        // Screenshot only on failure
        screenshot: 'only-on-failure',
        // Retain video on failure
        video: 'retain-on-failure',
        // Launch options for host resolvable rules
        launchOptions: {
          args: [
            '--host-resolver-rules=MAP localhost 127.0.0.1,MAP 192.168.0.128 192.168.0.128'
          ]
        }
      },
    },
  ],

  /*
   * WebServer configuration is commented out for local E2E testing.
   *
   * Servers run on 192.168.0.128 (local machine) with remote database on 192.168.0.42.
   *
   * If you need to run tests with local servers, uncomment and configure below:
   */
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:5173',
  //   timeout: 120000,
  //   reuseExistingServer: !process.env.CI,
  // },
});
