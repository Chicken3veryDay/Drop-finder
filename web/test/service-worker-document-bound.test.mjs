import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

function extractFunction(source, signature, nextSignature) {
  const start = source.indexOf(signature);
  const end = source.indexOf(nextSignature, start);
  assert.notEqual(start, -1, `${signature} must exist`);
  assert.notEqual(end, -1, `${nextSignature} must follow ${signature}`);
  return source.slice(start, end).trim();
}

async function serviceWorkerSource() {
  return readFile(new URL('../../cloud_pages/sw.js', import.meta.url), 'utf8');
}

test('opened-document cache uses bounded streaming instead of full-body buffering', async () => {
  const source = await serviceWorkerSource();
  const cacheFunction = extractFunction(
    source,
    'async function cacheOpenedDocument',
    'async function safeCachePut',
  );
  assert.match(cacheFunction, /readBoundedCacheResponse/);
  assert.doesNotMatch(cacheFunction, /arrayBuffer\s*\(/);
});

test('service-worker bounded document reader cancels headerless overflow', async () => {
  const source = await serviceWorkerSource();
  const helperSource = extractFunction(
    source,
    'async function readBoundedCacheResponse',
    'async function cacheOpenedDocument',
  );
  const readBoundedCacheResponse = Function(`"use strict"; return (${helperSource});`)();
  let pulls = 0;
  let cancelled = false;
  const response = new Response(new ReadableStream({
    pull(controller) {
      pulls += 1;
      controller.enqueue(Uint8Array.from(pulls === 1 ? [1, 2, 3, 4] : [5, 6, 7, 8]));
    },
    cancel() { cancelled = true; },
  }));

  const bounded = await readBoundedCacheResponse(response, 5);
  assert.equal(bounded, null);
  assert.equal(cancelled, true);
  assert.equal(pulls, 2);
});

test('service-worker bounded document reader preserves valid bodies at the cap', async () => {
  const source = await serviceWorkerSource();
  const helperSource = extractFunction(
    source,
    'async function readBoundedCacheResponse',
    'async function cacheOpenedDocument',
  );
  const readBoundedCacheResponse = Function(`"use strict"; return (${helperSource});`)();
  const response = new Response(Uint8Array.from([1, 2, 3, 4, 5]));
  const bounded = await readBoundedCacheResponse(response, 5);
  assert.ok(bounded instanceof Response);
  assert.deepEqual([...new Uint8Array(await bounded.arrayBuffer())], [1, 2, 3, 4, 5]);
});
