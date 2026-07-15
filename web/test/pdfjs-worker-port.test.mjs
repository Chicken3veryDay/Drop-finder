import test from 'node:test';
import assert from 'node:assert/strict';
import { disposePdfJsRuntimeWorker, loadPdfJsRuntime } from '../src/platform/documents/pdfjs-loader.js';

test('PDF.js uses one explicit dedicated worker port and releases it', async () => {
  const originalWindow = globalThis.window;
  const originalWorker = globalThis.Worker;
  const instances = [];

  class FakeWorker {
    constructor(source, options) {
      this.source = source;
      this.options = options;
      this.listeners = new Map();
      this.terminated = false;
      instances.push(this);
    }
    addEventListener(name, listener) { this.listeners.set(name, listener); }
    terminate() { this.terminated = true; }
  }

  globalThis.window = {};
  globalThis.Worker = FakeWorker;
  try {
    const first = await loadPdfJsRuntime({ workerSrc: '/pdf.worker.mjs' });
    const second = await loadPdfJsRuntime({ workerSrc: '/pdf.worker.mjs' });
    assert.equal(instances.length, 1);
    assert.equal(instances[0].options.type, 'module');
    assert.equal(instances[0].options.name, 'dropfinder-pdfjs');
    assert.equal(first.GlobalWorkerOptions.workerPort, instances[0]);
    assert.equal(second.GlobalWorkerOptions.workerPort, instances[0]);

    disposePdfJsRuntimeWorker();
    assert.equal(instances[0].terminated, true);
    assert.equal(first.GlobalWorkerOptions.workerPort, null);
  } finally {
    disposePdfJsRuntimeWorker();
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
  }
});
