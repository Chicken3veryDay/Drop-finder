import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BrowserGenerationCache,
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';

function validCachedGeneration(generationId = 'cached-current') {
  const now = Date.now();
  return Object.freeze({
    generationId,
    manifest: {
      schema_version: 4,
      generation_id: generationId,
      generated_at: new Date(now - 1_000).toISOString(),
      index: { url: 'https://example.test/data/catalog-v4/index.json' },
    },
    index: {
      generation_id: generationId,
      products: [{ product_id: 'p1', variants: [] }],
    },
    manifestUrl: 'https://example.test/data/catalog-v4/manifest.json',
    publicationBaseUrl: 'https://example.test/data/catalog-v4/',
    activatedAt: now - 1_000,
    cachedAt: now - 1_000,
    source: 'cache',
  });
}

function failingFetch() {
  return Promise.resolve(new Response('', { status: 503 }));
}

function clientFor(cache) {
  return new CatalogGenerationClient({
    manifestUrl: 'https://example.test/data/catalog-v4/manifest.json',
    fetchImpl: failingFetch,
    cache,
    maxRetries: 0,
  });
}

test('structurally corrupt cached generations are quarantined and never activated or rewritten', async () => {
  const valid = validCachedGeneration();
  const invalid = [
    { ...valid, generationId: '' },
    { ...valid, manifest: null },
    { ...valid, manifest: { ...valid.manifest, schema_version: 3 } },
    { ...valid, manifest: { ...valid.manifest, generation_id: 'other' } },
    { ...valid, index: { ...valid.index, generation_id: 'other' } },
    { ...valid, index: { ...valid.index, products: 'not-an-array' } },
    { ...valid, index: { ...valid.index, products: [null] } },
    { ...valid, index: { ...valid.index, products: [{}] } },
  ];

  for (const cached of invalid) {
    let deletes = 0;
    let writes = 0;
    const events = [];
    const client = clientFor({
      async getLastComplete() { return cached; },
      async deleteLastComplete() { deletes += 1; return true; },
      async putComplete() { writes += 1; },
    });
    client.subscribe(event => events.push(event));

    await assert.rejects(client.initialize(), error => error?.code === 'http_error');
    assert.equal(client.snapshot(), null);
    assert.equal(deletes, 1);
    assert.equal(writes, 0);
    assert.ok(events.some(event => event.type === 'generation-cache-corrupt'));
    assert.ok(!events.some(event => event.type === 'generation-activated'));
  }
});

test('a structurally valid current cache remains an honest cache fallback', async () => {
  let deletes = 0;
  let writes = 0;
  const client = clientFor({
    async getLastComplete() { return validCachedGeneration(); },
    async deleteLastComplete() { deletes += 1; },
    async putComplete() { writes += 1; },
  });

  const generation = await client.initialize();
  assert.equal(generation.generationId, 'cached-current');
  assert.equal(generation.source, 'cache-fallback');
  assert.equal(client.snapshot().source, 'cache-fallback');
  assert.equal(deletes, 0);
  assert.equal(writes, 0);
});

test('BrowserGenerationCache deletes malformed JSON records instead of retrying them forever', async () => {
  let deletes = 0;
  const opened = {
    async match() { return new Response('{broken-json'); },
    async delete() { deletes += 1; return true; },
  };
  const cache = new BrowserGenerationCache({
    cacheStorage: { async open() { return opened; } },
    deploymentUrl: 'https://example.test/data/catalog-v4/',
  });

  assert.equal(await cache.getLastComplete(), null);
  assert.equal(deletes, 1);
});

test('BrowserGenerationCache deletes incompatible record envelopes', async () => {
  let deletes = 0;
  const opened = {
    async match() {
      return new Response(JSON.stringify({
        schemaVersion: 'old-cache-schema',
        deploymentKey: 'https://example.test/data/catalog-v4/',
        cachedAt: Date.now(),
        generation: validCachedGeneration(),
      }));
    },
    async delete() { deletes += 1; return true; },
  };
  const cache = new BrowserGenerationCache({
    cacheStorage: { async open() { return opened; } },
    deploymentUrl: 'https://example.test/data/catalog-v4/',
  });

  assert.equal(await cache.getLastComplete(), null);
  assert.equal(deletes, 1);
});

test('MemoryGenerationCache supports explicit quarantine', async () => {
  const cache = new MemoryGenerationCache();
  await cache.putComplete(validCachedGeneration());
  assert.ok(await cache.getLastComplete());
  assert.equal(await cache.deleteLastComplete(), true);
  assert.equal(await cache.getLastComplete(), null);
});
