import { PlatformError, abortError } from '../contracts.js';
import { loadPdfJsRuntime } from './pdfjs-loader.js';

const DEFAULTS = Object.freeze({
  maxBytes: 20 * 1024 * 1024,
  maxPages: 80,
  minScale: 0.5,
  maxScale: 3,
  initialScale: 1,
  maxRetainedCanvases: 2,
  workerStartupTimeoutMs: 15_000,
});

/** Headless, cancellable document capability consumed by issue #8's overlay. */
export class DocumentViewerCapability {
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch?.bind(globalThis);
    this.loadPdfJs = options.loadPdfJs ?? (() => loadPdfJsRuntime({ workerSrc: options.pdfWorkerUrl }));
    this.decodeImage = options.decodeImage ?? decodeImageUrl;
    this.state = closedState();
    this.listeners = new Set();
    this.session = null;
    this.lifecycleRevision = 0;
    this.cleanupSequence = Promise.resolve();
    this.invoker = null;
    this.scrollLock = null;
  }

  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  snapshot() { return this.state; }

  async open(documentRef, context = {}) {
    const lifecycleRevision = ++this.lifecycleRevision;
    await this.closeSession({ restoreFocus: false, lifecycleRevision, publishClosed: false });
    if (lifecycleRevision !== this.lifecycleRevision) return this.state;
    const type = classifyDocument(documentRef);
    this.invoker = context.invoker ?? globalThis.document?.activeElement ?? null;
    this.lockScroll();
    const controller = new AbortController();
    const sessionId = cryptoRandomId();
    this.session = {
      id: sessionId,
      controller,
      loadingTask: null,
      pdf: null,
      renderTask: null,
      renderRevision: 0,
      renderSequence: Promise.resolve(),
      objectUrl: null,
    };
    this.setState({
      status: 'loading', type, documentRef, context, page: 1, pages: null,
      scale: this.options.initialScale, fitWidth: true, displayUrl: null, error: null, sessionId,
    });
    try {
      if (type === 'pdf') await this.openPdf(documentRef, sessionId, controller.signal);
      else if (type === 'image') await this.openImage(documentRef, sessionId, controller.signal);
      else if (type === 'html') this.setState({ ...this.state, status: 'external-only' });
      else this.setState({ ...this.state, status: 'unsupported' });
    } catch (error) {
      if (controller.signal.aborted || sessionId !== this.session?.id) return this.state;
      this.setState({ ...this.state, status: 'error', error: conciseDocumentError(error) });
    }
    return this.state;
  }

  async openPdf(documentRef, sessionId, signal) {
    if (!this.fetchImpl) throw new PlatformError('fetch_unavailable', 'Document fetch is unavailable');
    const response = await this.fetchImpl(documentRef.url, { signal, credentials: 'omit', referrerPolicy: 'no-referrer' });
    if (!response.ok) throw new PlatformError('document_unavailable', `Document request failed with ${response.status}`);
    const length = Number(response.headers.get('content-length'));
    if (Number.isFinite(length) && length > this.options.maxBytes) throw new PlatformError('document_oversized', 'Document is too large');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > this.options.maxBytes) throw new PlatformError('document_oversized', 'Document is too large');
    const session = this.session;
    let loadingTask = null;
    let destroyPromise = null;
    let startupExpired = false;
    const destroyLoadingTask = () => {
      if (!loadingTask) return Promise.resolve();
      if (session?.loadingTask === loadingTask) session.loadingTask = null;
      if (!destroyPromise) {
        destroyPromise = Promise.resolve()
          .then(() => loadingTask.destroy?.())
          .catch(() => undefined);
      }
      return destroyPromise;
    };

    const startup = (async () => {
      const pdfjs = await this.loadPdfJs();
      if (startupExpired || signal.aborted || sessionId !== this.session?.id) throw abortError();

      loadingTask = pdfjs.getDocument({
        data: bytes,
        isEvalSupported: false,
        useWorkerFetch: false,
      });
      if (startupExpired || signal.aborted || sessionId !== this.session?.id) {
        await destroyLoadingTask();
        throw abortError();
      }
      session.loadingTask = loadingTask;
      return loadingTask.promise;
    })();

    let pdf;
    try {
      pdf = await settleWithin(
        startup,
        this.options.workerStartupTimeoutMs,
        signal,
        'document_worker_timeout',
        () => {
          startupExpired = true;
          void destroyLoadingTask();
        },
      );
    } catch (error) {
      if (error?.code === 'document_worker_timeout') {
        startupExpired = true;
        await destroyLoadingTask();
      }
      throw error;
    }

    if (signal.aborted || sessionId !== this.session?.id) {
      await pdf.destroy?.();
      return;
    }
    if (pdf.numPages > this.options.maxPages) {
      await pdf.destroy();
      throw new PlatformError('document_too_many_pages', 'Document has too many pages');
    }
    this.session.pdf = pdf;
    this.setState({ ...this.state, status: 'ready', pages: pdf.numPages, page: 1 });
  }

  async openImage(documentRef, sessionId, signal) {
    let objectUrl = null;
    try {
      const sourceUrl = documentRef.url;
      if (!this.fetchImpl) {
        await this.decodeImage(sourceUrl, signal);
        if (sessionId !== this.session?.id || signal.aborted) return;
        this.setState({ ...this.state, status: 'ready', displayUrl: sourceUrl });
        return;
      }
      const response = await this.fetchImpl(sourceUrl, {
        signal,
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
      });
      const length = Number(response.headers.get('content-length'));
      if (Number.isFinite(length) && length > this.options.maxBytes) {
        throw new PlatformError('document_oversized', 'Image is too large');
      }
      if (!response.ok) {
        throw new PlatformError('document_unavailable', `Image request failed with ${response.status}`);
      }
      const bytes = await response.arrayBuffer();
      if (bytes.byteLength > this.options.maxBytes) {
        throw new PlatformError('document_oversized', 'Image is too large');
      }
      if (sessionId !== this.session?.id || signal.aborted) return;
      const blob = new Blob([bytes], {
        type: response.headers.get('content-type') || documentRef.mimeType || 'application/octet-stream',
      });
      objectUrl = URL.createObjectURL(blob);
      await this.decodeImage(objectUrl, signal);
      if (sessionId !== this.session?.id || signal.aborted) return;
      this.session.objectUrl = objectUrl;
      this.setState({ ...this.state, status: 'ready', displayUrl: objectUrl });
      objectUrl = null;
    } catch (error) {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
      if (signal.aborted || error?.name === 'AbortError') throw abortError();
      if (error instanceof PlatformError) throw error;
      throw new PlatformError('image_decode_failed', 'This image could not be displayed.', error);
    } finally {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    }
  }

  renderPage(canvas, { page = this.state.page, fitWidth = this.state.fitWidth, scale = this.state.scale } = {}) {
    const session = this.session;
    if (!session?.pdf || this.state.status !== 'ready') {
      return Promise.reject(new PlatformError('document_not_ready', 'PDF is not ready'));
    }

    const request = {
      revision: ++session.renderRevision,
      page,
      fitWidth,
      scale,
    };
    try { session.renderTask?.cancel?.(); } catch {}

    const operation = session.renderSequence
      .catch(() => undefined)
      .then(() => this.performRenderPage(session, canvas, request));
    session.renderSequence = operation.catch(() => undefined);
    return operation;
  }

  async performRenderPage(session, canvas, request) {
    assertCurrentRender(this, session, request.revision);
    const pdfPage = await session.pdf.getPage(request.page);
    let renderTask = null;
    try {
      assertCurrentRender(this, session, request.revision);
      const base = pdfPage.getViewport({ scale: 1 });
      const effectiveScale = request.fitWidth && canvas.parentElement?.clientWidth
        ? Math.min(this.options.maxScale, Math.max(this.options.minScale, canvas.parentElement.clientWidth / base.width))
        : clamp(request.scale, this.options.minScale, this.options.maxScale);
      const viewport = pdfPage.getViewport({ scale: effectiveScale });
      const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      canvas.style.width = `${Math.ceil(viewport.width)}px`;
      canvas.style.height = `${Math.ceil(viewport.height)}px`;
      const context = canvas.getContext('2d', { alpha: false });
      if (!context) throw new PlatformError('canvas_unavailable', 'Canvas rendering is unavailable');
      renderTask = pdfPage.render({ canvasContext: context, viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] });
      session.renderTask = renderTask;
      await renderTask.promise;
      assertCurrentRender(this, session, request.revision);
      return { page: request.page, scale: effectiveScale, width: viewport.width, height: viewport.height };
    } catch (error) {
      if (isRenderCancellation(error) || this.session !== session || request.revision !== session.renderRevision) throw abortError();
      throw error;
    } finally {
      try { pdfPage.cleanup?.(); } catch {}
      if (session.renderTask === renderTask) session.renderTask = null;
    }
  }

  goToPage(page) {
    const pages = this.state.pages ?? 1;
    this.setState({ ...this.state, page: clamp(Math.trunc(page), 1, pages) });
  }
  zoomIn() { this.setZoom(this.state.scale + 0.25); }
  zoomOut() { this.setZoom(this.state.scale - 0.25); }
  resetZoom() { this.setState({ ...this.state, scale: this.options.initialScale, fitWidth: false }); }
  setFitWidth(enabled = true) { this.setState({ ...this.state, fitWidth: Boolean(enabled) }); }
  setZoom(scale) { this.setState({ ...this.state, scale: clamp(scale, this.options.minScale, this.options.maxScale), fitWidth: false }); }

  close({ restoreFocus = true } = {}) {
    const lifecycleRevision = ++this.lifecycleRevision;
    return this.closeSession({ restoreFocus, lifecycleRevision });
  }

  async closeSession({ restoreFocus, lifecycleRevision, publishClosed = true }) {
    const session = this.session;
    this.session = null;
    let cleanup = this.cleanupSequence;
    if (session) {
      session.controller.abort('Document viewer closed');
      session.renderRevision += 1;
      try { session.renderTask?.cancel?.(); } catch {}
      cleanup = this.cleanupSequence.then(async () => {
        try { await session.renderSequence; } catch {}
        try { await session.loadingTask?.destroy?.(); } catch {}
        try { await session.pdf?.cleanup?.(); } catch {}
        if (session.objectUrl) URL.revokeObjectURL(session.objectUrl);
      });
      this.cleanupSequence = cleanup.catch(() => undefined);
    }
    await cleanup;
    if (lifecycleRevision !== this.lifecycleRevision || !publishClosed) return;
    this.unlockScroll();
    this.setState(closedState());
    if (restoreFocus && this.invoker?.isConnected && typeof this.invoker.focus === 'function') this.invoker.focus({ preventScroll: true });
    this.invoker = null;
  }

  handleKeyDown(event, overlayRoot) {
    if (this.state.status === 'closed') return false;
    if (event.key === 'Escape') { event.preventDefault(); void this.close(); return true; }
    if (event.key !== 'Tab' || !overlayRoot) return false;
    const focusable = [...overlayRoot.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')]
      .filter(node => !node.hidden && node.getAttribute('aria-hidden') !== 'true');
    if (!focusable.length) { event.preventDefault(); overlayRoot.focus?.(); return true; }
    const first = focusable[0]; const last = focusable.at(-1);
    const activeIndex = focusable.indexOf(globalThis.document?.activeElement);
    if (event.shiftKey && activeIndex <= 0) { event.preventDefault(); last.focus(); return true; }
    if (!event.shiftKey && (activeIndex === -1 || activeIndex === focusable.length - 1)) { event.preventDefault(); first.focus(); return true; }
    return false;
  }

  lockScroll() {
    const body = globalThis.document?.body;
    if (!body || this.scrollLock) return;
    const width = globalThis.innerWidth - document.documentElement.clientWidth;
    this.scrollLock = { overflow: body.style.overflow, paddingRight: body.style.paddingRight };
    body.style.overflow = 'hidden';
    if (width > 0) body.style.paddingRight = `${width}px`;
  }
  unlockScroll() {
    const body = globalThis.document?.body;
    if (!body || !this.scrollLock) return;
    body.style.overflow = this.scrollLock.overflow;
    body.style.paddingRight = this.scrollLock.paddingRight;
    this.scrollLock = null;
  }

  setState(next) { this.state = Object.freeze(next); for (const listener of this.listeners) listener(this.state); }
}

