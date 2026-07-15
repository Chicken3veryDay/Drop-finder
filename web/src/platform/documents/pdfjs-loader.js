/** Lazy-loads PDF.js and configures its dedicated browser worker on first use. */
export async function loadPdfJsRuntime(options = {}) {
  const pdfjs = typeof window === 'undefined'
    ? await import('pdfjs-dist/legacy/build/pdf.mjs')
    : await import('pdfjs-dist/build/pdf.mjs');
  if (typeof window !== 'undefined') {
    let workerSrc = options.workerSrc;
    if (!workerSrc) {
      const workerModule = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
      workerSrc = workerModule.default;
    }
    pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
  }
  return pdfjs;
}
