/** Lazy-loads pinned PDF.js and configures its separately emitted module worker. */
let sharedWorkerSource = null;
let sharedRuntime = null;

export async function loadPdfJsRuntime(options = {}) {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  if (typeof window !== 'undefined') {
    const workerSource = options.workerSrc ?? await loadBundledWorkerSource();
    if (typeof workerSource !== 'string' || workerSource.length === 0) {
      throw new TypeError('PDF.js worker source must be a non-empty string');
    }
    clearConfiguredWorkerSource();
    pdfjs.GlobalWorkerOptions.workerPort = null;
    pdfjs.GlobalWorkerOptions.workerSrc = workerSource;
    sharedWorkerSource = workerSource;
    sharedRuntime = pdfjs;
  }
  return pdfjs;
}

async function loadBundledWorkerSource() {
  const workerModule = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url');
  return workerModule.default;
}

function clearConfiguredWorkerSource() {
  if (!sharedRuntime) return;
  if (sharedRuntime.GlobalWorkerOptions.workerPort) {
    sharedRuntime.GlobalWorkerOptions.workerPort = null;
  }
  if (sharedRuntime.GlobalWorkerOptions.workerSrc === sharedWorkerSource) {
    sharedRuntime.GlobalWorkerOptions.workerSrc = '';
  }
}

/** Compatibility export: PDF.js owns and destroys workers through each loading task. */
export function disposePdfJsRuntimeWorker() {
  clearConfiguredWorkerSource();
  sharedWorkerSource = null;
  sharedRuntime = null;
}
