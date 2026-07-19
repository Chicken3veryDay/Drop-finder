import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { CatalogGenerationClient } from '../src/platform/catalog/catalog-generation-client.js';

const sha256 = text => createHash('sha256').update(text).digest('hex');

function generationFetch(generationId = 'network-current') {
  const index = JSON.stringify({
    generation_id: generationId,
    products: [{ product_id: 'p1', variants: [] }],
  });
  const manifest = {
    schema_version: 4,
    generation_id: generationId,
    generated_at: new Date().toISOString(),
    index: {
      url: 'https://example.test/index.json',
      bytes: index.length,
      sha256: sha256(index),
    },
  };
  return async input => {
    const url = String(input);
    if (url.endsWith('manifest.json')) {
      const body = JSON.stringify(manifest);
      return new Response(body, {
        headers: { 'content-length': String(body.length) },
      });
    }
    if (url.endsWith('index.json')) {
      return new Response(index, {
        headers: { 'content-length': String(index.length) },
      });
    }
    return new Response('', { status: 404 });
  };
}

function cachedGeneration(generationId = 'cached-old') {
  return Object.freeze({
    generationId,
    manifest: { generation_id: generationId, generated_at: new Date().toISOString() },
    index: { generation_id: generationId, products: [] },
    activatedAt: Date.now(),
    cachedAt: Date.now(),
    source: 'cache',
  });
}

function clientWith(cache, fetchImpl = generationFetch()) {
  return new CatalogGenerationClient({
    manifestUrl: 'https://example.test/manifest.json',
    fetchImpl,
    cache,
    maxRetries: 0,
  });
}

test('quota failure preserves a verified network generation with no prior cache', async () => {
  const quota = new DOMException('quota full', 'QuotaExceededError');
  const events = [];
  const client = clientWith({
    async putComplete() { throw quota; },
    async getLastComplete() { return null; },
  });
  client.subscribe(event => events.push(event));

  const generation = await client.initialize();
  assert.equal(generation.generationId, 'network-current');
  assert.equal(generation.source, 'network');
  assert.equal(client.snapshot().generationId, 'network-current');
  assert.equal(client.snapshot().source, 'network');
  assert.ok(events.some(event => (
    event.type === 'generation-cache-degraded'
    && event.generationId === 'network-current'
    && event.code === 'cache_quota_exceeded'
    && event.error === quota
  )));
  assert.ok(events.some(event => event.type === 'generation-activated'));
});

test('storage failure never replaces verified current data with an older cache', async () => {
  const client = clientWith({
    async putComplete() { throw new DOMException('blocked', 'SecurityError'); },
    async getLastComplete() { return cachedGeneration(); },
  });
  const events = [];
  client.subscribe(event => events.push(event));

  const generation = await client.initialize();
  assert.equal(generation.generationId, 'network-current');
  assert.equal(client.snapshot().generationId, 'network-current');
  assert.equal(client.snapshot().source, 'network');
  assert.ok(events.some(event => (
    event.type === 'generation-cache-degraded'
    && event.code === 'cache_security_denied'
  )));
});

test('generic persistence failures use a stable degraded-offline code', async () => {
  const events = [];
  const client = clientWith({
    async putComplete() { throw new Error('storage unavailable'); },
    async getLastComplete() { return null; },
  });
  client.subscribe(event => events.push(event));

  await client.initialize();
  assert.ok(events.some(event => (
    event.type === 'generation-cache-degraded'
    && event.code === 'cache_persistence_failed'
  )));
});

test('true network validation failure still uses the last complete cache', async () => {
  const old = cachedGeneration();
  let writes = 0;
  const client = clientWith({
    async putComplete() { writes += 1; },
    async getLastComplete() { return old; },
  }, async input => {
    if (String(input).endsWith('manifest.json')) {
      return new Response(JSON.stringify({
        schema_version: 4,
        generation_id: 'broken',
        index: { url: 'https://example.test/index.json' },
      }));
    }
    return new Response(JSON.stringify({ generation_id: 'wrong', products: [] }));
  });

  const generation = await client.initialize();
  assert.equal(generation.generationId, 'cached-old');
  assert.equal(generation.source, 'cache-fallback');
  assert.equal(writes, 0);
});

test('a later successful refresh restores persistence without replacing live products', async () => {
  let failWrites = true;
  let successfulWrites = 0;
  const cache = {
    async putComplete(value) {
      if (failWrites) throw new DOMException('quota full', 'QuotaExceededError');
      successfulWrites += 1;
      this.complete = value;
    },
    async getLastComplete() { return this.complete ?? null; },
  };
  const client = clientWith(cache);
  const first = await client.initialize();
  assert.equal(first.generationId, 'network-current');
  failWrites = false;

  const refreshed = await client.refresh();
  assert.equal(refreshed.generationId, 'network-current');
  assert.equal(client.snapshot().generationId, 'network-current');
  assert.equal(successfulWrites, 1);
  assert.equal(cache.complete.generationId, 'network-current');
});
