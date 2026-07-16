import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceQueryEngine } from '../src/platform/workers/marketplace-query-engine.js';

function fixtureProducts(count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `p${index}`,
    vendor_id: 'vendor',
    vendor: 'Vendor',
    strain: `Strain ${index}`,
    lineage: 'hybrid',
    total_thc: 20,
    variants: [{ id: `p${index}-v`, grams: 7, price: 35, price_per_gram: 5 }],
  }));
}

class FakeWorker {
  constructor({ failQueries = false } = {}) {
    this.failQueries = failQueries;
    this.messages = [];
  }

  postMessage(message) {
    if (this.failQueries && message.type === 'query') throw new Error('worker transport failed');
    this.messages.push(message);
  }

  terminate() {
    this.terminated = true;
  }
}

test('query engine fails honestly without leaking after worker recovery is exhausted', async () => {
  const workers = [];
  const engine = new MarketplaceQueryEngine({
    syncFallbackLimit: 2,
    maxWorkerRestarts: 1,
    workerFactory: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker;
    },
  });

  await engine.initialize('g1', fixtureProducts(3));
  workers[0].onerror(new Error('first crash'));
  workers[1].onerror(new Error('second crash'));

  assert.equal(engine.mode, 'failed');
  assert.equal(engine.worker, null);

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await assert.rejects(
      engine.query({ search: 'Strain' }),
      error => error.name === 'PlatformError'
        && error.code === 'worker_unavailable_for_catalog_size'
        && !error.message.includes('null'),
    );
    assert.equal(engine.pending.size, 0);
  }

  await engine.initialize('g2', fixtureProducts(3));
  assert.equal(engine.mode, 'worker');
  assert.equal(engine.workerRestarts, 0);

  workers[2].onerror(new Error('new generation crash'));
  assert.equal(workers.length, 4);
  assert.equal(engine.mode, 'worker');
  assert.equal(engine.workerRestarts, 1);
});

test('query engine falls back to synchronous queries below the size limit', async () => {
  const workers = [];
  const engine = new MarketplaceQueryEngine({
    syncFallbackLimit: 3,
    maxWorkerRestarts: 1,
    workerFactory: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker;
    },
  });

  await engine.initialize('g1', fixtureProducts(3));
  workers[0].onerror(new Error('first crash'));
  workers[1].onerror(new Error('second crash'));

  assert.equal(engine.mode, 'sync');
  const result = await engine.query({ search: 'Strain 1' });
  assert.deepEqual(result.rows.map(row => row.productId), ['p1']);
  assert.equal(engine.pending.size, 0);
});

test('query dispatch failures reject with a typed error and clean pending state', async () => {
  const engine = new MarketplaceQueryEngine({
    workerFactory: () => new FakeWorker({ failQueries: true }),
  });

  await engine.initialize('g1', fixtureProducts(1));

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await assert.rejects(
      engine.query(),
      error => error.name === 'PlatformError'
        && error.code === 'worker_dispatch_failed'
        && error.cause?.message === 'worker transport failed',
    );
    assert.equal(engine.pending.size, 0);
  }
});

test('an inconsistent worker mode rejects before allocating pending state', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => new FakeWorker() });
  await engine.initialize('g1', fixtureProducts(1));
  engine.disposeWorker();

  await assert.rejects(
    engine.query(),
    error => error.name === 'PlatformError' && error.code === 'worker_unavailable',
  );
  assert.equal(engine.pending.size, 0);
});
