import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('document viewer destroys a timed-out PDF loading task before open settles', async () => {
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
  assert.equal(destroyed, true);
  await viewer.close();
});

test('document viewer applies the startup deadline to lazy PDF runtime loading', async () => {
  let releaseLoader;
  let getDocumentCalls = 0;
  const loader = new Promise(resolve => { releaseLoader = resolve; });
  const viewer = new DocumentViewerCapability({
    workerStartupTimeoutMs: 5,
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
    loadPdfJs: () => loader,
  });

  await viewer.open({ url: 'https://example.test/sample.pdf', mimeType: 'application/pdf' });
  assert.equal(viewer.snapshot().status, 'error');
  assert.equal(viewer.snapshot().error.code, 'document_worker_timeout');

  releaseLoader({
    getDocument() {
      getDocumentCalls += 1;
      return { promise: Promise.resolve({ numPages: 1, destroy: async () => {} }) };
    },
  });
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(getDocumentCalls, 0);
  assert.equal(viewer.snapshot().status, 'error');
  await viewer.close();
});
