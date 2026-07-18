import assert from 'node:assert/strict';
import test from 'node:test';

import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('unsupported document dispatch avoids network and PDF runtime work', async () => {
  let fetchCalls = 0;
  let pdfRuntimeCalls = 0;
  const documentRef = {
    url: 'https://documents.example.test/report.txt',
    mimeType: 'text/plain',
  };
  const viewer = new DocumentViewerCapability({
    fetchImpl: async () => {
      fetchCalls += 1;
      throw new Error('unsupported documents must not be fetched');
    },
    loadPdfJs: async () => {
      pdfRuntimeCalls += 1;
      throw new Error('unsupported documents must not load PDF.js');
    },
  });

  const opened = await viewer.open(documentRef, { productId: 'product-1' });

  assert.equal(opened.status, 'unsupported');
  assert.equal(opened.type, 'unsupported');
  assert.equal(opened.documentRef, documentRef);
  assert.equal(fetchCalls, 0);
  assert.equal(pdfRuntimeCalls, 0);

  await viewer.close({ restoreFocus: false });

  assert.equal(viewer.snapshot().status, 'closed');
  assert.equal(viewer.snapshot().type, null);
  assert.equal(viewer.snapshot().documentRef, null);
  assert.equal(viewer.session, null);
});
