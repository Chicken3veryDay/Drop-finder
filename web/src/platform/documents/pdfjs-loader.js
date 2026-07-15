/** Lazy-loads PDF.js and binds one explicit dedicated module worker. */
let sharedWorker = null;
let sharedWorkerIdentity = null;
let sharedRuntime = null;

export async function loadPdfJsRuntime(options = {}) {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  if (typeof window !== 'undefined' && typeof Worker !== 'undefined') {
    const identity = options.workerSrc ?? 'vite:pdfjs-legacy-worker';
    if (!sharedWorker || sharedWorkerIdentity !== identity) {
      disposePdfJsRuntimeWorker();
      const worker = options.workerSrc
        ? new Worker(options.workerSrc, { type: 'module', name: 'dropfinder-pdfjs' })
        : await createBundledWorker();
      sharedWorker = worker;
      sharedWorkerIdentity = identity;
      sharedRuntime = pdfjs;
      worker.addEventListener('error', () => {
        if (sharedWorker !== worker) return;
        if (sharedRuntime?.GlobalWorkerOptions.workerPort === worker) {
          sharedRuntime.GlobalWorkerOptions.workerPort = null;
        }
        sharedWorker = null;
        sharedWorkerIdentity = null;
      }, { once: true });
    }
    pdfjs.GlobalWorkerOptions.workerPort = sharedWorker;
  }
  return pdfjs;
}

async function createBundledWorker() {
  const workerModule = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker');
  const PdfJsWorker = workerModule.default;
  return new PdfJsWorker({ name: 'dropfinder-pdfjs' });
}

/**
 * Creates PDF.js's compatibility worker on the main thread through a
 * MessageChannel. This is used only after a real worker fails its bounded
 * startup window, matching PDF.js's own fake-worker architecture.
 */
export async function createPdfJsCompatibilityWorker(pdfjs) {
  if (typeof MessageChannel === 'undefined') {
    throw new Error('MessageChannel is unavailable');
  }
  const workerModule = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs');
  const channel = new MessageChannel();
  workerModule.WorkerMessageHandler.initializeFromPort(channel.port1);
  const worker = new pdfjs.PDFWorker({
    name: 'dropfinder-pdfjs-compatibility',
    port: channel.port2,
  });
  await worker.promise;
  return {
    worker,
    destroy() {
      worker.destroy();
      channel.port1.close?.();
      channel.port2.close?.();
    },
  };
}

export function disposePdfJsRuntimeWorker() {
  if (sharedRuntime?.GlobalWorkerOptions.workerPort === sharedWorker) {
    sharedRuntime.GlobalWorkerOptions.workerPort = null;
  }
  sharedWorker?.terminate?.();
  sharedWorker = null;
  sharedWorkerIdentity = null;
  sharedRuntime = null;
}
