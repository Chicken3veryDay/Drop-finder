import test from 'node:test';
import assert from 'node:assert/strict';
import { CatalogGenerationClient } from '../src/platform/catalog/catalog-generation-client.js';

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function deferredFetch() {
  const calls = [];
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {
    calls,
    resolve,
    fetchImpl(input, init) {
      calls.push({ input, init });
      return promise;
    },
  };
}

function fetchDetail(client, signal) {
  return client.fetchDeduped('g1:detail', 'https://example.test/detail.json', {
    signal,
    maxBytes: 1024,
    cache: 'default',
  });
}

test('aborting one shared detail consumer keeps the transport alive for another', async () => {
  const transport = deferredFetch();
  const client = new CatalogGenerationClient({ fetchImpl: transport.fetchImpl, maxRetries: 0 });
  const first = new AbortController();
  const second = new AbortController();

  const firstResult = fetchDetail(client, first.signal);
  const secondResult = fetchDetail(client, second.signal);
  await tick();
  assert.equal(transport.calls.length, 1);
  const sharedSignal = transport.calls[0].init.signal;

  first.abort('first consumer closed');
  await assert.rejects(firstResult, (error) => error?.name === 'AbortError');
  assert.equal(sharedSignal.aborted, false);

  transport.resolve(new Response('{"ok":true}', { headers: { 'content-length': '11' } }));
  assert.deepEqual(await (await secondResult).json(), { ok: true });
  assert.equal(client.inflight.size, 0);
});

test('aborting the final shared detail consumer aborts the transport', async () => {
  const transport = deferredFetch();
  const client = new CatalogGenerationClient({ fetchImpl: transport.fetchImpl, maxRetries: 0 });
  const first = new AbortController();
  const second = new AbortController();

  const firstResult = fetchDetail(client, first.signal);
  const secondResult = fetchDetail(client, second.signal);
  await tick();
  const sharedSignal = transport.calls[0].init.signal;

  first.abort();
  await assert.rejects(firstResult, (error) => error?.name === 'AbortError');
  assert.equal(sharedSignal.aborted, false);
  second.abort();
  await assert.rejects(secondResult, (error) => error?.name === 'AbortError');
  assert.equal(sharedSignal.aborted, true);

  transport.resolve(new Response('{}'));
  await tick();
  assert.equal(client.inflight.size, 0);
});

test('a pre-aborted caller does not join or cancel an active shared request', async () => {
  const transport = deferredFetch();
  const client = new CatalogGenerationClient({ fetchImpl: transport.fetchImpl, maxRetries: 0 });
  const active = new AbortController();
  const alreadyAborted = new AbortController();
  alreadyAborted.abort();

  const activeResult = fetchDetail(client, active.signal);
  await tick();
  const sharedSignal = transport.calls[0].init.signal;
  await assert.rejects(fetchDetail(client, alreadyAborted.signal), (error) => error?.name === 'AbortError');
  assert.equal(transport.calls.length, 1);
  assert.equal(sharedSignal.aborted, false);

  transport.resolve(new Response('{"ok":true}'));
  assert.deepEqual(await (await activeResult).json(), { ok: true });
});

test('a new caller replaces an all-cancelled shared detail request', async () => {
  const firstTransport = deferredFetch();
  const secondTransport = deferredFetch();
  let fetchCount = 0;
  const client = new CatalogGenerationClient({
    maxRetries: 0,
    fetchImpl(input, init) {
      fetchCount += 1;
      return fetchCount === 1
        ? firstTransport.fetchImpl(input, init)
        : secondTransport.fetchImpl(input, init);
    },
  });
  const cancelled = new AbortController();
  const cancelledResult = fetchDetail(client, cancelled.signal);
  await tick();
  cancelled.abort();
  await assert.rejects(cancelledResult, (error) => error?.name === 'AbortError');
  assert.equal(firstTransport.calls[0].init.signal.aborted, true);

  const replacementResult = fetchDetail(client);
  await tick();
  assert.equal(fetchCount, 2);
  secondTransport.resolve(new Response('{"replacement":true}'));
  assert.deepEqual(await (await replacementResult).json(), { replacement: true });

  firstTransport.resolve(new Response('{"stale":true}'));
  await tick();
  assert.equal(client.inflight.size, 0);
});

test('generation activation aborts all consumers of the obsolete shared request', async () => {
  const transport = deferredFetch();
  const client = new CatalogGenerationClient({ fetchImpl: transport.fetchImpl, maxRetries: 0 });
  const firstResult = fetchDetail(client);
  const secondResult = fetchDetail(client);
  await tick();

  client.cancelObsolete('generation changed');
  assert.equal(transport.calls[0].init.signal.aborted, true);
  transport.resolve(new Response('{}'));
  await assert.rejects(firstResult, (error) => error?.name === 'AbortError');
  await assert.rejects(secondResult, (error) => error?.name === 'AbortError');
  assert.equal(client.inflight.size, 0);
});
