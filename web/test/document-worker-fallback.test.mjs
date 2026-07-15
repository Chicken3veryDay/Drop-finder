import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('document viewer retries through compatibility worker after bounded startup timeout', async () => {
  let calls = 0;
  let compatibilityDestroyed = false;
  const pdf = {
    numPages: 2,
    cleanup: async () => {},
    destroy: async () => {},
    getPage: async () => ({}),
  };
  const pdfjs = {
    getDocument(options) {
      calls += 1;
      if (calls === 1) {
        return { promise: new Promise(() => {}), destroy: async () => {} };
      }
      assert.equal(options.worker, compatibility.worker);
      return { promise: Promise.resolve(pdf), destroy: async () => {} };
    },
  };
  const compatibility = {
    worker: { name: 'compatibility-worker' },
    destroy() { compatibilityDestroyed = true; },
  };
  const viewer = new DocumentViewerCapability({
    workerStartupTimeoutMs: 5,
    compatibilityStartupTimeoutMs: 100,
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
    loadPdfJs: async () => pdfjs,
    createCompatibilityWorker: async value => {
      assert.equal(value, pdfjs);
      return compatibility;
    },
  });

  await viewer.open({ url: 'https://example.test/sample.pdf', mimeType: 'application/pdf' });
  assert.equal(calls, 2);
  assert.equal(viewer.snapshot().status, 'ready');
  assert.equal(viewer.snapshot().pages, 2);
  await viewer.close();
  assert.equal(compatibilityDestroyed, true);
});
