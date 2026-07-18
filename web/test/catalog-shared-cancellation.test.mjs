import test from 'node:test';
import assert from 'node:assert/strict';
import { CatalogGenerationClient, MemoryGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function detailFixture(fetchImpl) {
  const body = JSON.stringify({
    generation_id: 'g1',
    products: [{ product_id: 'a', image_url: 'https://x/a.jpg' }, { product_id: 'b', image_url: 'https://x/b.jpg' }],
  });
  const client = new CatalogGenerationClient({ fetchImpl, maxRetries: 0 });
  client.active = Object.freeze({
    generationId: 'g1',
    manifest: {
      product_detail_shards: [{ path: 'data/catalog-v4/details/015.json', bytes: Buffer.byteLength(body) }],
    },
    index: {
      products: [
        { product_id: 'a', detail_shard: 15 },
        { product_id: 'b', detail_shard: 15 },
      ],
    },
    manifestUrl: 'https://x/data/catalog-v4/manifest.json',
    publicationBaseUrl: 'https://x/',
    activatedAt: Date.now(),
    source: 'network',
  });
  return { client, body };
}

function delayedFetch() {
  const response = deferred();
  let calls = 0;
  let aborts = 0;
  const fetchImpl = (_input, { signal }) => {
    calls += 1;
    return new Promise((resolve, reject) => {
      const onAbort = () => {
        aborts += 1;
        reject(new DOMException('aborted', 'AbortError'));
      };
      signal.addEventListener('abort', onAbort, { once: true });
      response.promise.then(
        value => {
          signal.removeEventListener('abort', onAbort);
          resolve(value);
        },
        error => {
          signal.removeEventListener('abort', onAbort);
          reject(error);
        },
      );
    });
  };
  return {
    fetchImpl,
    resolve: value => response.resolve(value),
    stats: () => ({ calls, aborts }),
  };
}

async function expectAbort(promise) {
  await assert.rejects(promise, error => error?.name === 'AbortError');
}

test('first detail consumer can cancel without aborting a later consumer', async () => {
  const delayed = delayedFetch();
  const { client, body } = detailFixture(delayed.fetchImpl);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('a', { signal: firstController.signal });
  const second = client.loadDetail('b', { signal: secondController.signal });
  firstController.abort('collapsed');
  delayed.resolve(new Response(body));

  await expectAbort(first);
  assert.equal((await second).generation_id, 'g1');
  assert.equal(secondController.signal.aborted, false);
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 0 });
  assert.equal(client.inflight.size, 0);
});

test('later detail consumer can cancel without aborting the first consumer', async () => {
  const delayed = delayedFetch();
  const { client, body } = detailFixture(delayed.fetchImpl);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('a', { signal: firstController.signal });
  const second = client.loadDetail('b', { signal: secondController.signal });
  secondController.abort('collapsed');
  delayed.resolve(new Response(body));

  await expectAbort(second);
  assert.equal((await first).generation_id, 'g1');
  assert.equal(firstController.signal.aborted, false);
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 0 });
  assert.equal(client.inflight.size, 0);
});

test('shared detail transport aborts only after every consumer cancels', async () => {
  const delayed = delayedFetch();
  const { client } = detailFixture(delayed.fetchImpl);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('a', { signal: firstController.signal });
  const second = client.loadDetail('b', { signal: secondController.signal });
  await Promise.resolve();
  firstController.abort('first collapsed');
  assert.equal(delayed.stats().aborts, 0);
  secondController.abort('second collapsed');

  await Promise.all([expectAbort(first), expectAbort(second)]);
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 1 });
  await Promise.resolve();
  assert.equal(client.inflight.size, 0);
});

// Old cleanup must not delete a replacement created in the abort-to-settlement gap.
test('a new detail caller replaces an all-cancelled operation before old cleanup settles', async () => {
  const responses = [deferred(), deferred()];
  let calls = 0;
  const fetchImpl = (_input, { signal }) => {
    const response = responses[calls];
    calls += 1;
    return new Promise((resolve, reject) => {
      const onAbort = () => reject(new DOMException('aborted', 'AbortError'));
      signal.addEventListener('abort', onAbort, { once: true });
      response.promise.then(
        value => {
          signal.removeEventListener('abort', onAbort);
          resolve(value);
        },
        error => {
          signal.removeEventListener('abort', onAbort);
          reject(error);
        },
      );
    });
  };
  const { client, body } = detailFixture(fetchImpl);
  const controller = new AbortController();
  const cancelled = client.loadDetail('a', { signal: controller.signal });
  await Promise.resolve();
  controller.abort('collapsed');

  const replacement = client.loadDetail('b');
  responses[1].resolve(new Response(body));

  await expectAbort(cancelled);
  assert.equal((await replacement).generation_id, 'g1');
  assert.equal(calls, 2);
  assert.equal(client.inflight.size, 0);
});

test('global generation activation still aborts every shared detail consumer', async () => {
  const delayed = delayedFetch();
  const { client } = detailFixture(delayed.fetchImpl);
  const first = client.loadDetail('a');
  const second = client.loadDetail('b');
  await Promise.resolve();

  client.activate({
    generationId: 'g2',
    manifest: {},
    index: { products: [] },
    activatedAt: Date.now(),
  }, 'network');

  await Promise.all([expectAbort(first), expectAbort(second)]);
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 1 });
  assert.equal(client.inflight.size, 0);
});

