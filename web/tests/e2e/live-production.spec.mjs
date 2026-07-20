import { test, expect } from '@playwright/test';

const ready = async (page) => {
  await page.goto('./', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain' })).toBeVisible();
  await expect(page.locator('.df-row').first()).toBeVisible({ timeout: 30_000 });
};

const countResults = async (page) => {
  const text = await page.locator('.df-result-header').innerText();
  return Number((text.match(/[\d,]+/)?.[0] || '0').replaceAll(',', ''));
};

const clearFilters = async (page) => {
  const search = page.getByRole('searchbox', { name: 'Search vendor or strain' });
  await search.fill('');
  for (const name of ['Vendor', 'Lineage']) {
    const details = page.locator('details.df-multiselect').filter({ hasText: name }).first();
    if (await details.count()) {
      if (!(await details.getAttribute('open'))) await details.locator('summary').click();
      const checked = details.locator('input[type="checkbox"]:checked');
      while (await checked.count()) await checked.first().uncheck();
    }
  }
  for (const name of ['Total THC', 'Weight', 'Price', 'Price/g']) {
    const group = page.getByRole('group', { name });
    await group.getByLabel('Min').fill('');
    await group.getByLabel('Max').fill('');
  }
};

const injectCombiningAccent = (value) => {
  const match = value.match(/[A-Za-z]/);
  if (!match) return value;
  const index = match.index;
  return `${value.slice(0, index + 1)}\u0301${value.slice(index + 1)}`;
};

test('live generation, service worker, navigation fallback, and offline shell agree', async ({ page, context, request }) => {
  await ready(page);
  const [catalog, status, runtime, manifest] = await Promise.all([
    request.get('./data/catalog.json'),
    request.get('./data/status.json'),
    request.get('./data/runtime.json'),
    request.get('./data/catalog-v4/manifest.json'),
  ]);
  for (const response of [catalog, status, runtime, manifest]) expect(response.ok()).toBeTruthy();
  const documents = await Promise.all([catalog, status, runtime, manifest].map((response) => response.json()));
  const generations = documents.map((value) => value.generation_id);
  expect(new Set(generations).size).toBe(1);
  expect(documents[3].catalog_schema_version).toBe('dropfinder-catalog-v4');

  const registration = await page.evaluate(async () => {
    const value = await navigator.serviceWorker.ready;
    await value.update();
    return { scope: value.scope, controlled: Boolean(navigator.serviceWorker.controller) };
  });
  expect(registration.scope).toContain('/Drop-finder/');

  const fallback = await request.get('./closure-route-that-does-not-exist', { headers: { Accept: 'text/html' } });
  expect(fallback.status()).toBe(200);
  expect((fallback.headers()['content-type'] || '')).toContain('text/html');

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain' })).toBeVisible();
  await context.setOffline(false);

  const cacheKeys = await page.evaluate(() => caches.keys());
  expect(cacheKeys.some((key) => key.includes('dropfinder-app-'))).toBeTruthy();
  expect(cacheKeys.every((key) => !key.includes('raw.githack'))).toBeTruthy();

  await page.goto('./index.html');
  await page.goto('./');
  await page.goBack();
  await expect(page).toHaveURL(/index\.html/);
  await page.goForward();
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain' })).toBeVisible();
});

test('live punctuation and diacritic search preserve deterministic results', async ({ page }) => {
  await ready(page);
  const firstName = (await page.locator('.df-row .df-strain').first().innerText()).trim();
  const search = page.getByRole('searchbox', { name: 'Search vendor or strain' });

  await search.fill(firstName.replace(/\s+/g, ' - '));
  await expect.poll(() => countResults(page)).toBeGreaterThan(0);
  await expect(page.locator('.df-row .df-strain').first()).toContainText(firstName, { ignoreCase: true });

  await search.fill(injectCombiningAccent(firstName));
  await expect.poll(() => countResults(page)).toBeGreaterThan(0);
  await expect(page.locator('.df-row .df-strain').first()).toContainText(firstName, { ignoreCase: true });

  await search.fill('');
  await page.keyboard.press('/');
  await expect(search).toBeFocused();
  await search.fill(firstName);
  await search.press('Escape');
  await expect(search).toHaveValue('');
  await search.press('Escape');
  await expect(search).not.toBeFocused();
});

test('live vendor, lineage, numeric filters, and sorting operate on accepted rows', async ({ page }) => {
  await ready(page);
  const initial = await countResults(page);
  expect(initial).toBeGreaterThan(0);

  const vendorDetails = page.locator('details.df-multiselect').filter({ hasText: 'Vendor' }).first();
  await vendorDetails.locator('summary').click();
  const vendorCheckbox = vendorDetails.locator('input[type="checkbox"]').first();
  const vendorLabel = (await vendorCheckbox.locator('xpath=..').innerText()).trim();
  await vendorCheckbox.check();
  await expect.poll(() => countResults(page)).toBeGreaterThan(0);
  await expect(page.locator('.df-row .df-vendor').first()).toContainText(vendorLabel, { ignoreCase: true });
  await vendorCheckbox.uncheck();

  const lineageDetails = page.locator('details.df-multiselect').filter({ hasText: 'Lineage' }).first();
  await lineageDetails.locator('summary').click();
  const lineageOptions = lineageDetails.locator('input[type="checkbox"]');
  let selectedLineage = '';
  for (let index = 0; index < await lineageOptions.count(); index += 1) {
    const option = lineageOptions.nth(index);
    const label = (await option.locator('xpath=..').innerText()).trim();
    await option.check();
    if (await countResults(page)) {
      selectedLineage = label;
      break;
    }
    await option.uncheck();
  }
  expect(selectedLineage).not.toBe('');
  await expect(page.locator('.df-row .df-lineage').first()).toContainText(selectedLineage, { ignoreCase: true });
  await lineageOptions.filter({ has: page.locator(':checked') }).uncheck().catch(() => {});
  await clearFilters(page);

  const row = page.locator('.df-row').first();
  const parseNumber = async (selector) => Number((await row.locator(selector).innerText()).replace(/[^0-9.]/g, ''));
  const values = {
    'Total THC': await parseNumber('.df-thc'),
    Weight: await parseNumber('.df-weight'),
    Price: await parseNumber('.df-price'),
    'Price/g': await parseNumber('.df-ppg'),
  };
  for (const [name, value] of Object.entries(values)) {
    if (!Number.isFinite(value) || value <= 0) continue;
    const group = page.getByRole('group', { name });
    await group.getByLabel('Min').fill(String(Math.max(0, value - 0.01)));
    await group.getByLabel('Max').fill(String(value + 0.01));
    await expect.poll(() => countResults(page)).toBeGreaterThan(0);
    await group.getByLabel('Min').fill('');
    await group.getByLabel('Max').fill('');
  }

  const sort = page.getByLabel('Sort');
  await sort.selectOption('strain_az');
  await expect.poll(async () => (await page.locator('.df-row .df-strain').count())).toBeGreaterThan(1);
  const names = await page.locator('.df-row .df-strain').allInnerTexts();
  const expected = [...names].sort(new Intl.Collator('en', { sensitivity: 'base', numeric: true, usage: 'sort' }).compare);
  expect(names).toEqual(expected);
});

test('live pagination stays bounded and expansion, variants, images, documents, and links work', async ({ page }) => {
  await ready(page);
  const total = await countResults(page);
  const seen = new Set();
  let maxRows = 0;
  for (let step = 0; step < 18; step += 1) {
    const rows = page.locator('.df-row');
    maxRows = Math.max(maxRows, await rows.count());
    for (const text of await rows.allInnerTexts()) seen.add(text);
    await page.locator('.df-virtual-viewport').evaluate((node) => { node.scrollTop = node.scrollHeight; });
    await page.waitForTimeout(250);
  }
  expect(maxRows).toBeLessThanOrEqual(80);
  expect(seen.size).toBeGreaterThan(Math.min(total, 8));
  const positions = await page.locator('[role="listitem"]').evaluateAll((nodes) => nodes.map((node) => Number(node.getAttribute('aria-posinset'))));
  expect(new Set(positions).size).toBe(positions.length);

  await page.locator('.df-virtual-viewport').evaluate((node) => { node.scrollTop = 0; });
  const row = page.locator('.df-row').first();
  await row.scrollIntoViewIfNeeded();
  await row.click();
  const detail = page.locator('.df-expanded').first();
  await expect(detail).toBeVisible();
  const productLink = detail.getByRole('link', { name: 'Product link' });
  await expect(productLink).toHaveAttribute('target', '_blank');
  await expect(productLink).toHaveAttribute('rel', /noreferrer/);

  const variant = detail.getByLabel('Weight');
  if (await variant.locator('option').count() > 1) {
    const before = await detail.locator('.df-price-block strong').innerText();
    await variant.selectOption({ index: 1 });
    await expect(detail.locator('.df-price-block strong')).not.toHaveText(before);
  }

  const image = detail.getByRole('img', { name: /product$/ });
  if (await image.count()) {
    await expect.poll(() => image.evaluate((node) => ({ complete: node.complete, width: node.naturalWidth }))).toMatchObject({ complete: true });
    expect((await image.evaluate((node) => node.naturalWidth))).toBeGreaterThan(0);
  } else {
    await expect(detail).toContainText('Image unavailable');
  }

  const documentButton = detail.getByRole('button', { name: /Open (COA|terpene document)/ }).first();
  if (await documentButton.count()) {
    await documentButton.focus();
    await documentButton.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('link', { name: 'Open original' })).toHaveAttribute('rel', /noreferrer/);
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(documentButton).toBeFocused();
  }
});

test('live accessibility names, retired type absence, focus containment, and 320px layout hold', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 760 });
  await ready(page);
  await expect(page.getByRole('region', { name: 'Marketplace' })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: 'Search vendor or strain' })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Marketplace filters' })).toBeVisible();
  await expect(page.getByText(/Edibles/i)).toHaveCount(0);
  await expect(page.locator('[data-product-type="cannabis_edible"]')).toHaveCount(0);
  await expect(page.getByText(/Source health/i)).toHaveCount(0);
  await expect(page.getByText(/Favorites/i)).toHaveCount(0);

  await page.keyboard.press('Tab');
  let foundSearch = false;
  for (let index = 0; index < 12; index += 1) {
    if (await page.getByRole('searchbox', { name: 'Search vendor or strain' }).evaluate((node) => document.activeElement === node)) {
      foundSearch = true;
      break;
    }
    await page.keyboard.press('Tab');
  }
  expect(foundSearch).toBeTruthy();

  const layout = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(Math.max(layout.body, layout.document)).toBeLessThanOrEqual(layout.viewport + 1);
});
