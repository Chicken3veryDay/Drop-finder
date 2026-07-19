from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    "import { PlatformError, abortError } from '../contracts.js';\n",
    "import { PlatformError, abortError } from '../contracts.js';\nimport { readBoundedBytes } from '../network/read-bounded-bytes.js';\n",
    "bounded reader import",
)
replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    "  workerStartupTimeoutMs: 15_000,\n",
    "  workerStartupTimeoutMs: 15_000,\n  cleanupTimeoutMs: 1_000,\n",
    "cleanup timeout option",
)
replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    '''    const length = Number(response.headers.get('content-length'));
    if (Number.isFinite(length) && length > this.options.maxBytes) throw new PlatformError('document_oversized', 'Document is too large');
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.byteLength > this.options.maxBytes) throw new PlatformError('document_oversized', 'Document is too large');
''',
    '''    const bytes = await readBoundedBytes(response, {
      maxBytes: this.options.maxBytes,
      signal,
      oversizedError: () => new PlatformError('document_oversized', 'Document is too large'),
    });
''',
    "bounded PDF body",
)
replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    '''      const length = Number(response.headers.get('content-length'));
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
''',
    '''      if (!response.ok) {
        throw new PlatformError('document_unavailable', `Image request failed with ${response.status}`);
      }
      const bytes = await readBoundedBytes(response, {
        maxBytes: this.options.maxBytes,
        signal,
        oversizedError: () => new PlatformError('document_oversized', 'Image is too large'),
      });
''',
    "bounded image body",
)
replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    '''      cleanup = this.cleanupSequence.then(async () => {
        try { await session.renderSequence; } catch {}
        try { await session.loadingTask?.destroy?.(); } catch {}
        try { await session.pdf?.cleanup?.(); } catch {}
        if (session.objectUrl) URL.revokeObjectURL(session.objectUrl);
      });
''',
    '''      cleanup = this.cleanupSequence.then(async () => {
        await settleCleanupWithin(Promise.allSettled([
          Promise.resolve().then(() => session.loadingTask?.destroy?.()),
          Promise.resolve().then(() => session.pdf?.destroy?.()),
        ]), this.options.cleanupTimeoutMs);
        await settleCleanupWithin(session.renderSequence, this.options.cleanupTimeoutMs);
        await settleCleanupWithin(
          Promise.resolve().then(() => session.pdf?.cleanup?.()),
          this.options.cleanupTimeoutMs,
        );
        if (session.objectUrl) URL.revokeObjectURL(session.objectUrl);
      });
''',
    "bounded close ordering",
)
replace_once(
    "web/src/platform/documents/document-viewer-capability.js",
    '''function settleWithin(promise, timeoutMs, signal, code, onTimeout = null) {
''',
    '''async function settleCleanupWithin(promise, timeoutMs) {
  let timer = null;
  try {
    await Promise.race([
      Promise.resolve(promise).catch(() => undefined),
      new Promise(resolve => { timer = setTimeout(resolve, Math.max(0, timeoutMs)); }),
    ]);
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

function settleWithin(promise, timeoutMs, signal, code, onTimeout = null) {
''',
    "cleanup timeout helper",
)

sw = Path("cloud_pages/sw.js")
text = sw.read_text(encoding="utf-8")
helper = '''async function readBoundedCacheResponse(response, maxBytes) {
  const contentLength = response.headers.get('content-length');
  const declared = contentLength === null ? null : Number(contentLength);
  if (Number.isFinite(declared) && declared > maxBytes) {
    try { await response.body?.cancel('Document exceeds its cache limit'); } catch {}
    return null;
  }
  if (!response.body) {
    return new Response(null, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }

  const reader = response.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value);
      if (totalBytes + chunk.byteLength > maxBytes) {
        try { await reader.cancel('Document exceeds its cache limit'); } catch {}
        return null;
      }
      chunks.push(chunk);
      totalBytes += chunk.byteLength;
    }
  } finally {
    try { reader.releaseLock(); } catch {}
  }

  let chunkIndex = 0;
  const body = new ReadableStream({
    pull(controller) {
      if (chunkIndex >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(chunks[chunkIndex]);
      chunks[chunkIndex] = null;
      chunkIndex += 1;
    },
    cancel() { chunks.length = 0; },
  });
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

'''
if helper not in text:
    marker = "async function cacheOpenedDocument(document, source) {\n"
    count = text.count(marker)
    if count != 1:
        raise SystemExit(f"service-worker bounded helper insertion: expected one match, found {count}")
    text = text.replace(marker, helper + marker, 1)
sw.write_text(text, encoding="utf-8")

replace_once(
    "cloud_pages/sw.js",
    '''    const response = await fetch(request);
    const length = Number(response.headers.get('content-length'));
    const cacheControl = response.headers.get('cache-control') || '';
    if (!response.ok || response.type === 'opaque' || /private|no-store/i.test(cacheControl)
      || (Number.isFinite(length) && length > MAX_DOCUMENT_BYTES)) return;
    const bytes = await response.clone().arrayBuffer();
    if (bytes.byteLength > MAX_DOCUMENT_BYTES) return;
    const cache = await caches.open(DOCUMENT_CACHE);
    await safeCachePut(cache, request, response);
''',
    '''    const response = await fetch(request);
    const cacheControl = response.headers.get('cache-control') || '';
    if (!response.ok || response.type === 'opaque' || /private|no-store/i.test(cacheControl)) return;
    const bounded = await readBoundedCacheResponse(response, MAX_DOCUMENT_BYTES);
    if (!bounded) return;
    const cache = await caches.open(DOCUMENT_CACHE);
    await safeCachePut(cache, request, bounded);
''',
    "bounded opened-document cache",
)
