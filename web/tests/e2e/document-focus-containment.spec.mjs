import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';

const sha256 = (text) => createHash('sha256').update(text).digest('hex');

async function installDocumentCatalogFixture(page) {
  const generationId = 'focus-trap-generation';
  const document = {
    document_id: 'focus-trap-coa',
    kind: 'coa',
    public_url: './tests/e2e/fixtures/sample.pdf',
    mime_type: 'application/pdf',
    discovered_label: 'Focus trap COA',
  };
  const variant = {
    variant_id: 'focus-variant',
    grams: 7,
    current_price: 35,
    price_per_gram: 5,
    product_url: 'https://example.test/focus-product',
    source_weight_label: '7 g',
    documents: [document],
  };
  const product = {
    product_id: 'focus-product',
    vendor_id: 'focus-vendor',
    vendor_name: 'Focus Vendor',
    strain_name: 'Focus Flower',
    lineage: 'hybrid',
    total_thc_display_percent: 25,
    detail_shard: 0,
    variants: [variant],
  };
  const indexText = JSON.stringify({ generation_id: generationId, products: [product] });
  const detailText = JSON.stringify({
    generation_id: generationId,
    products: [{ ...product, effects: ['calm'], grow_environment: 'indoor' }],
  });
  const detailDescriptor = {
    path: 'data/catalog-v4/details/000.json',
    product_count: 1,
    sha256: sha256(detailText),
  };
  const manifestText = JSON.stringify({
    schema_version: 'dropfinder-catalog-manifest-v4',
    generation_id: generationId,
    compact_index: {
      path: 'data/catalog-v4/index.json',
      sha256: sha256(indexText),
    },
    product_detail_shards: [detailDescriptor],
    details: { [product.product_id]: detailDescriptor },
  });
  const json = (body) => ({ status: 200, contentType: 'application/json', body });

  await page.route(/\/data\/catalog-v4\/manifest\.json(?:\?.*)?$/, (route) => route.fulfill(json(manifestText)));
  await page.route(/\/data\/catalog-v4\/index\.json(?:\?.*)?$/, (route) => route.fulfill(json(indexText)));
  await page.route(/\/data\/catalog-v4\/details\/000\.json(?:\?.*)?$/, (route) => route.fulfill(json(detailText)));
}

test('document overlay contains immediate backward focus navigation', async ({ page }) => {
  test.setTimeout(120_000);
  await installDocumentCatalogFixture(page);
  await page.goto('/');

  const row = page.locator('.df-row').first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.click();

  const opener = page.getByRole('button', { name: 'Open COA' });
  await expect(opener).toBeVisible();
  await opener.click();

  const dialog = page.getByRole('dialog', { name: 'Focus trap COA' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toBeFocused();

  const lastControl = dialog.getByRole('button', { name: 'Fit width' });
  await expect(lastControl).toBeVisible({ timeout: 45_000 });
  await page.keyboard.press('Shift+Tab');

  await expect(lastControl).toBeFocused();
  await expect(opener).not.toBeFocused();
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
});
