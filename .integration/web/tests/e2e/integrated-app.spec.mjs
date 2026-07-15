import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

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
