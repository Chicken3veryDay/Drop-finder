import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceQueryEngine } from '../src/platform/workers/marketplace-query-engine.js';

const products = [
  {
    id: 'p1',
    vendor_id: 'v1',
    vendor: 'WNC—CBD',
    strain: 'ADL | THCa Flower | Tier 1',
    lineage: 'hybrid',
    total_thc: 24,
    image: 'https://example.test/image-secret.jpg',
    variants: [{ id: 'p1-v1', grams: 7, price: 35, price_per_gram: 5 }],
  },
  {
    id: 'p2',
    vendor_id: 'v2',
    vendor: 'Café Botanica',
    strain: 'Crème Brûlée',
    lineage: 'indica_hybrid',
    total_thc: 26,
    variants: [{ id: 'p2-v1', grams: 7, price: 42, price_per_gram: 6 }],
  },
  {
    id: 'p3',
    vendor_id: 'v3',
    vendor: 'Plain Vendor',
    strain: 'Unrelated Flower',
    lineage: 'sativa',
    total_thc: 20,
    variants: [{ id: 'p3-v1', grams: 7, price: 49, price_per_gram: 7 }],
  },
];

async function createEngine() {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null, syncFallbackLimit: 10 });
  await engine.initialize('g-search-normalization', products);
  return engine;
}

test('marketplace worker search normalizes punctuation, symbols, diacritics, and whitespace', async () => {
  const engine = await createEngine();
  try {
    for (const search of [
      'adl thca flower tier 1',
      'ADL | THCa Flower | Tier 1',
      '  WNC CBD   ADL THCA FLOWER TIER 1  ',
    ]) {
      const result = await engine.query({ search });
      assert.deepEqual(result.rows.map(row => row.productId), ['p1'], search);
    }

    for (const search of [
      'cafe botanica creme brulee',
      'Cafe\u0301 Botanica Cre\u0300me Bru\u0302le\u0301e',
    ]) {
      const result = await engine.query({ search });
      assert.deepEqual(result.rows.map(row => row.productId), ['p2'], search);
    }

    const unrelatedField = await engine.query({ search: 'image secret' });
    assert.equal(unrelatedField.total, 0, 'search must remain limited to vendor and strain');
  } finally {
    engine.dispose();
  }
});

test('semantically equivalent searches use the same query identity', async () => {
  const engine = await createEngine();
  try {
    const punctuated = await engine.query({ search: 'ADL | THCa Flower | Tier 1' });
    const normalized = await engine.query({ search: 'adl thca flower tier 1' });
    assert.equal(punctuated.queryKey, normalized.queryKey);
  } finally {
    engine.dispose();
  }
});
