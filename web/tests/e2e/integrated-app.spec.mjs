import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const desktopFieldLabels = [
  'Vendor',
  'Strain Name',
  'Lineage',
  'Total THC',
  'Weight',
  'Price',
  'Price/g',
  'Rating',
];

const assertNoDocumentOverflow = async (page) => {
  await expect.poll(async () => page.evaluate(() => Math.max(
    document.documentElement.scrollWidth,
    document.body.scrollWidth,
  ) - window.innerWidth)).toBeLessThanOrEqual(1);
};

test('integrated marketplace loads catalog-v4 and preserves bounded accessible interaction', async ({ page }) => {
  await page.goto('/');

  const search = page.getByRole('searchbox', { name: 'Search vendor or strain' });
  await expect(search).toBeVisible();
  const resultStatus = page.locator('.df-result-header').first();
  await expect(resultStatus).toContainText(/[1-9][\d,]* results/);

  const count = Number((await resultStatus.textContent())?.match(/[\d,]+/)?.[0].replaceAll(',', '') ?? 0);
  expect(count).toBeGreaterThan(0);
  expect(await page.locator('.df-product').count()).toBeLessThan(60);

  await page.keyboard.press('/');
  await expect(search).toBeFocused();
  await search.fill('__dropfinder_no_match__');
  await expect(resultStatus).toContainText('0 results');
  await search.fill('');
  await expect(resultStatus).toContainText(/[1-9][\d,]* results/);

  const firstRow = page.locator('.df-row').first();
  await expect(firstRow).toBeVisible();
  await firstRow.click();
  await expect(page.getByRole('link', { name: 'Product link' }).first()).toBeVisible();

  await expect(page.locator('body')).not.toContainText(/recommended|settings|raw thca|source health/i);
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test('mobile is a complete responsive port of the desktop marketplace', async ({ page }) => {
  await page.goto('/');
  const viewport = page.viewportSize();
  test.skip(!viewport || viewport.width > 900, 'Mobile parity assertions run on mobile projects.');

  const search = page.getByRole('searchbox', { name: 'Search vendor or strain' });
  await expect(search).toBeVisible();
  await assertNoDocumentOverflow(page);

  const filterOrder = await page.locator('.df-filter-row').evaluate((row) => Array.from(row.children)
    .filter((child) => !child.classList.contains('df-filter-separator'))
    .map((child) => {
      if (child instanceof HTMLDetailsElement) return child.querySelector('summary')?.textContent?.trim() ?? '';
      if (child instanceof HTMLFieldSetElement) return child.querySelector('legend')?.textContent?.trim() ?? '';
      return child.querySelector(':scope > span')?.textContent?.trim() ?? '';
    }));
  expect(filterOrder).toEqual(['Vendor', 'Lineage', 'Total THC', 'Weight', 'Price', 'Price/g', 'Sort']);

  await expect(page.locator('.df-multiselect')).toHaveCount(2);
  await expect(page.locator('.df-range')).toHaveCount(4);
  await expect(page.getByLabel('Sort')).toBeVisible();

  const vendorFilter = page.locator('.df-multiselect').first();
  await vendorFilter.locator('summary').click();
  await expect(vendorFilter.locator('.df-multiselect-menu')).toBeVisible();
  const menuBounds = await vendorFilter.locator('.df-multiselect-menu').boundingBox();
  expect(menuBounds).not.toBeNull();
  expect(menuBounds.x).toBeGreaterThanOrEqual(0);
  expect(menuBounds.x + menuBounds.width).toBeLessThanOrEqual(viewport.width + 1);
  await vendorFilter.locator('summary').click();

  const firstRow = page.locator('.df-row').first();
  await expect(firstRow).toBeVisible();
  const fieldLabels = await firstRow.locator('.df-cell').evaluateAll((cells) => cells.map((cell) => cell.getAttribute('data-label')));
  expect(fieldLabels).toEqual(desktopFieldLabels);

  for (const label of desktopFieldLabels) {
    await expect(firstRow.locator(`.df-cell[data-label="${label}"]`)).toBeVisible();
  }

  await firstRow.click();
  const expanded = page.locator('.df-expanded').first();
  await expect(expanded).toBeVisible();
  await expect(expanded.getByText('Weight', { exact: true })).toBeVisible();
  await expect(expanded.getByText('Price', { exact: true })).toBeVisible();
  await expect(expanded.getByText('Price/g', { exact: true })).toBeVisible();
  await expect(expanded.getByRole('link', { name: 'Product link' })).toBeVisible();

  const undersizedTargets = await page.locator([
    '.df-search',
    '.df-multiselect summary',
    '.df-sort select',
    '.df-range-input',
    '.df-expanded-meta select',
    '.df-expanded-actions a',
    '.df-expanded-actions button',
  ].join(', ')).evaluateAll((elements) => elements
    .filter((element) => {
      const style = getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden';
    })
    .map((element) => ({
      tag: element.tagName,
      className: element.className,
      height: element.getBoundingClientRect().height,
    }))
    .filter((target) => target.height < 43.5));
  expect(undersizedTargets).toEqual([]);

  await assertNoDocumentOverflow(page);
  expect(await page.locator('.df-product').count()).toBeLessThan(60);
});
