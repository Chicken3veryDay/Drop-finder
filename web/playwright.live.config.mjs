import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.DROPFINDER_PUBLIC_URL || 'https://chicken3veryday.github.io/Drop-finder/';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['integrated-app.spec.mjs', 'live-production.spec.mjs'],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 2,
  reporter: [
    ['line'],
    ['json', { outputFile: 'test-results/live-results.json' }],
    ['html', { outputFolder: 'playwright-live-report', open: 'never' }],
  ],
  use: {
    baseURL,
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
