import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const HARNESS = '/tests/e2e/fixtures/harness.html';
const DOCUMENT_TEST_TIMEOUT = 120_000;
const DOCUMENT_READY_TIMEOUT = 45_000;

async function waitForCatalog(page) {
  await expect(page.locator('#main')).toHaveAttribute('data-ready', 'true', { timeout: 45_000 });
  await expect(page.locator('#feed')).toHaveAttribute('data-result-count', '10000', { timeout: 45_000 });
  await expect(page.locator('[data-marketplace-row]').first()).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('#main')).toHaveAttribute('data-layout-stable', 'true', { timeout: 45_000 });
}

async function waitForRenderedDocument(page, expectedPage, expectedPages = 2) {
  const stage = page.locator('#document-stage');
  await expect(stage).toHaveAttribute('data-render-state', 'ready', { timeout: DOCUMENT_READY_TIMEOUT });
  await expect(stage).toHaveAttribute('data-render-page', String(expectedPage), { timeout: DOCUMENT_READY_TIMEOUT });
  await expect(page.locator('#page-status')).toHaveText(`Page ${expectedPage} of ${expectedPages}`, { timeout: DOCUMENT_READY_TIMEOUT });
  const canvas = page.locator('#pdf-canvas');
  await expect(canvas).toBeVisible({ timeout: DOCUMENT_READY_TIMEOUT });
  expect(await canvas.evaluate(element => element.width)).toBeGreaterThan(0);
}

async function openPwaHarness(page) {
  await page.goto(`${HARNESS}?pwa=1`);
  await waitForCatalog(page);
  await page.evaluate(() => window.__platformHarness.serviceWorkerReady);
}

test.beforeEach(async ({ page }) => {
  await page.goto(HARNESS);
  await waitForCatalog(page);
});

test('loads a large catalog and keeps rendered rows bounded during endless scrolling', async ({ page }) => {
  for (let index = 0; index < 24; index += 1) {
    const beforeEnd = await page.evaluate(() => window.__platformHarness.virtual.loadedRange().endOffset);
    await page.locator('#viewport').evaluate(element => {
      const range = window.__platformHarness.virtual.loadedRange();
      element.scrollTop = Math.max(0, range.endPx - element.clientHeight + 1);
      element.dispatchEvent(new Event('scroll'));
    });
    await expect.poll(
      () => page.evaluate(() => window.__platformHarness.virtual.loadedRange().endOffset),
    ).toBeGreaterThan(beforeEnd);
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
  await expect(page.locator('#main')).toHaveAttribute('data-layout-stable', 'true', { timeout: 45_000 });
  const productId = await page.evaluate(() => {
    const viewportElement = document.querySelector('#viewport');
    const bounds = viewportElement.getBoundingClientRect();
    const center = bounds.top + bounds.height / 2;
    const candidates = [...document.querySelectorAll('[data-marketplace-row]')]
      .map(row => {
        const box = row.getBoundingClientRect();
        return {
          id: row.dataset.productId,
          visible: box.bottom > bounds.top && box.top < bounds.bottom,
          distance: Math.abs((box.top + box.bottom) / 2 - center),
        };
      })
      .filter(candidate => candidate.visible && candidate.id)
      .sort((a, b) => a.distance - b.distance);
    return candidates[0]?.id ?? null;
  });
  expect(productId).toBeTruthy();
  const row = page.locator(`[data-product-id="${productId}"]`);
  const expand = row.getByRole('button', { name: 'Expand' });
  await expand.evaluate(element => element.focus({ preventScroll: true }));
  await expect(expand).toBeFocused();
  const before = await viewport.evaluate(element => element.scrollTop);
  await expand.press('Enter');
  const collapse = row.getByRole('button', { name: 'Collapse' });
  await expect(collapse).toBeFocused();
  await expect(row).toHaveAttribute('data-expanded', 'true');
  const after = await viewport.evaluate(element => element.scrollTop);
  expect(Math.abs(after - before)).toBeLessThan(260);
  await collapse.press('Enter');
  await expect(row).toHaveAttribute('data-expanded', 'false');
});

test('renders the real two-page PDF, navigates, zooms, closes, and restores focus', async ({ page }) => {
  test.setTimeout(DOCUMENT_TEST_TIMEOUT);
  const opener = page.getByRole('button', { name: 'Open COA' }).first();
  await opener.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await waitForRenderedDocument(page, 1);
  await page.getByRole('button', { name: 'Next page' }).click();
  await waitForRenderedDocument(page, 2);
  await page.getByRole('button', { name: 'Zoom in' }).click();
  await waitForRenderedDocument(page, 2);
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
  await openPwaHarness(page);
  const url = page.url();
  await page.getByRole('button', { name: 'Simulate update' }).click();
  await expect(page.locator('#status')).toContainText('generation-ready');
  expect(page.url()).toBe(url);
});

test('reloads offline after the service worker has cached the harness', async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'Offline transport control is asserted once in desktop Chromium; generation logic is unit-tested independently.');
  await openPwaHarness(page);
  await page.reload();
  await waitForCatalog(page);
  await page.evaluate(() => window.__platformHarness.waitForOfflineCache());
  await context.setOffline(true);
  await page.reload();
  await waitForCatalog(page);
  await context.setOffline(false);
});

test('has no serious automated accessibility violations in the shell and marketplace', async ({ page }) => {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
});

test('has no serious automated accessibility violations in the document dialog', async ({ page }) => {
  test.setTimeout(DOCUMENT_TEST_TIMEOUT);
  await page.getByRole('button', { name: 'Open COA' }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await waitForRenderedDocument(page, 1);
  const results = await new AxeBuilder({ page }).include('#dialog').analyze();
  expect(results.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
});
