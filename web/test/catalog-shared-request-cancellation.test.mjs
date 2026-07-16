import test from 'node:test';
import assert from 'node:assert/strict';
import { CatalogGenerationClient, MemoryGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';

function fixtureGeneration(generationId = 'g1') {
  const detail = JSON.stringify({
    generation_id: generationId,
    products: [{ id: 'p0' }, { id: 'p1' }],
  });
  const descriptor = {
    url: `https://example.test/${generationId}/shared-detail.json`,
    bytes: detail.length,
  };
  return {
    generation: {
      generationId,
      manifest: {
        schema_version: 4,
        generation_id: generationId,
        details: { p0: descriptor, p1: descriptor },
      },
      index: {
        generation_id: generationId,
        products: [{ id: 'p0' }, { id: 'p1' }],
      },
      manifestUrl: `https://example.test/${generationId}/manifest.json`,
      publicationBaseUrl: `https://example.test/${generationId}/`,
      activatedAt: Date.now(),
      source: 'fixture',
    },
    detail,
  };
}

function deferredFetch(body) {
  const calls = [];
  const fetchImpl = (_input, { signal }) => new Promise((resolve, reject) => {
    const call = {
      aborted: false,
      release() {
        resolve(new Response(body, {
          headers: { 'content-length': String(body.length) },
        }));
      },
    };
    signal.addEventListener('abort', () => {
      call.aborted = true;
      reject(new DOMException('aborted', 'AbortError'));
    }, { once: true });
    calls.push(call);
  });
  return {
    calls,
    fetchImpl,
    async waitForCalls(count) {
      while (calls.length < count) await new Promise(resolve => setImmediate(resolve));
    },
  };
}

function clientWithDetailFetch() {
  const { generation, detail } = fixtureGeneration();
  const transport = deferredFetch(detail);
  const client = new CatalogGenerationClient({
    fetchImpl: transport.fetchImpl,
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  client.activate(generation, 'fixture');
  return { client, transport };
}

test('cancelling the first detail consumer does not abort a later active consumer', async () => {
  const { client, transport } = clientWithDetailFetch();
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('p0', { signal: firstController.signal });
  const second = client.loadDetail('p1', { signal: secondController.signal });
  await transport.waitForCalls(1);
  firstController.abort('first product collapsed');

  await assert.rejects(first, error => error?.name === 'AbortError');
  assert.equal(transport.calls[0].aborted, false);
  transport.calls[0].release();

  const detail = await second;
  assert.equal(detail.generation_id, 'g1');
  assert.equal(secondController.signal.aborted, false);
  assert.equal(transport.calls.length, 1);
});

test('cancelling a later detail consumer does not abort the first active consumer', async () => {
  const { client, transport } = clientWithDetailFetch();
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('p0', { signal: firstController.signal });
  const second = client.loadDetail('p1', { signal: secondController.signal });
  await transport.waitForCalls(1);
  secondController.abort('second product collapsed');

  await assert.rejects(second, error => error?.name === 'AbortError');
  assert.equal(transport.calls[0].aborted, false);
  transport.calls[0].release();

  const detail = await first;
  assert.equal(detail.generation_id, 'g1');
  assert.equal(firstController.signal.aborted, false);
  assert.equal(transport.calls.length, 1);
});

test('the shared detail transport aborts and detaches after every consumer cancels', async () => {
  const { client, transport } = clientWithDetailFetch();
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.loadDetail('p0', { signal: firstController.signal });
  const second = client.loadDetail('p1', { signal: secondController.signal });
  await transport.waitForCalls(1);
  firstController.abort('first product collapsed');
  secondController.abort('second product collapsed');

  await Promise.all([
    assert.rejects(first, error => error?.name === 'AbortError'),
    assert.rejects(second, error => error?.name === 'AbortError'),
  ]);
  assert.equal(transport.calls[0].aborted, true);
  assert.equal(client.inflight.size, 0);
});

test('a replacement detail consumer does not join an orphaned aborting transport', async () => {
  const { client, transport } = clientWithDetailFetch();
  const firstController = new AbortController();
  const replacementController = new AbortController();

  const first = client.loadDetail('p0', { signal: firstController.signal });
  await transport.waitForCalls(1);
  firstController.abort('product collapsed');
  await assert.rejects(first, error => error?.name === 'AbortError');

  const replacement = client.loadDetail('p1', { signal: replacementController.signal });
  await transport.waitForCalls(2);
  assert.equal(transport.calls[0].aborted, true);
  assert.equal(transport.calls[1].aborted, false);
  transport.calls[1].release();

  const detail = await replacement;
  assert.equal(detail.generation_id, 'g1');
  assert.equal(transport.calls.length, 2);
});

test('catalog activation still aborts every consumer of an obsolete detail request', async () => {
  const { client, transport } = clientWithDetailFetch();
  const first = client.loadDetail('p0');
  const second = client.loadDetail('p1');
  await transport.waitForCalls(1);

  client.activate(fixtureGeneration('g2').generation, 'fixture');

  await Promise.all([
    assert.rejects(first, error => error?.name === 'AbortError'),
    assert.rejects(second, error => error?.name === 'AbortError'),
  ]);
  assert.equal(transport.calls[0].aborted, true);
  assert.equal(client.inflight.size, 0);
});

function deferredGenerationLoad(client, generation) {
  const calls = [];
  client.loadCompleteGeneration = signal => new Promise((resolve, reject) => {
    const call = {
      aborted: false,
      release() { resolve(generation); },
    };
    signal.addEventListener('abort', () => {
      call.aborted = true;
      reject(new DOMException('aborted', 'AbortError'));
    }, { once: true });
    calls.push(call);
  });
  return {
    calls,
    async waitForCalls(count) {
      while (calls.length < count) await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('cancelling the first refresh caller does not poison a later active caller', async () => {
  const client = new CatalogGenerationClient({
    fetchImpl: async () => new Response('', { status: 500 }),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  const transport = deferredGenerationLoad(client, fixtureGeneration().generation);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.refresh({ signal: firstController.signal });
  const second = client.refresh({ signal: secondController.signal });
  await transport.waitForCalls(1);
  firstController.abort('first refresh caller left');

  await assert.rejects(first, error => error?.name === 'AbortError');
  assert.equal(transport.calls[0].aborted, false);
  transport.calls[0].release();

  const generation = await second;
  assert.equal(generation.generationId, 'g1');
  assert.equal(client.snapshot().generationId, 'g1');
  assert.equal(transport.calls.length, 1);
});

test('cancelling a later refresh caller does not poison the first active caller', async () => {
  const client = new CatalogGenerationClient({
    fetchImpl: async () => new Response('', { status: 500 }),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  const transport = deferredGenerationLoad(client, fixtureGeneration().generation);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.refresh({ signal: firstController.signal });
  const second = client.refresh({ signal: secondController.signal });
  await transport.waitForCalls(1);
  secondController.abort('second refresh caller left');

  await assert.rejects(second, error => error?.name === 'AbortError');
  assert.equal(transport.calls[0].aborted, false);
  transport.calls[0].release();

  const generation = await first;
  assert.equal(generation.generationId, 'g1');
  assert.equal(client.snapshot().generationId, 'g1');
  assert.equal(transport.calls.length, 1);
});

test('the shared refresh transport aborts and detaches after every caller cancels', async () => {
  const client = new CatalogGenerationClient({
    fetchImpl: async () => new Response('', { status: 500 }),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
  });
  const transport = deferredGenerationLoad(client, fixtureGeneration().generation);
  const firstController = new AbortController();
  const secondController = new AbortController();

  const first = client.refresh({ signal: firstController.signal });
  const second = client.refresh({ signal: secondController.signal });
  await transport.waitForCalls(1);
  firstController.abort('first refresh caller left');
  secondController.abort('second refresh caller left');

  await Promise.all([
    assert.rejects(first, error => error?.name === 'AbortError'),
    assert.rejects(second, error => error?.name === 'AbortError'),
  ]);
  assert.equal(transport.calls[0].aborted, true);
  assert.equal(client.pending, null);
});

test('an aborted initialize caller never falls back to cached catalog data', async () => {
  const cache = new MemoryGenerationCache();
  await cache.putComplete(fixtureGeneration('cached').generation);
  const client = new CatalogGenerationClient({
    fetchImpl: async () => new Response('', { status: 500 }),
    cache,
    maxRetries: 0,
  });
  const transport = deferredGenerationLoad(client, fixtureGeneration('network').generation);
  const controller = new AbortController();

  const pending = client.initialize({ signal: controller.signal });
  await transport.waitForCalls(1);
  controller.abort('initialization caller left');

  await assert.rejects(pending, error => error?.name === 'AbortError');
  assert.equal(client.snapshot(), null);
  assert.equal(transport.calls[0].aborted, true);
});
