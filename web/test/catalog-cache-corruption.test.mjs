import test from 'node:test';
import assert from 'node:assert/strict';
import {
  BrowserGenerationCache,
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';

const NOW = Date.parse('2026-07-19T17:30:00Z');
const BASE = 'https://example.test/app/';

function validVariant(overrides = {}) {
  return {
    variant_id: 'variant-1',
    grams: 3.5,
    current_price: 25,
    price_per_gram: 25 / 3.5,
    product_url: 'https://vendor.example/products/blue-dream?variant=variant-1',
    in_stock: true,
    ...overrides,
  };
}

function validProduct(overrides = {}) {
  return {
    product_id: 'product-1',
    vendor_id: 'vendor-1',
    vendor_name: 'Vendor One',
    strain_name: 'Blue Dream',
    default_variant_id: 'variant-1',
    variants: [validVariant()],
    ...overrides,
  };
}

function validGeneration(overrides = {}) {
  const {
    manifest: manifestOverrides = {},
    index: indexOverrides = {},
    ...generationOverrides
  } = overrides;
  const generationId = generationOverrides.generationId ?? 'generation-1';
  return {
    generationId,
    manifest: {
      schema_version: 'dropfinder-catalog-manifest-v4',
      generation_id: generationId,
      generated_at: new Date(NOW - 60_000).toISOString(),
      compact_index: { path: 'data/catalog-v4/index.json', sha256: 'a'.repeat(64) },
      ...manifestOverrides,
    },
    index: {
      generation_id: generationId,
      product_count: 1,
      in_stock_variant_count: 1,
      products: [validProduct()],
      ...indexOverrides,
    },
    manifestUrl: `${BASE}data/catalog-v4/manifest.json`,
    publicationBaseUrl: `${BASE}data/catalog-v4/`,
    activatedAt: NOW - 60_000,
    cachedAt: NOW - 30_000,
    source: 'cache',
    ...generationOverrides,
  };
}

function cacheWith(value) {
  return {
    value,
    reads: 0,
    writes: 0,
    deletes: 0,
    async getLastComplete() { this.reads += 1; return this.value; },
    async putComplete() { this.writes += 1; },
    async deleteLastComplete() { this.deletes += 1; this.value = null; return true; },
  };
}

async function withClock(run) {
  const original = Date.now;
  Date.now = () => NOW;
  try { await run(); }
  finally { Date.now = original; }
}

async function assertCorruptCacheRejected(value, expectedCode) {
  await withClock(async () => {
    const networkError = new Error('network unavailable');
    const cache = cacheWith(value);
    const events = [];
    const client = new CatalogGenerationClient({
      manifestUrl: `${BASE}data/catalog-v4/manifest.json`,
      fetchImpl: async () => { throw networkError; },
      cache,
      maxRetries: 0,
    });
    client.subscribe(event => events.push(event));

    await assert.rejects(client.initialize(), error => error === networkError);
    assert.equal(client.snapshot(), null);
    assert.equal(cache.reads, 1);
    assert.equal(cache.writes, 0);
    assert.equal(cache.deletes, 1);
    assert.equal(cache.value, null);
    assert.equal(events.length, 1);
    assert.equal(events[0].type, 'generation-cache-corrupt');
    assert.equal(events[0].code, expectedCode);
  });
}

test('cached generation validator quarantines malformed structural variants', async t => {
  const cases = [
    ['scalar cache value', 42, 'cache_value_invalid'],
    ['array cache value', [], 'cache_value_invalid'],
    ['missing generation id', { ...validGeneration(), generationId: '' }, 'cache_generation_id_missing'],
    ['missing manifest', { ...validGeneration(), manifest: null }, 'cache_manifest_invalid'],
    ['unsupported manifest schema', validGeneration({ manifest: { schema_version: 'old-schema' } }), 'cache_manifest_invalid'],
    ['missing index', { ...validGeneration(), index: null }, 'cache_index_invalid'],
    ['manifest generation mismatch', validGeneration({ manifest: { generation_id: 'other' } }), 'cache_generation_mismatch'],
    ['index generation mismatch', validGeneration({ index: { generation_id: 'other' } }), 'cache_generation_mismatch'],
    ['non-array products', validGeneration({ index: { products: 'not-an-array' } }), 'cache_products_invalid'],
    ['declared product count mismatch', validGeneration({ index: { product_count: 2 } }), 'cache_product_count_mismatch'],
    ['non-object product', validGeneration({ index: { products: [null] } }), 'cache_product_invalid'],
    ['missing product identity', validGeneration({ index: { products: [validProduct({ product_id: '' })] } }), 'cache_product_invalid'],
    ['non-array variants', validGeneration({ index: { products: [validProduct({ variants: 'not-an-array' })] } }), 'cache_variants_invalid'],
  ];

  for (const [name, value, code] of cases) {
    await t.test(name, () => assertCorruptCacheRejected(value, code));
  }
});

test('fresh valid fallback remains usable and honestly attributed', async () => {
  await withClock(async () => {
    const cache = cacheWith(validGeneration());
    const client = new CatalogGenerationClient({
      manifestUrl: `${BASE}data/catalog-v4/manifest.json`,
      fetchImpl: async () => { throw new Error('offline'); },
      cache,
      maxRetries: 0,
    });
    const result = await client.initialize();
    assert.equal(result.generationId, 'generation-1');
    assert.equal(result.source, 'cache-fallback');
    assert.equal(client.snapshot().source, 'cache-fallback');
    assert.equal(cache.deletes, 0);
    assert.equal(cache.writes, 0);
  });
});

test('over-age but structurally valid cache follows the existing freshness policy', async () => {
  await withClock(async () => {
    const cache = cacheWith(validGeneration({
      cachedAt: NOW - 31 * 60_000,
      manifest: { generated_at: new Date(NOW - 31 * 60_000).toISOString() },
    }));
    const client = new CatalogGenerationClient({
      manifestUrl: `${BASE}data/catalog-v4/manifest.json`,
      fetchImpl: async () => { throw new Error('offline'); },
      cache,
      maxRetries: 0,
      maxFallbackAgeMs: 30 * 60_000,
    });
    await assert.rejects(client.initialize(), error => error?.code === 'cache_fallback_stale');
    assert.equal(cache.deletes, 0);
  });
});

function memoryCacheStorage() {
  const records = new Map();
  return {
    records,
    async open() {
      return {
        async match(key) { return records.get(String(key)); },
        async put(key, response) { records.set(String(key), response.clone()); },
        async delete(key) { return records.delete(String(key)); },
      };
    },
  };
}

test('BrowserGenerationCache deletes the persistent record on quarantine', async () => {
  await withClock(async () => {
    const cacheStorage = memoryCacheStorage();
    const cache = new BrowserGenerationCache({ cacheStorage, deploymentUrl: BASE });
    await cache.putComplete(validGeneration({ index: { products: 'not-an-array' } }));
    assert.equal(cacheStorage.records.size, 1);
    const client = new CatalogGenerationClient({
      manifestUrl: `${BASE}data/catalog-v4/manifest.json`,
      deploymentUrl: BASE,
      fetchImpl: async () => { throw new Error('offline'); },
      cache,
      maxRetries: 0,
    });
    await assert.rejects(client.initialize(), /offline/);
    assert.equal(cacheStorage.records.size, 0);
  });
});

test('MemoryGenerationCache supports explicit quarantine deletion', async () => {
  await withClock(async () => {
    const cache = new MemoryGenerationCache();
    await cache.putComplete(validGeneration());
    assert.ok(await cache.getLastComplete());
    assert.equal(await cache.deleteLastComplete(), true);
    assert.equal(await cache.getLastComplete(), null);
    assert.equal(await cache.deleteLastComplete(), false);
  });
});
