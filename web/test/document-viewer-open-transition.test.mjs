import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

test('document open does not publish a terminal closed state during replacement cleanup', async () => {
  const viewer = new DocumentViewerCapability();
  const statuses = [];
  viewer.subscribe(state => statuses.push(state.status));

  await viewer.open({ url: './unknown.bin', mimeType: 'application/octet-stream' });
  assert.deepEqual(statuses, ['loading', 'unsupported']);

  statuses.length = 0;
  await viewer.open({ url: './next.bin', mimeType: 'application/octet-stream' });
  assert.deepEqual(statuses, ['loading', 'unsupported']);

  await viewer.close();
  assert.equal(viewer.snapshot().status, 'closed');
});
