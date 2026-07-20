import { test, expect } from '@playwright/test';

const FLOWER_COUNT = 139;
const VAPE_COUNT = 6;

const marketplace = (page) => page.getByRole('region', { name: 'Marketplace', exact: true });
const resultList = (page) => page.getByRole('list', { name: /marketplace results/i });

async function openMarketplace(page) {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Dropfinder Marketplace', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Type-aware marketplace', exact: true })).toBeVisible();
  await expect(page.getByRole('tablist', { name: 'Marketplace product type', exact: true })).toBeVisible();
  await expect(marketplace(page)).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain', exact: true })).toBeVisible();
  await expect(page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true }).getByRole('listitem').first()).toBeVisible();
}

function usefulToken(value) {
  return value
    .split(/\s+/)
    .map((part) => part.replace(/[^\p{L}\p{N}'-]/gu, ''))
    .find((part) => part.length >= 4) || '';
}

test('current live marketplace exposes accepted counts, search, and type tabs', async ({ page }) => {
  await openMarketplace(page);

  const flowerTab = page.getByRole('tab', { name: new RegExp(`^Flower\\s+${FLOWER_COUNT} products$`, 'i') });
  const vapeTab = page.getByRole('tab', { name: new RegExp(`^Cannabis vapes\\s+${VAPE_COUNT} products$`, 'i') });
  await expect(flowerTab).toHaveAttribute('aria-selected', 'true');
  await expect(vapeTab).toHaveAttribute('aria-selected', 'false');

  const initialList = page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true });
  const firstText = (await initialList.getByRole('listitem').first().innerText()).trim();
  const token = usefulToken(firstText);
  expect(token).not.toBe('');

  const search = page.getByRole('searchbox', { name: 'Search vendor or strain', exact: true });
  await search.fill(token);
  await expect.poll(async () => resultList(page).getByRole('listitem').count()).toBeGreaterThan(0);
  await expect(resultList(page).getByRole('listitem').first()).toContainText(token, { ignoreCase: true });
  await search.fill('');
  await expect(page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true })).toBeVisible();

  await vapeTab.click();
  await expect(vapeTab).toHaveAttribute('aria-selected', 'true');
  const vapeList = page.getByRole('list', { name: `${VAPE_COUNT} marketplace results`, exact: true });
  await expect(vapeList).toBeVisible();
  await expect(vapeList.getByRole('listitem')).toHaveCount(VAPE_COUNT);

  await flowerTab.click();
  await expect(flowerTab).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true })).toBeVisible();
});

test('current live marketplace retains accessible controls and a bounded 320px layout', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await openMarketplace(page);

  await expect(marketplace(page).getByRole('group', { name: 'Marketplace filters', exact: true })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: /sort/i })).toBeVisible();
  await expect(page.getByRole('list', { name: `${FLOWER_COUNT} marketplace results`, exact: true }).getByRole('listitem').first()).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(Math.max(dimensions.body, dimensions.document)).toBeLessThanOrEqual(dimensions.viewport + 1);

  await page.keyboard.press('Tab');
  let reachedSearch = false;
  const search = page.getByRole('searchbox', { name: 'Search vendor or strain', exact: true });
  for (let index = 0; index < 18; index += 1) {
    if (await search.evaluate((node) => document.activeElement === node)) {
      reachedSearch = true;
      break;
    }
    await page.keyboard.press('Tab');
  }
  expect(reachedSearch).toBeTruthy();
});
