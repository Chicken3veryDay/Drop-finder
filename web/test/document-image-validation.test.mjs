import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

async function trackObjectUrlRevocations(run) {
  const original = URL.revokeObjectURL;
  const revoked = [];
  URL.revokeObjectURL = url => {
    revoked.push(url);
    original.call(URL, url);
  };
  try { await run(revoked); }
  finally { URL.revokeObjectURL = original; }
}

test('image-classified HTML responses fail before publishing a ready preview', async () => {
  await trackObjectUrlRevocations(async revoked => {
    const viewer = new DocumentViewerCapability({
      fetchImpl: async () => new Response('<html>challenge</html>', {
        headers: { 'content-type': 'text/html', 'content-length': '22' },
      }),
      decodeImage: async () => { throw new Error('not an image'); },
    });
    await viewer.open({ url: 'https://example.test/coa.png', mimeType: 'image/png' });
    assert.equal(viewer.snapshot().status, 'error');
    assert.equal(viewer.snapshot().displayUrl, null);
    assert.equal(viewer.snapshot().error.code, 'image_decode_failed');
    assert.equal(viewer.snapshot().error.action, 'open-original');
    assert.equal(revoked.length, 1);
    await viewer.close();
    assert.equal(revoked.length, 1);
  });
});

test('corrupt bytes labeled as an image fail through the same decode gate', async () => {
  await trackObjectUrlRevocations(async revoked => {
    let decodeCalls = 0;
    const viewer = new DocumentViewerCapability({
      fetchImpl: async () => new Response(new Uint8Array([0, 1, 2, 3]), {
        headers: { 'content-type': 'image/png', 'content-length': '4' },
      }),
      decodeImage: async () => { decodeCalls += 1; throw new Error('corrupt image'); },
    });
    await viewer.open({ url: 'https://example.test/corrupt.png', mimeType: 'image/png' });
    assert.equal(decodeCalls, 1);
    assert.equal(viewer.snapshot().status, 'error');
    assert.equal(viewer.snapshot().error.message, 'This image could not be displayed.');
    assert.equal(revoked.length, 1);
  });
});

test('a successfully decoded image remains ready until close releases its object URL', async () => {
  await trackObjectUrlRevocations(async revoked => {
    let decodedUrl = null;
    const viewer = new DocumentViewerCapability({
      fetchImpl: async () => new Response(new Uint8Array([137, 80, 78, 71]), {
        headers: { 'content-type': 'image/png', 'content-length': '4' },
      }),
      decodeImage: async url => { decodedUrl = url; },
    });
    await viewer.open({ url: 'https://example.test/valid.png', mimeType: 'image/png' });
    assert.equal(viewer.snapshot().status, 'ready');
    assert.equal(viewer.snapshot().displayUrl, decodedUrl);
    assert.match(decodedUrl, /^blob:/);
    assert.equal(revoked.length, 0);
    await viewer.close();
    assert.deepEqual(revoked, [decodedUrl]);
    assert.equal(viewer.snapshot().status, 'closed');
  });
});

test('closing while image decoding is pending aborts validation and releases the object URL', async () => {
  await trackObjectUrlRevocations(async revoked => {
    let decodingStarted;
    const started = new Promise(resolve => { decodingStarted = resolve; });
    const viewer = new DocumentViewerCapability({
      fetchImpl: async () => new Response(new Uint8Array([71, 73, 70, 56]), {
        headers: { 'content-type': 'image/gif', 'content-length': '4' },
      }),
      decodeImage: (_url, signal) => new Promise((_resolve, reject) => {
        decodingStarted();
        signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
      }),
    });
    const opening = viewer.open({ url: 'https://example.test/pending.gif', mimeType: 'image/gif' });
    await started;
    await viewer.close();
    await opening;
    assert.equal(viewer.snapshot().status, 'closed');
    assert.equal(revoked.length, 1);
  });
});

test('direct image URLs use the same decode gate when transport is unavailable', async () => {
  let decoded = null;
  const viewer = new DocumentViewerCapability({
    decodeImage: async url => { decoded = url; },
  });
  viewer.fetchImpl = null;
  await viewer.open({ url: 'https://example.test/direct.webp', mimeType: 'image/webp' });
  assert.equal(decoded, 'https://example.test/direct.webp');
  assert.equal(viewer.snapshot().status, 'ready');
  assert.equal(viewer.snapshot().displayUrl, decoded);
});
