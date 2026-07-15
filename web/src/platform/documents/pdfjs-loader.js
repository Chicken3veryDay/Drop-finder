/** Lazy-loads the cross-browser PDF.js runtime and its dedicated worker. */
export async function loadPdfJsRuntime(options = {}) {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs');
  if (typeof window !== 'undefined') {
    let workerSrc = options.workerSrc;
    if (!workerSrc) {
      const workerModule = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url');
      workerSrc = workerModule.default;
    }
    pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
  }
  return pdfjs;
}
