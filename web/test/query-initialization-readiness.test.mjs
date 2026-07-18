import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceQueryEngine } from '../src/platform/workers/marketplace-query-engine.js';

const product = {
  id: 'ready-product',
  vendor_id: 'ready-vendor',
  vendor: 'Ready Vendor',
  strain: 'Ready Flower',
  lineage: 'hybrid',
  total_thc: 25,
  variants: [{
    id: 'ready-variant',
    grams: 7,
    price: 35,
    price_per_gram: 5,
  }],
};

test('a query started before initialization waits for the matching catalog', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null });
  let settled = false;
  const resultPromise = engine.query({ search: 'ready' }).finally(() => { settled = true; });

  await Promise.resolve();
  assert.equal(settled, false);

  await engine.initialize('generation-ready', [product]);
  const result = await resultPromise;

  assert.equal(result.generationId, 'generation-ready');
  assert.equal(result.total, 1);
  assert.equal(result.rows[0].productId, 'ready-product');
});

test('initialization failure rejects queries that are waiting for readiness', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null });
  const resultPromise = engine.query();

  await assert.rejects(
    engine.initialize('generation-invalid', null),
    (error) => error?.code === 'invalid_index',
  );
  await assert.rejects(
    resultPromise,
    (error) => error?.code === 'invalid_index',
  );
});

test('disposing an uninitialized engine aborts waiting queries', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null });
  const resultPromise = engine.query();

  engine.dispose();

  await assert.rejects(
    resultPromise,
    (error) => error?.name === 'AbortError',
  );
});
