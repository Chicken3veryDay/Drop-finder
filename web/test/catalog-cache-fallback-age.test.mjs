import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';

const NOW = Date.parse('2026-07-19T15:00:00Z');
const MAX_FALLBACK_AGE_MS = 30 * 60_000;
const sha256 = text => createHash('sha256').update(text).digest('hex');

function cachedGeneration({
  generationId = 'cached',
  cachedAt = NOW - 5 * 60_000,
  generatedAt = NOW - 5 * 60_000,
} = {}) {
  return Object.freeze({
    generationId,
    manifest: {
      generation_id: generationId,
      generated_at: typeof generatedAt === 'number' ? new Date(generatedAt).toISOString() : generatedAt,
    },
    index: { generation_id: generationId, products: [] },
    publicationBaseUrl: 'https://example.test/data/catalog-v4/',
    activatedAt: cachedAt,
    cachedAt,
    source: 'cache',
  });
}

function failingFetch() {
  return Promise.resolve(new Response('', { status: 503 }));
}

function clientFor(cached, options = {}) {
  return new CatalogGenerationClient({
    manifestUrl: 'https://example.test/data/catalog-v4/manifest.json',
    fetchImpl: options.fetchImpl ?? failingFetch,
    cache: {
      async putComplete() {},
      async getLastComplete() { return cached; },
    },
    maxRetries: 0,
    maxFallbackAgeMs: options.maxFallbackAgeMs ?? MAX_FALLBACK_AGE_MS,
  });
}

async function withClock(run) {
  const original = Date.now;
  Date.now = () => NOW;
  try {
    await run();
  } finally {
    Date.now = original;
  }
}

test('cached generation just inside the fallback bound is accepted with honest provenance', async () => {
  await withClock(async () => {
    const client = clientFor(cachedGeneration({
      cachedAt: NOW - MAX_FALLBACK_AGE_MS + 1,
      generatedAt: NOW - MAX_FALLBACK_AGE_MS + 1,
    }));
    const generation = await client.initialize();
    assert.equal(generation.generationId, 'cached');
    assert.equal(generation.source, 'cache-fallback');
    assert.equal(client.snapshot().source, 'cache-fallback');
  });
});

test('cached generation exactly at the fallback bound is accepted', async () => {
  await withClock(async () => {
    const generation = await clientFor(cachedGeneration({
      cachedAt: NOW - MAX_FALLBACK_AGE_MS,
      generatedAt: NOW - MAX_FALLBACK_AGE_MS,
    })).initialize();
    assert.equal(generation.source, 'cache-fallback');
  });
});

test('over-age cached generation is rejected and never activated', async () => {
  await withClock(async () => {
    const client = clientFor(cachedGeneration({
      cachedAt: NOW - MAX_FALLBACK_AGE_MS - 1,
      generatedAt: NOW - MAX_FALLBACK_AGE_MS - 1,
    }));
    await assert.rejects(client.initialize(), error => error?.code === 'cache_fallback_stale');
    assert.equal(client.snapshot(), null);
  });
});

test('an old publication cannot become fresh merely by being cached again', async () => {
  await withClock(async () => {
    const client = clientFor(cachedGeneration({
      cachedAt: NOW - 1_000,
      generatedAt: Date.parse('2019-01-01T00:00:00Z'),
    }));
    await assert.rejects(client.initialize(), error => error?.code === 'cache_fallback_stale');
    assert.equal(client.snapshot(), null);
  });
});

test('missing, malformed, and materially future timestamps fail closed', async () => {
  await withClock(async () => {
    const base = cachedGeneration();
    const invalid = [
      { ...base, cachedAt: undefined },
      { ...base, manifest: { generation_id: base.generationId } },
      { ...base, manifest: { ...base.manifest, generated_at: 'not-a-date' } },
      { ...base, cachedAt: NOW + 60_001 },
      { ...base, manifest: { ...base.manifest, generated_at: new Date(NOW + 60_001).toISOString() } },
    ];
    for (const generation of invalid) {
      const client = clientFor(generation);
      await assert.rejects(client.initialize(), error => error?.code === 'cache_fallback_stale');
      assert.equal(client.snapshot(), null);
    }
  });
});

test('MemoryGenerationCache persists a trustworthy cachedAt timestamp', async () => {
  await withClock(async () => {
    const cache = new MemoryGenerationCache();
    await cache.putComplete(cachedGeneration({ cachedAt: NOW - 10_000 }));
    const stored = await cache.getLastComplete();
    assert.equal(stored.cachedAt, NOW);
    assert.equal(stored.manifest.generated_at, new Date(NOW - 5 * 60_000).toISOString());
  });
});

test('a verified network generation supersedes an accepted fallback', async () => {
  await withClock(async () => {
    let networkAvailable = false;
    const generationId = 'network-current';
    const index = JSON.stringify({ generation_id: generationId, products: [] });
    const manifest = {
      schema_version: 4,
      generation_id: generationId,
      generated_at: new Date(NOW).toISOString(),
      index: {
        url: 'https://example.test/data/catalog-v4/index.json',
        bytes: index.length,
        sha256: sha256(index),
      },
    };
    const fetchImpl = async input => {
      if (!networkAvailable) return new Response('', { status: 503 });
      if (String(input).endsWith('manifest.json')) {
        const body = JSON.stringify(manifest);
        return new Response(body, { headers: { 'content-length': String(body.length) } });
      }
      return new Response(index, { headers: { 'content-length': String(index.length) } });
    };
    const client = clientFor(cachedGeneration(), { fetchImpl });
    const fallback = await client.initialize();
    assert.equal(fallback.source, 'cache-fallback');
    networkAvailable = true;
    const current = await client.refresh();
    assert.equal(current.generationId, generationId);
    assert.equal(current.source, 'network');
    assert.equal(client.snapshot().source, 'network');
  });
});
