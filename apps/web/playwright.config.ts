import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { actionTimeout: 12_000, navigationTimeout: 30_000, baseURL: 'http://127.0.0.1:3000', ...devices['Desktop Chrome'], channel: 'chrome', trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev -- --port 3000', url: 'http://127.0.0.1:3000/api/health', reuseExistingServer: true, timeout: 90_000 },
});
