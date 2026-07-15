/** Lazy-loads pinned PDF.js and binds one explicit dedicated module worker. */
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
      const release = () => {
        if (sharedWorker !== worker) return;
        if (sharedRuntime?.GlobalWorkerOptions.workerPort === worker) {
          sharedRuntime.GlobalWorkerOptions.workerPort = null;
        }
        worker.terminate?.();
        sharedWorker = null;
        sharedWorkerIdentity = null;
      };
      worker.addEventListener('error', release, { once: true });
      worker.addEventListener('messageerror', release, { once: true });
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

export function disposePdfJsRuntimeWorker() {
  if (sharedRuntime?.GlobalWorkerOptions.workerPort === sharedWorker) {
    sharedRuntime.GlobalWorkerOptions.workerPort = null;
  }
  sharedWorker?.terminate?.();
  sharedWorker = null;
  sharedWorkerIdentity = null;
  sharedRuntime = null;
}
