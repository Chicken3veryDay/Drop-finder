/** Lazy-loads PDF.js and binds one explicit dedicated module worker. */
let sharedWorker = null;
let sharedWorkerSource = null;
let sharedRuntime = null;

export async function loadPdfJsRuntime(options = {}) {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  if (typeof window !== 'undefined' && typeof Worker !== 'undefined') {
    let workerSrc = options.workerSrc;
    if (!workerSrc) {
      const workerModule = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url');
      workerSrc = workerModule.default;
    }
    pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
    if (!sharedWorker || sharedWorkerSource !== workerSrc) {
      disposePdfJsRuntimeWorker();
      sharedWorker = new Worker(workerSrc, { type: 'module', name: 'dropfinder-pdfjs' });
      sharedWorkerSource = workerSrc;
      sharedRuntime = pdfjs;
      sharedWorker.addEventListener('error', () => {
        if (sharedRuntime?.GlobalWorkerOptions.workerPort === sharedWorker) {
          sharedRuntime.GlobalWorkerOptions.workerPort = null;
        }
        sharedWorker = null;
        sharedWorkerSource = null;
      }, { once: true });
    }
    pdfjs.GlobalWorkerOptions.workerPort = sharedWorker;
  }
  return pdfjs;
}

export function disposePdfJsRuntimeWorker() {
  if (sharedRuntime?.GlobalWorkerOptions.workerPort === sharedWorker) {
    sharedRuntime.GlobalWorkerOptions.workerPort = null;
  }
  sharedWorker?.terminate?.();
  sharedWorker = null;
  sharedWorkerSource = null;
  sharedRuntime = null;
}
