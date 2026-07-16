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

test('worker query engine runs one request and retains only the latest queued query', async () => {
  const worker = new FakeWorker();
  const engine = new MarketplaceQueryEngine({ workerFactory: () => worker });
  await engine.initialize('g1', fixtureProducts());

  const first = engine.query({ search: 'one' });
  const firstOutcome = first.catch(error => error);
  const second = engine.query({ search: 'two' });
  const secondOutcome = second.catch(error => error);
  const third = engine.query({ search: 'three' });

  assert.equal((await firstOutcome).name, 'AbortError');
  assert.equal((await secondOutcome).name, 'AbortError');
  assert.deepEqual(
    worker.messages.filter(message => message.type === 'query').map(message => message.version),
    [1],
  );

  worker.complete(1);
  assert.deepEqual(
    worker.messages.filter(message => message.type === 'query').map(message => message.version),
    [1, 3],
  );

  const latestResult = { version: 3, rows: [] };
  worker.complete(3, latestResult);
  assert.equal(await third, latestResult);
  assert.equal(engine.pending.size, 0);
  engine.dispose();
});
