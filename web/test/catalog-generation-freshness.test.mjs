import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  CatalogGenerationClient,
  MemoryGenerationCache,
} from '../src/platform/catalog/catalog-generation-client.js';

const sha256 = (text) => createHash('sha256').update(text).digest('hex');

function generationFixture(generationId = 'g1') {
  const index = JSON.stringify({ generation_id: generationId, products: [] });
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
  return { index, manifest };
}

function generationFetch(fixture, calls, shouldFail = () => false) {
  return async (input) => {
    const url = String(input);
    calls.push(url);
    if (shouldFail()) throw new TypeError('synthetic network failure');
    if (url.endsWith('manifest.json')) {
      const body = JSON.stringify(fixture.manifest);
      return new Response(body, { headers: { 'content-length': String(body.length) } });
    }
    if (url.endsWith('index.json')) {
      return new Response(fixture.index, {
        headers: { 'content-length': String(fixture.index.length) },
      });
    }
    return new Response('', { status: 404 });
  };
}

function makeNetworkFreshnessStale(client) {
  const staleAt = Date.now() - 1_000;
  client.active = Object.freeze({ ...client.snapshot(), activatedAt: staleAt });
  client.lastNetworkVerification = Object.freeze({
    generationId: client.active.generationId,
    verifiedAt: staleAt,
  });
  return staleAt;
}

test('same-generation verification refreshes freshness without reactivation', async () => {
  const fixture = generationFixture();
  const calls = [];
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://example.test/manifest.json',
    fetchImpl: generationFetch(fixture, calls),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    staleMs: 100,
  });
  const events = [];
  client.subscribe((event) => events.push(event));

  await client.initialize();
  const staleAt = makeNetworkFreshnessStale(client);
  const active = client.snapshot();
  assert.equal(calls.length, 2);
  assert.equal(events.length, 1);
  assert.equal(active.activatedAt, staleAt);

  let aborts = 0;
  client.detailLru.set('g1:sentinel', { retained: true });
  client.inflight.set('sentinel', {
    controller: { abort: () => { aborts += 1; } },
    promise: Promise.resolve(),
  });

  const [first, second] = await Promise.all([client.initialize(), client.initialize()]);
  assert.equal(first.generationId, 'g1');
  assert.equal(second.generationId, 'g1');
  assert.equal(calls.length, 4);
  assert.strictEqual(client.snapshot(), active);
  assert.equal(client.snapshot().activatedAt, staleAt);
  assert.equal(events.length, 1);
  assert.equal(aborts, 0);
  assert.equal(client.detailLru.has('g1:sentinel'), true);
  assert.equal(client.inflight.has('sentinel'), true);
  assert.ok(client.lastNetworkVerification.verifiedAt > staleAt);

  const verifiedAt = client.lastNetworkVerification.verifiedAt;
  await client.initialize();
  assert.equal(calls.length, 4);
  assert.equal(client.lastNetworkVerification.verifiedAt, verifiedAt);

  await client.initialize({ force: true });
  assert.equal(calls.length, 6);
  assert.strictEqual(client.snapshot(), active);
  assert.equal(events.length, 1);
  assert.equal(aborts, 0);
});

test('cached fallback does not advance successful-network freshness', async () => {
  const fixture = generationFixture();
  const calls = [];
  let failNetwork = false;
  const client = new CatalogGenerationClient({
    manifestUrl: 'https://example.test/manifest.json',
    fetchImpl: generationFetch(fixture, calls, () => failNetwork),
    cache: new MemoryGenerationCache(),
    maxRetries: 0,
    staleMs: 100,
  });
  const events = [];
  client.subscribe((event) => events.push(event));

  await client.initialize();
  const staleAt = makeNetworkFreshnessStale(client);
  const active = client.snapshot();
  assert.equal(calls.length, 2);
  assert.equal(events.length, 1);

  failNetwork = true;
  const fallback = await client.initialize();
  assert.equal(fallback.generationId, 'g1');
  assert.equal(calls.length, 3);
  assert.strictEqual(client.snapshot(), active);
  assert.equal(events.length, 1);
  assert.equal(client.lastNetworkVerification.verifiedAt, staleAt);

  await client.initialize();
  assert.equal(calls.length, 4);
  assert.strictEqual(client.snapshot(), active);
  assert.equal(events.length, 1);
  assert.equal(client.lastNetworkVerification.verifiedAt, staleAt);
});
