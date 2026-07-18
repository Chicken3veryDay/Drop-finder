import test from 'node:test';
import assert from 'node:assert/strict';

import { CatalogGenerationClient } from '../src/platform/catalog/catalog-generation-client.js';

function streamingResponse(chunks) {
  let pulls = 0;
  let producedBytes = 0;
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
  });
  return {
    response: new Response(stream),
    stats: () => ({ pulls, producedBytes }),
  };
}

test('invalid effective byte limits fail before fetch', async () => {
  for (const maxBytes of [Number.NaN, Number.POSITIVE_INFINITY, -1, 1.5]) {
    let calls = 0;
    const client = new CatalogGenerationClient({
      fetchImpl: async () => {
        calls += 1;
        return new Response('{}');
      },
    });

    await assert.rejects(
      client.fetchBounded('https://x/asset.json', { maxBytes }),
      error => error.code === 'invalid_size_limit',
    );
    assert.equal(calls, 0);
  }
});

test('malformed compact-index byte metadata is rejected before the index fetch', async () => {
  const manifest = {
    schema_version: 4,
    generation_id: 'g1',
    index: {
      url: 'https://x/index.json',
      bytes: 'not-a-number',
    },
  };
  let calls = 0;
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    fetchImpl: async () => {
      calls += 1;
      return new Response(JSON.stringify(manifest));
    },
  });

  await assert.rejects(
    client.initialize(),
    error => error.code === 'invalid_size_limit',
  );
  assert.equal(calls, 1);
});

test('non-finite detail metadata preserves the configured hard ceiling', async () => {
  let calls = 0;
  let stats;
  const client = new CatalogGenerationClient({
    maxDetailBytes: 8,
    maxRetries: 0,
    fetchImpl: async () => {
      calls += 1;
      const result = streamingResponse([
        new Uint8Array(4),
        new Uint8Array(4),
        new Uint8Array(4),
      ]);
      stats = result.stats;
      return result.response;
    },
  });
  client.activate({
    generationId: 'g1',
    manifest: {
      details: {
        p1: {
          url: 'https://x/detail.json',
          bytes: Number.POSITIVE_INFINITY,
        },
      },
    },
    index: { products: [{ product_id: 'p1' }] },
    manifestUrl: 'https://x/manifest.json',
    publicationBaseUrl: 'https://x/',
    activatedAt: 1,
  }, 'test');

  await assert.rejects(
    client.loadDetail('p1'),
    error => error.code === 'asset_oversized',
  );
  assert.equal(calls, 1);
  assert.ok(stats().producedBytes <= 16, `produced ${stats().producedBytes} bytes for an 8-byte cap`);
});
