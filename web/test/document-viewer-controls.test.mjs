import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentViewerCapability } from '../src/platform/documents/document-viewer-capability.js';

// Manual zoom is owned by the rendered PDF scale, not the stale configured scale.
function readyViewer(parentWidth) {
  const viewer = new DocumentViewerCapability({ minScale: 0.5, maxScale: 3, initialScale: 1 });
  const pdfPage = {
    getViewport: ({ scale }) => ({ width: 400 * scale, height: 600 * scale }),
    render: () => ({ promise: Promise.resolve(), cancel() {} }),
    cleanup() {},
  };
  const session = {
    id: 'session',
    controller: new AbortController(),
    loadingTask: null,
    pdf: { getPage: async () => pdfPage },
    renderTask: null,
    renderRevision: 0,
    renderSequence: Promise.resolve(),
    objectUrl: null,
  };
  viewer.session = session;
  viewer.setState({
    status: 'ready', type: 'pdf', documentRef: { url: 'https://example.test/report.pdf' }, context: {},
    page: 1, pages: 1, scale: 1, renderedScale: 1, fitWidth: true,
    displayUrl: null, error: null, sessionId: session.id,
  });
  const canvas = {
    parentElement: { clientWidth: parentWidth },
    style: {},
    getContext: () => ({}),
  };
  return { viewer, canvas };
}

test('manual zoom starts from the rendered fit-width scale', async () => {
  const wide = readyViewer(1000);
  const wideRender = await wide.viewer.renderPage(wide.canvas);
  assert.equal(wideRender.scale, 2.5);
  assert.equal(wide.viewer.snapshot().renderedScale, 2.5);
  wide.viewer.zoomIn();
  assert.equal(wide.viewer.snapshot().scale, 2.75);
  assert.equal(wide.viewer.snapshot().fitWidth, false);

  const narrow = readyViewer(200);
  const narrowRender = await narrow.viewer.renderPage(narrow.canvas);
  assert.equal(narrowRender.scale, 0.5);
  narrow.viewer.zoomOut();
  assert.equal(narrow.viewer.snapshot().scale, 0.5);
  assert.equal(narrow.viewer.snapshot().fitWidth, false);
});

test('reset zoom restores the configured manual scale', async () => {
  const { viewer, canvas } = readyViewer(800);
  await viewer.renderPage(canvas);
  viewer.zoomIn();
  assert.notEqual(viewer.snapshot().scale, 1);
  viewer.resetZoom();
  assert.equal(viewer.snapshot().scale, 1);
  assert.equal(viewer.snapshot().renderedScale, 1);
  assert.equal(viewer.snapshot().fitWidth, false);
});
