import test from 'node:test';
import assert from 'node:assert/strict';
import { MarketplaceQueryEngine } from '../src/platform/workers/marketplace-query-engine.js';

function fixtureProducts(count = 4) {
  return Array.from({ length: count }, (_, index) => ({
    id: `p${index}`,
    vendor_id: 'v1',
    vendor: 'Vendor',
    strain: `Strain ${index}`,
    lineage: 'hybrid',
    total_thc: 20,
    variants: [{ id: `p${index}-7`, grams: 7, price: 35, price_per_gram: 5 }],
  }));
}

class FakeWorker {
  constructor() { this.messages = []; }
  postMessage(message) { this.messages.push(message); }
  terminate() { this.terminated = true; }
  complete(version, result = { version }) {
    this.onmessage({ data: { type: 'result', generationId: 'g1', version, result } });
  }
}

test('worker query engine retains only the latest request from a rapid burst', async () => {
  const worker = new FakeWorker();
  const engine = new MarketplaceQueryEngine({ workerFactory: () => worker });
  await engine.initialize('g1', fixtureProducts());

  const superseded = [];
  let latest;
  for (let index = 1; index <= 20; index += 1) {
    const pending = engine.query({ search: `query ${index}` });
    if (index < 20) superseded.push(pending.catch(error => error));
    else latest = pending;
  }

  const supersededErrors = await Promise.all(superseded);
  assert.equal(supersededErrors.length, 19);
  assert.ok(supersededErrors.every(error => error.name === 'AbortError'));
  assert.deepEqual(
    worker.messages.filter(message => message.type === 'query').map(message => message.version),
    [1],
  );

  worker.complete(1);
  assert.deepEqual(
    worker.messages.filter(message => message.type === 'query').map(message => message.version),
    [1, 20],
  );

  const latestResult = { version: 20, rows: [] };
  worker.complete(20, latestResult);
  assert.equal(await latest, latestResult);
  assert.equal(engine.pending.size, 0);
  engine.dispose();
});
