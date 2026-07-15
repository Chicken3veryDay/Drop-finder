import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('document viewer cancels stale canvas work and serializes the latest render', async () => {
  let rejectFirst;
  let firstCancelled = false;
  const cleanedPages = [];
  const pdf = {
    numPages: 2,
    async cleanup() {},
    async getPage(pageNumber) {
      return {
        getViewport({ scale }) { return { width: 400 * scale, height: 600 * scale }; },
        render() {
          if (pageNumber === 1) {
            return {
              promise: new Promise((_resolve, reject) => { rejectFirst = reject; }),
              cancel() {
                firstCancelled = true;
                const error = new Error('cancelled');
                error.name = 'RenderingCancelledException';
                rejectFirst(error);
              },
            };
          }
          return { promise: Promise.resolve(), cancel() {} };
        },
        cleanup() { cleanedPages.push(pageNumber); },
      };
    },
  };
  const viewer = new DocumentViewerCapability({
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
    loadPdfJs: async () => ({ getDocument: () => ({ promise: Promise.resolve(pdf), destroy: async () => {} }) }),
  });
  const canvas = {
    parentElement: { clientWidth: 400 },
    style: {},
    getContext: () => ({}),
  };

  await viewer.open({ url: 'https://example.test/sample.pdf', mimeType: 'application/pdf' });
  const first = viewer.renderPage(canvas, { page: 1, fitWidth: false, scale: 1 });
  await new Promise(resolve => setImmediate(resolve));
  const second = viewer.renderPage(canvas, { page: 2, fitWidth: false, scale: 1 });

  await assert.rejects(first, error => error.name === 'AbortError');
  const result = await second;
  assert.equal(result.page, 2);
  assert.equal(firstCancelled, true);
  assert.deepEqual(cleanedPages, [1, 2]);
  await viewer.close();
});
