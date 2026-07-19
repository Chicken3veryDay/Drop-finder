import test from 'node:test';
import assert from 'node:assert/strict';
import { CatalogGenerationClient, MemoryGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';

function streamingResponse({ chunks, headers = {} }) {
  let pulls = 0;
  let producedBytes = 0;
  let cancelled = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (pulls >= chunks.length) {
        controller.close();
        return;
      }
      const chunk = chunks[pulls];
      pulls += 1;
      producedBytes += chunk.byteLength;
      controller.enqueue(chunk);
    },
    cancel() { cancelled += 1; },
  });
  return {
    response: new Response(stream, { headers }),
    stats: () => ({ pulls, producedBytes, cancelled }),
  };
}

test('headerless oversized catalog assets stop at the streaming bound and are not retried', async () => {
  let calls = 0;
  let stats;
  const client = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => {
      calls += 1;
      const result = streamingResponse({ chunks: Array.from({ length: 20 }, () => new Uint8Array(4)) });
      stats = result.stats;
      return result.response;
    },
  });

  await assert.rejects(
    client.fetchBounded('https://x/asset.json', { maxBytes: 8 }),
    error => error.code === 'asset_oversized',
  );
  assert.equal(calls, 1);
  assert.ok(stats().producedBytes <= 16, `produced ${stats().producedBytes} bytes for an 8-byte cap`);
  assert.equal(stats().cancelled, 1);
});

test('understated content-length remains bounded by actual streamed bytes', async () => {
  let stats;
  const client = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => {
      const result = streamingResponse({
        chunks: [new Uint8Array(4), new Uint8Array(4), new Uint8Array(4), new Uint8Array(4)],
        headers: { 'content-length': '4' },
      });
      stats = result.stats;
      return result.response;
    },
  });

  await assert.rejects(
    client.fetchBounded('https://x/asset.json', { maxBytes: 8 }),
    error => error.code === 'asset_oversized',
  );
  assert.ok(stats().producedBytes <= 16);
  assert.equal(stats().cancelled, 1);
});

test('honest oversized content-length rejects without reading the body', async () => {
  let cancelled = 0;
  let reads = 0;
  const client = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'content-length': '32' }),
      body: {
        cancel: async () => { cancelled += 1; },
        getReader: () => {
          reads += 1;
          throw new Error('body reader must not be created');
        },
      },
    }),
  });

  await assert.rejects(
    client.fetchBounded('https://x/asset.json', { maxBytes: 8 }),
    error => error.code === 'asset_oversized',
  );
  assert.equal(reads, 0);
  assert.equal(cancelled, 1);
});

test('catalog stream accepts bodies at and below the byte limit', async () => {
  for (const size of [7, 8]) {
    const client = new CatalogGenerationClient({
      maxRetries: 0,
      fetchImpl: async () => new Response(new Uint8Array(size)),
    });
    const response = await client.fetchBounded('https://x/asset.json', { maxBytes: 8 });
    assert.equal((await response.arrayBuffer()).byteLength, size);
  }
});

test('transient failures retry while deterministic HTTP failures do not', async () => {
  let transportCalls = 0;
  const transient = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => {
      transportCalls += 1;
      if (transportCalls < 3) throw new TypeError('network reset');
      return new Response('{}');
    },
  });
  await transient.fetchBounded('https://x/asset.json', { maxBytes: 8 });
  assert.equal(transportCalls, 3);

  let missingCalls = 0;
  const missing = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => {
      missingCalls += 1;
      return new Response('', { status: 404 });
    },
  });
  await assert.rejects(
    missing.fetchBounded('https://x/missing.json', { maxBytes: 8 }),
    error => error.code === 'http_error',
  );
  assert.equal(missingCalls, 1);

  let unavailableCalls = 0;
  const unavailable = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => {
      unavailableCalls += 1;
      return new Response('', { status: 503 });
    },
  });
  await assert.rejects(
    unavailable.fetchBounded('https://x/unavailable.json', { maxBytes: 8 }),
    error => error.code === 'http_error',
  );
  assert.equal(unavailableCalls, 3);
});

test('cached generation fallback activates after one bounded oversized attempt', async () => {
  const cache = new MemoryGenerationCache();
  const cachedAt = Date.now();
  await cache.putComplete({
    generationId: 'cached',
    manifest: { generated_at: new Date(cachedAt).toISOString() },
    index: { products: [] },
    activatedAt: cachedAt,
    source: 'cache',
  });
  let calls = 0;
  let stats;
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    cache,
    maxRetries: 2,
    fetchImpl: async () => {
      calls += 1;
      const result = streamingResponse({ chunks: Array.from({ length: 20 }, () => new Uint8Array(64 * 1024)) });
      stats = result.stats;
      return result.response;
    },
  });
  const generation = await client.initialize();
  assert.equal(generation.generationId, 'cached');
  assert.equal(calls, 1);
  assert.ok(stats().producedBytes <= (512 * 1024) + (2 * 64 * 1024));
  assert.equal(stats().cancelled, 1);
});

test('abort during a bounded stream cancels the reader and prevents publication', async () => {
  let cancelled = 0;
  let pulls = 0;
  const stream = new ReadableStream({
    pull(controller) {
      pulls += 1;
      if (pulls === 1) {
        controller.enqueue(new Uint8Array(4));
        return;
      }
      return new Promise(() => {});
    },
    cancel() { cancelled += 1; },
  });
  const controller = new AbortController();
  const client = new CatalogGenerationClient({
    maxRetries: 2,
    fetchImpl: async () => new Response(stream),
  });
  const pending = client.fetchBounded('https://x/asset.json', { maxBytes: 32, signal: controller.signal });
  await new Promise(resolve => setTimeout(resolve, 0));
  controller.abort('superseded');
  await assert.rejects(pending, error => error.name === 'AbortError');
  assert.equal(cancelled, 1);
});

test('content validation failures remain single-attempt operations', async () => {
  let malformedCalls = 0;
  const malformed = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    maxRetries: 2,
    fetchImpl: async () => {
      malformedCalls += 1;
      return new Response('not-json');
    },
  });
  await assert.rejects(malformed.initialize(), SyntaxError);
  assert.equal(malformedCalls, 1);

  const indexText = JSON.stringify({ generation_id: 'g1', products: [] });
  const hashManifest = {
    schema_version: 4,
    generation_id: 'g1',
    index: { url: 'https://x/index.json', bytes: indexText.length, sha256: '0'.repeat(64) },
  };
  let hashCalls = 0;
  const hashMismatch = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    maxRetries: 2,
    fetchImpl: async input => {
      hashCalls += 1;
      return String(input).includes('manifest')
        ? new Response(JSON.stringify(hashManifest))
        : new Response(indexText);
    },
  });
  await assert.rejects(hashMismatch.initialize(), error => error.code === 'hash_mismatch');
  assert.equal(hashCalls, 2);

  const generationManifest = {
    schema_version: 4,
    generation_id: 'g1',
    index: { url: 'https://x/index.json', bytes: indexText.length },
  };
  let generationCalls = 0;
  const generationMismatch = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    maxRetries: 2,
    fetchImpl: async input => {
      generationCalls += 1;
      return String(input).includes('manifest')
        ? new Response(JSON.stringify(generationManifest))
        : new Response(JSON.stringify({ generation_id: 'g2', products: [] }));
    },
  });
  await assert.rejects(generationMismatch.initialize(), error => error.code === 'generation_mismatch');
  assert.equal(generationCalls, 2);
});