function delayedGenerationClient() {
  const load = deferred();
  let calls = 0;
  let aborts = 0;
  const client = new CatalogGenerationClient({
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    fetchImpl: async () => { throw new Error('fetchImpl should not be called'); },
  });
  client.loadCompleteGeneration = signal => {
    calls += 1;
    return new Promise((resolve, reject) => {
      const onAbort = () => {
        aborts += 1;
        reject(new DOMException('aborted', 'AbortError'));
      };
      signal.addEventListener('abort', onAbort, { once: true });
      load.promise.then(
        value => {
          signal.removeEventListener('abort', onAbort);
          resolve(value);
        },
        error => {
          signal.removeEventListener('abort', onAbort);
          reject(error);
        },
      );
    });
  };
  return {
    client,
    resolve: generationId => load.resolve({
      generationId,
      manifest: {},
      index: { products: [] },
      activatedAt: Date.now(),
      source: 'network',
    }),
    stats: () => ({ calls, aborts }),
  };
}

test('shared generation refresh isolates first-caller cancellation', async () => {
  const delayed = delayedGenerationClient();
  const firstController = new AbortController();
  const secondController = new AbortController();
  const first = delayed.client.refresh({ signal: firstController.signal });
  const second = delayed.client.refresh({ signal: secondController.signal });
  await Promise.resolve();

  firstController.abort('view disposed');
  delayed.resolve('g1');

  await expectAbort(first);
  assert.equal((await second).generationId, 'g1');
  assert.equal(delayed.client.snapshot().generationId, 'g1');
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 0 });
  assert.equal(delayed.client.pending, null);
});

test('shared generation refresh isolates later-caller cancellation', async () => {
  const delayed = delayedGenerationClient();
  const firstController = new AbortController();
  const secondController = new AbortController();
  const first = delayed.client.refresh({ signal: firstController.signal });
  const second = delayed.client.refresh({ signal: secondController.signal });
  await Promise.resolve();

  secondController.abort('view disposed');
  delayed.resolve('g1');

  await expectAbort(second);
  assert.equal((await first).generationId, 'g1');
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 0 });
  assert.equal(delayed.client.pending, null);
});

test('shared generation transport aborts when all callers cancel', async () => {
  const delayed = delayedGenerationClient();
  const firstController = new AbortController();
  const secondController = new AbortController();
  const first = delayed.client.refresh({ signal: firstController.signal });
  const second = delayed.client.refresh({ signal: secondController.signal });
  await Promise.resolve();

  firstController.abort('first disposed');
  assert.equal(delayed.stats().aborts, 0);
  secondController.abort('second disposed');

  await Promise.all([expectAbort(first), expectAbort(second)]);
  assert.deepEqual(delayed.stats(), { calls: 1, aborts: 1 });
  await Promise.resolve();
  assert.equal(delayed.client.pending, null);
});

// Refresh replacement uses the same ownership boundary as detail deduplication.
test('a new refresh caller replaces an all-cancelled operation before old cleanup settles', async () => {
  const loads = [deferred(), deferred()];
  let calls = 0;
  const client = new CatalogGenerationClient({
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    fetchImpl: async () => { throw new Error('fetchImpl should not be called'); },
  });
  client.loadCompleteGeneration = signal => {
    const load = loads[calls];
    calls += 1;
    return new Promise((resolve, reject) => {
      const onAbort = () => reject(new DOMException('aborted', 'AbortError'));
      signal.addEventListener('abort', onAbort, { once: true });
      load.promise.then(
        value => {
          signal.removeEventListener('abort', onAbort);
          resolve(value);
        },
        error => {
          signal.removeEventListener('abort', onAbort);
          reject(error);
        },
      );
    });
  };
  const generation = generationId => ({
    generationId,
    manifest: {},
    index: { products: [] },
    activatedAt: Date.now(),
    source: 'network',
  });
  const controller = new AbortController();
  const cancelled = client.refresh({ signal: controller.signal });
  await Promise.resolve();
  controller.abort('disposed');

  const replacement = client.refresh();
  loads[1].resolve(generation('g2'));

  await expectAbort(cancelled);
  assert.equal((await replacement).generationId, 'g2');
  assert.equal(calls, 2);
  assert.equal(client.pending, null);
});

test('initialize preserves caller cancellation instead of activating cache fallback', async () => {
  const cache = new MemoryGenerationCache();
  await cache.putComplete({
    generationId: 'cached',
    manifest: {},
    index: { products: [] },
    activatedAt: Date.now(),
    source: 'cache',
  });
  const client = new CatalogGenerationClient({
    cache,
    maxRetries: 0,
    fetchImpl: async (_input, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
    }),
  });
  const controller = new AbortController();
  const pending = client.initialize({ signal: controller.signal });
  await Promise.resolve();
  controller.abort('navigation');

  await expectAbort(pending);
  assert.equal(client.snapshot(), null);
});