function decodeImageUrl(url, signal) {
  if (signal?.aborted) return Promise.reject(abortError());
  if (typeof Image === 'undefined') {
    return Promise.reject(new PlatformError('image_decode_unavailable', 'Image decoding is unavailable'));
  }
  return new Promise((resolve, reject) => {
    const image = new Image();
    let settled = false;
    const cleanup = () => {
      image.onload = null;
      image.onerror = null;
      signal?.removeEventListener('abort', onAbort);
    };
    const finish = handler => {
      if (settled) return;
      settled = true;
      cleanup();
      handler();
    };
    const onAbort = () => finish(() => {
      image.src = '';
      reject(abortError());
    });
    image.onload = () => finish(resolve);
    image.onerror = () => finish(() => reject(new PlatformError(
      'image_decode_failed',
      'This image could not be displayed.',
    )));
    signal?.addEventListener('abort', onAbort, { once: true });
    image.decoding = 'async';
    image.src = url;
    if (signal?.aborted) onAbort();
  });
}

export function classifyDocument(documentRef) {
  const declared = String(documentRef?.mimeType ?? '').toLowerCase();
  const url = String(documentRef?.url ?? '');
  if (!/^https?:|^\.\.?\//.test(url)) return 'unsupported';
  if (declared === 'application/pdf' || /\.pdf(?:$|[?#])/i.test(url)) return 'pdf';
  if (declared.startsWith('image/') || /\.(png|jpe?g|webp|gif)(?:$|[?#])/i.test(url)) return 'image';
  if (declared === 'text/html' || /\.html?(?:$|[?#])/i.test(url)) return 'html';
  return 'unsupported';
}

function conciseDocumentError(error) {
  if (error?.name === 'PasswordException') return { code: 'encrypted', message: 'This PDF is encrypted.', action: 'open-original' };
  const code = error?.code ?? (error?.name === 'AbortError' ? 'cancelled' : 'document_failed');
  const messages = {
    document_oversized: 'This document is too large to open here.',
    document_too_many_pages: 'This document has too many pages to open here.',
    document_unavailable: 'This document could not be loaded.',
    document_worker_timeout: 'This document worker could not start.',
    malformed: 'This document could not be read.',
    image_decode_failed: 'This image could not be displayed.',
    image_decode_unavailable: 'This image could not be displayed.',
  };
  return { code, message: messages[code] ?? 'This document could not be opened.', action: 'open-original' };
}

function settleWithin(promise, timeoutMs, signal, code, onTimeout = null) {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      try { onTimeout?.(); } catch {}
      reject(new PlatformError(code, 'Document initialization timed out'));
    }, timeoutMs);
    const onAbort = () => reject(abortError());
    signal?.addEventListener('abort', onAbort, { once: true });
    Promise.resolve(promise).then(resolve, reject).finally(() => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    });
  });
}

function assertCurrentRender(viewer, session, revision) {
  if (viewer.session !== session || session.controller.signal.aborted || revision !== session.renderRevision) throw abortError();
}
function isRenderCancellation(error) {
  return error?.name === 'RenderingCancelledException' || error?.name === 'AbortException' || error?.name === 'AbortError';
}
function closedState() { return Object.freeze({ status: 'closed', type: null, documentRef: null, context: null, page: 1, pages: null, scale: 1, fitWidth: true, displayUrl: null, error: null, sessionId: null }); }
function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
function cryptoRandomId() { return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
