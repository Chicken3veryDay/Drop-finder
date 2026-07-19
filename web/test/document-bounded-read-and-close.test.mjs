import assert from 'node:assert/strict';
import test from 'node:test';

import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';
import { readBoundedBytes } from '../src/platform/network/read-bounded-bytes.js';

function chunkedResponse(chunks, headers = {}) {
  let index = 0;
  let cancelled = false;
  const response = new Response(new ReadableStream({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(Uint8Array.from(chunks[index++]));
    },
    cancel() { cancelled = true; },
  }), { headers });
  return { response, pulls: () => index, cancelled: () => cancelled };
}

test('bounded reader cancels a headerless stream as soon as the next chunk exceeds the cap', async () => {
  const stream = chunkedResponse([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]);
  await assert.rejects(
    readBoundedBytes(stream.response, { maxBytes: 5 }),
    error => error instanceof RangeError,
  );
  assert.equal(stream.cancelled(), true);
  assert.equal(stream.pulls(), 2);
});

test('bounded reader rejects an honest oversized declaration before body acquisition', async () => {
  let cancelled = false;
  const response = {
    headers: new Headers({ 'content-length': '6' }),
    body: { cancel: async () => { cancelled = true; } },
  };
  await assert.rejects(
    readBoundedBytes(response, { maxBytes: 5 }),
    error => error instanceof RangeError,
  );
  assert.equal(cancelled, true);
});

test('bounded reader accepts bodies exactly at the configured cap', async () => {
  const stream = chunkedResponse([[1, 2], [3, 4, 5]]);
  const bytes = await readBoundedBytes(stream.response, { maxBytes: 5 });
  assert.deepEqual([...bytes], [1, 2, 3, 4, 5]);
  assert.equal(stream.cancelled(), false);
});

test('PDF and image viewers share bounded streaming rejection semantics', async () => {
  for (const documentRef of [
    { url: 'https://example.test/report.pdf', mimeType: 'application/pdf' },
    { url: 'https://example.test/report.png', mimeType: 'image/png' },
  ]) {
    const stream = chunkedResponse([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]);
    let runtimeCalled = false;
    let decodeCalled = false;
    const viewer = new DocumentViewerCapability({
      maxBytes: 5,
      fetchImpl: async () => stream.response,
      loadPdfJs: async () => { runtimeCalled = true; throw new Error('should not load'); },
      decodeImage: async () => { decodeCalled = true; },
    });

    await viewer.open(documentRef);
    assert.equal(viewer.snapshot().status, 'error');
    assert.equal(viewer.snapshot().error.code, 'document_oversized');
    assert.equal(stream.pulls(), 2);
    assert.equal(runtimeCalled, false);
    assert.equal(decodeCalled, false);
    await viewer.close();
  }
});

test('closing settles even when PDF page acquisition is stalled', async () => {
  let releasePage;
  let markPageStarted;
  let loadingDestroyCalls = 0;
  let pdfDestroyCalls = 0;
  let pdfCleanupCalls = 0;
  const pageStarted = new Promise(resolve => { markPageStarted = resolve; });
  const pendingPage = new Promise(resolve => { releasePage = resolve; });
  const pdf = {
    numPages: 1,
    getPage() {
      markPageStarted();
      return pendingPage;
    },
    async destroy() { pdfDestroyCalls += 1; },
    async cleanup() { pdfCleanupCalls += 1; },
  };
  const loadingTask = {
    promise: Promise.resolve(pdf),
    async destroy() { loadingDestroyCalls += 1; },
  };
  const viewer = new DocumentViewerCapability({
    cleanupTimeoutMs: 20,
    fetchImpl: async () => new Response(Uint8Array.from([1, 2, 3])),
    loadPdfJs: async () => ({ getDocument: () => loadingTask }),
  });
  const canvas = {
    parentElement: { clientWidth: 400 },
    style: {},
    getContext: () => ({}),
  };

  await viewer.open({ url: 'https://example.test/stalled.pdf', mimeType: 'application/pdf' });
  const render = viewer.renderPage(canvas);
  await pageStarted;
  const outcome = await Promise.race([
    viewer.close().then(() => 'closed'),
    new Promise(resolve => setTimeout(() => resolve('timed-out'), 200)),
  ]);

  assert.equal(outcome, 'closed');
  assert.equal(viewer.snapshot().status, 'closed');
  assert.equal(loadingDestroyCalls, 1);
  assert.equal(pdfDestroyCalls, 1);
  assert.equal(pdfCleanupCalls, 1);

  releasePage({ cleanup() {}, getViewport: () => ({ width: 1, height: 1 }) });
  await assert.rejects(render, error => error.name === 'AbortError');
  await viewer.close();
});
