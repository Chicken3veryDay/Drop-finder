import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceQueryEngine } from '../src/platform/workers/marketplace-query-engine.js';

const products = [
  {
    id: 'p1', vendor_id: 'v1', vendor: 'Alpha', strain: 'One', lineage: 'hybrid', total_thc: 22,
    variants: [{ id: 'p1-v1', grams: 7, price: 35, price_per_gram: 5 }],
  },
  {
    id: 'p2', vendor_id: 'v2', vendor: 'Beta', strain: 'Two', lineage: 'sativa', total_thc: 28,
    variants: [{ id: 'p2-v1', grams: 14, price: 56, price_per_gram: 4 }],
  },
];

test('null and blank numeric bounds remain unbounded instead of coercing to zero', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null, syncFallbackLimit: 10 });
  await engine.initialize('g1', products);
  const result = await engine.query({
    minTotalThc: null,
    maxTotalThc: '',
    minWeight: null,
    maxWeight: ' ',
    minPrice: null,
    maxPrice: '',
    minPpg: null,
    maxPpg: '',
  });
  assert.equal(result.total, products.length);
  assert.deepEqual(result.rows.map(row => row.productId), ['p2', 'p1']);
  engine.dispose();
});
