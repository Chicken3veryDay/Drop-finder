import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.DROPFINDER_PUBLIC_URL;
if (!baseURL) throw new Error('DROPFINDER_PUBLIC_URL is required');

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'service-worker-activation.spec.mjs',
  timeout: 90_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [['json', { outputFile: 'test-results/activation-results.json' }], ['line']],
  use: {
    baseURL,
    serviceWorkers: 'allow',
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
