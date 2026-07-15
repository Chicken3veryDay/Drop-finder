import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('document viewer fails concisely when the dedicated PDF worker misses its bounded startup window', async () => {
  let destroyed = false;
  const viewer = new DocumentViewerCapability({
    workerStartupTimeoutMs: 5,
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
    loadPdfJs: async () => ({
      getDocument() {
        return {
          promise: new Promise(() => {}),
          async destroy() { destroyed = true; },
        };
      },
    }),
  });

  await viewer.open({ url: 'https://example.test/sample.pdf', mimeType: 'application/pdf' });
  assert.equal(viewer.snapshot().status, 'error');
  assert.equal(viewer.snapshot().error.code, 'document_worker_timeout');
  assert.equal(viewer.snapshot().error.action, 'open-original');
  await viewer.close();
  assert.equal(destroyed, true);
});
