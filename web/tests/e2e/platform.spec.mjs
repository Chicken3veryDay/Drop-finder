import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const HARNESS = '/tests/e2e/fixtures/harness.html';

test.beforeEach(async ({ page }) => {
  await page.goto(HARNESS);
  await expect(page.locator('#main')).toHaveAttribute('data-ready', 'true', { timeout: 45_000 });
});

test('loads a large catalog and keeps rendered rows bounded during endless scrolling', async ({ page }) => {
  await expect(page.locator('#feed')).toHaveAttribute('aria-setsize', '10000');
  for (let index = 0; index < 24; index += 1) {
    await page.locator('#viewport').evaluate(element => { element.scrollTop = element.scrollHeight; element.dispatchEvent(new Event('scroll')); });
    await page.waitForTimeout(25);
  }
  const rendered = await page.locator('[data-marketplace-row]').count();
  expect(rendered).toBeGreaterThan(0);
  expect(rendered).toBeLessThanOrEqual(20);
  await expect(page.locator('#main')).toHaveAttribute('data-query-current', 'true');
});

test('publishes only the latest rapid search and supports exact sort and weight changes', async ({ page }) => {
  const search = page.getByRole('searchbox');
  await search.pressSequentially('strain 222', { delay: 2 });
  await expect(page.locator('#main')).toHaveAttribute('data-query-current', 'true');
  await expect(page.locator('#status')).toContainText('results');
  await page.getByRole('combobox', { name: 'Sort results' }).selectOption('highest_total_thc');
  await page.getByRole('combobox', { name: 'Weight' }).selectOption('14');
  await expect(page.locator('#main')).toHaveAttribute('data-query-current', 'true');
  const weights = await page.locator('[data-marketplace-row] p').allTextContents();
  expect(weights.some(text => text.includes('14 g'))).toBeTruthy();
});

test('preserves keyboard focus and scroll anchor when a virtual row expands and collapses', async ({ page }) => {
  const viewport = page.locator('#viewport');
  await viewport.evaluate(element => { element.scrollTop = 2_000; element.dispatchEvent(new Event('scroll')); });
  const button = page.getByRole('button', { name: 'Expand' }).first();
  await button.focus();
  const before = await viewport.evaluate(element => element.scrollTop);
  await button.click();
  await expect(page.getByRole('button', { name: 'Collapse' }).first()).toBeFocused();
  const expanded = page.locator('[data-marketplace-row][aria-expanded="true"]');
  await expect(expanded).toHaveCount(1);
  const after = await viewport.evaluate(element => element.scrollTop);
  expect(Math.abs(after - before)).toBeLessThan(260);
  await page.getByRole('button', { name: 'Collapse' }).first().click();
  await expect(page.locator('[data-marketplace-row][aria-expanded="true"]')).toHaveCount(0);
});

test('renders the real two-page PDF, navigates, zooms, closes, and restores focus', async ({ page }) => {
  const opener = page.getByRole('button', { name: 'Open COA' }).first();
  await opener.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(page.locator('#pdf-canvas')).toBeVisible();
  expect(await page.locator('#pdf-canvas').evaluate(element => element.width)).toBeGreaterThan(0);
  await expect(page.locator('#page-status')).toContainText('Page 1 of 2');
  await page.getByRole('button', { name: 'Next page' }).click();
  await expect(page.locator('#page-status')).toContainText('Page 2 of 2');
  await page.getByRole('button', { name: 'Zoom in' }).click();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test('uses one concise original-document fallback for unsupported formats', async ({ page }) => {
  const opener = page.getByRole('button', { name: 'Open unsupported' });
  await opener.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('#document-fallback')).toContainText('Open the original document');
  await expect(page.getByRole('link', { name: 'Open original' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(opener).toBeFocused();
});

test('service-worker update is quiet and does not reload the page', async ({ page }) => {
  await page.evaluate(() => window.__platformHarness.serviceWorkerReady);
  const url = page.url();
  await page.getByRole('button', { name: 'Simulate update' }).click();
  await expect(page.locator('#status')).toContainText('generation-ready');
  expect(page.url()).toBe(url);
});

test('reloads offline after the service worker has cached the harness', async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'Offline transport control is asserted once in desktop Chromium; generation logic is unit-tested independently.');
  await page.evaluate(() => window.__platformHarness.serviceWorkerReady);
  await page.reload();
  await expect(page.locator('#main')).toHaveAttribute('data-ready', 'true', { timeout: 45_000 });
  await context.setOffline(true);
  await page.reload();
  await expect(page.locator('#main')).toHaveAttribute('data-ready', 'true', { timeout: 45_000 });
  await context.setOffline(false);
});

test('has no serious automated accessibility violations in the shell and marketplace', async ({ page }) => {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
});

test('has no serious automated accessibility violations in the document dialog', async ({ page }) => {
  await page.getByRole('button', { name: 'Open COA' }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const results = await new AxeBuilder({ page }).include('#dialog').analyze();
  expect(results.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
});
