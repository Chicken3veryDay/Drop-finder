import { defineConfig, devices } from '@playwright/test';

const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const chromiumOverride = chromiumExecutable ? { baseURL: 'http://dropfinder.test:4173', launchOptions: { executablePath: chromiumExecutable, args: ['--no-sandbox', '--disable-setuid-sandbox', '--host-resolver-rules=MAP dropfinder.test 127.0.0.1'] } } : {};

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'platform.spec.mjs',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]] : 'line',
  use: {
    baseURL: 'http://localhost:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  webServer: {
    command: 'npm run dev:e2e',
    url: 'http://127.0.0.1:4173/tests/e2e/fixtures/harness.html',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], ...chromiumOverride } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'], ...chromiumOverride } },
  ],
});
