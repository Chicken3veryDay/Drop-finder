import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['live-production.spec.mjs'],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 1,
  reporter: [
    ['line'],
    ['json', { outputFile: 'test-results/live-results.json' }],
    ['html', { outputFolder: 'playwright-live-report', open: 'never' }],
  ],
  use: {
    baseURL: process.env.PUBLIC_UI_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
    { name: 'mobile-webkit', use: { ...devices['iPhone 14'] } },
  ],
});
