import { defineConfig, devices } from '@playwright/test';
const baseURL = process.env.ONTARA_TEST_BASE_URL || 'http://127.0.0.1:3000';
export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { actionTimeout: 12_000, navigationTimeout: 30_000, baseURL, ...devices['Desktop Chrome'], channel: 'chrome', trace: 'retain-on-failure' },
  webServer: process.env.ONTARA_TEST_BASE_URL ? undefined : { command: 'npm run dev -- --port 3000', url: 'http://127.0.0.1:3000/api/health', reuseExistingServer: true, timeout: 90_000 },
});
