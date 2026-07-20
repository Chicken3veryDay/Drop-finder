import { test, expect } from '@playwright/test';

async function releaseCounts(request) {
  const [manifestResponse, runtimeResponse] = await Promise.all([
    request.get('./data/catalog-v4/manifest.json'),
    request.get('./data/runtime.json'),
  ]);
  expect(manifestResponse.ok()).toBeTruthy();
  expect(runtimeResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  const runtime = await runtimeResponse.json();
  const typeCounts = Object.values(runtime.products_by_type || {}).map(Number).filter(Number.isFinite);
  return {
    primary: Number(manifest.product_count),
    secondary: Math.min(...typeCounts),
  };
}

async function openApp(page, primaryCount) {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: /Dropfinder/i }).first()).toBeVisible();
  await expect(page.getByRole('region', { name: 'Marketplace', exact: true })).toBeVisible();
  const tablist = page.getByRole('tablist').first();
  await expect(tablist).toBeVisible();
  await expect(tablist.getByRole('tab')).toHaveCount(2);
  const list = page.getByRole('list', { name: `${primaryCount} marketplace results`, exact: true });
  await expect(list).toBeVisible({ timeout: 30_000 });
  await expect(list.getByRole('listitem').first()).toBeVisible();
  return { tablist, list };
}

function usefulToken(value) {
  return value
    .split(/\s+/)
    .map((part) => part.replace(/[^\p{L}\p{N}'-]/gu, ''))
    .find((part) => part.length >= 4) || '';
}

test('live type tabs, counts, and search follow the published schemas', async ({ page, request }) => {
  const counts = await releaseCounts(request);
  const { tablist, list } = await openApp(page, counts.primary);
  const tabs = tablist.getByRole('tab');
  await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
  await expect(tabs.nth(0)).toContainText(String(counts.primary));
  await expect(tabs.nth(1)).toContainText(String(counts.secondary));

  const token = usefulToken((await list.getByRole('listitem').first().innerText()).trim());
  expect(token).not.toBe('');
  const search = page.getByRole('searchbox').first();
  await search.fill(token);
  const filtered = page.getByRole('list', { name: /marketplace results/i });
  await expect.poll(async () => filtered.getByRole('listitem').count()).toBeGreaterThan(0);
  await expect(filtered.getByRole('listitem').first()).toContainText(token, { ignoreCase: true });
  await search.fill('');
  await expect(page.getByRole('list', { name: `${counts.primary} marketplace results`, exact: true })).toBeVisible();

  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
  const secondaryList = page.getByRole('list', { name: `${counts.secondary} marketplace results`, exact: true });
  await expect(secondaryList).toBeVisible();
  await expect(secondaryList.getByRole('listitem')).toHaveCount(counts.secondary);

  await tabs.nth(0).click();
  await expect(tabs.nth(0)).toHaveAttribute('aria-selected', 'true');
});

test('live controls remain keyboard reachable without 320px overflow', async ({ page, request }) => {
  const counts = await releaseCounts(request);
  await page.setViewportSize({ width: 320, height: 760 });
  await openApp(page, counts.primary);

  const search = page.getByRole('searchbox').first();
  await expect(search).toBeVisible();
  await expect(page.getByRole('combobox').first()).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(Math.max(dimensions.body, dimensions.document)).toBeLessThanOrEqual(dimensions.viewport + 1);

  await page.keyboard.press('Tab');
  let reachedSearch = false;
  for (let index = 0; index < 20; index += 1) {
    if (await search.evaluate((node) => document.activeElement === node)) {
      reachedSearch = true;
      break;
    }
    await page.keyboard.press('Tab');
  }
  expect(reachedSearch).toBeTruthy();
});
