import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';

function sameGenerationFixture() {
  const index = JSON.stringify({ generation_id: 'g1', products: [] });
  const manifest = {
    schema_version: 4,
    generation_id: 'g1',
    index: { url: 'https://x/index.json' },
  };
  return { index, manifest };
}

test('catalog client records successful same-generation refresh freshness', async () => {
  const { index, manifest } = sameGenerationFixture();
  let calls = 0;
  const fetchImpl = async input => {
    calls += 1;
    return String(input).includes('manifest')
      ? new Response(JSON.stringify(manifest))
      : new Response(index);
  };
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    fetchImpl,
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    staleMs: 60_000,
  });
  const activations = [];
  client.subscribe(event => activations.push(event));

  await client.initialize();
  assert.equal(calls, 2);
  client.active = Object.freeze({ ...client.snapshot(), activatedAt: 0 });
  client.lastNetworkRefreshAt = 0;

  await client.initialize();
  assert.equal(calls, 4);
  assert.equal(activations.length, 1);
  await client.initialize();
  assert.equal(calls, 4);

  await client.initialize({ force: true });
  assert.equal(calls, 6);
  assert.equal(activations.length, 1);
});

test('catalog client does not mark cached fallback as a successful network refresh', async () => {
  const { index, manifest } = sameGenerationFixture();
  let failNetwork = false;
  let calls = 0;
  const fetchImpl = async input => {
    calls += 1;
    if (failNetwork) throw new Error('offline');
    return String(input).includes('manifest')
      ? new Response(JSON.stringify(manifest))
      : new Response(index);
  };
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://x/manifest.json',
    fetchImpl,
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    staleMs: 60_000,
  });

  await client.initialize();
  client.active = Object.freeze({ ...client.snapshot(), activatedAt: 0 });
  client.lastNetworkRefreshAt = 0;
  failNetwork = true;
  await client.initialize();
  assert.equal(calls, 3);
  assert.equal(client.lastNetworkRefreshAt, 0);

  failNetwork = false;
  await client.initialize();
  assert.equal(calls, 5);
});
