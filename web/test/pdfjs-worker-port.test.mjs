import test from 'node:test';
import assert from 'node:assert/strict';
import { disposePdfJsRuntimeWorker, loadPdfJsRuntime } from '../src/platform/documents/pdfjs-loader.js';

test('PDF.js uses one explicit worker source and owns each loading-task worker lifecycle', async () => {
  const originalWindow = globalThis.window;
  const originalWorker = globalThis.Worker;
  let manuallyConstructedWorkers = 0;

  class UnexpectedWorker {
    constructor() { manuallyConstructedWorkers += 1; }
  }

  globalThis.window = {};
  globalThis.Worker = UnexpectedWorker;
  try {
    const first = await loadPdfJsRuntime({ workerSrc: '/pdf.worker.mjs' });
    const second = await loadPdfJsRuntime({ workerSrc: '/pdf.worker.mjs' });
    assert.equal(manuallyConstructedWorkers, 0);
    assert.equal(first.GlobalWorkerOptions.workerPort, null);
    assert.equal(second.GlobalWorkerOptions.workerPort, null);
    assert.equal(first.GlobalWorkerOptions.workerSrc, '/pdf.worker.mjs');
    assert.equal(second.GlobalWorkerOptions.workerSrc, '/pdf.worker.mjs');

    disposePdfJsRuntimeWorker();
    assert.equal(first.GlobalWorkerOptions.workerSrc, '');
  } finally {
    disposePdfJsRuntimeWorker();
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
  }
});
