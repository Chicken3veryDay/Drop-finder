import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';

const sha256 = (text) => createHash('sha256').update(text).digest('hex');
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function installDelayedCatalogFixture(page) {
  const generationId = 'delayed-query-ready-generation';
  const variant = {
    variant_id: 'delayed-query-ready-variant',
    grams: 7,
    current_price: 35,
    price_per_gram: 5,
    product_url: 'https://example.test/delayed-query-ready-product',
    source_weight_label: '7 g',
    documents: [],
  };
  const product = {
    product_id: 'delayed-query-ready-product',
    vendor_id: 'delayed-query-ready-vendor',
    vendor_name: 'Delayed Query Vendor',
    strain_name: 'Delayed Query Flower',
    lineage: 'hybrid',
    total_thc_display_percent: 25,
    detail_shard: 0,
    variants: [variant],
  };
  const indexText = JSON.stringify({ generation_id: generationId, products: [product] });
  const detailText = JSON.stringify({ generation_id: generationId, products: [product] });
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

  await page.route(/\/data\/catalog-v4\/manifest\.json(?:\?.*)?$/, async (route) => {
    await delay(350);
    await route.fulfill(json(manifestText));
  });
  await page.route(/\/data\/catalog-v4\/index\.json(?:\?.*)?$/, async (route) => {
    await delay(350);
    await route.fulfill(json(indexText));
  });
  await page.route(/\/data\/catalog-v4\/details\/000\.json(?:\?.*)?$/, (route) => route.fulfill(json(detailText)));
}

test('delayed catalog initialization produces results without manual retry', async ({ page }) => {
  await installDelayedCatalogFixture(page);
  await page.goto('/');

  const resultStatus = page.locator('.df-result-header').first();
  await expect(resultStatus).toContainText('1 result', { timeout: 20_000 });
  await expect(page.locator('.df-row').first()).toBeVisible();
  await expect(page.getByText('Query engine is not initialized')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Retry' })).toHaveCount(0);
});
