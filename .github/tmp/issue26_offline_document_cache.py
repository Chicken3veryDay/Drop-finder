from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


integration_path = "web/src/features/integration/register-marketplace-props.tsx"
replace_once(
    integration_path,
    '''type PwaCoordinator = {
  register(scriptUrl?: string, options?: { scope: string }): Promise<unknown>;
};
''',
    '''type PwaCoordinator = {
  register(scriptUrl?: string, options?: { scope: string }): Promise<unknown>;
  cacheOpenedDocument(document: MarketplaceDocument): Promise<boolean>;
};

export async function openMarketplaceDocument(
  viewer: PlatformDocumentViewer,
  pwa: PwaCoordinator | undefined,
  request: DocumentViewerRequest,
): Promise<void> {
  await viewer.open(request.document, {
    productId: request.productId,
    variantId: request.variantId,
    invoker: request.invokingElement,
  });
  const state = viewer.snapshot();
  if (state.status !== "ready" || (state.type !== "pdf" && state.type !== "image")) return;
  void Promise.resolve()
    .then(() => pwa?.cacheOpenedDocument(request.document))
    .catch(() => undefined);
}
''',
)
replace_once(
    integration_path,
    '''  const documentViewer = useMemo(() => viewer ? {
    async open(request: DocumentViewerRequest) {
      setDocumentRequest(request);
      await viewer.open(request.document, {
        productId: request.productId,
        variantId: request.variantId,
        invoker: request.invokingElement,
      });
    },
  } : undefined, [viewer]);
''',
    '''  const documentViewer = useMemo(() => viewer ? {
    async open(request: DocumentViewerRequest) {
      setDocumentRequest(request);
      await openMarketplaceDocument(viewer, pwa, request);
    },
  } : undefined, [viewer, pwa]);
''',
)

sw_path = "cloud_pages/sw.js"
replace_once(sw_path, "const SW_VERSION = 'platform-v3';", "const SW_VERSION = 'platform-v4';")
replace_once(
    sw_path,
    '''  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
''',
    '''  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) {
    event.respondWith(withOpenedDocumentFallback(event.request));
    return;
  }
''',
)
replace_once(
    sw_path,
    '''  event.respondWith(staleWhileRevalidate(event.request, APP_CACHE));
});

async function cacheApplicationShell() {
''',
    '''  event.respondWith(withOpenedDocumentFallback(
    event.request,
    () => staleWhileRevalidate(event.request, APP_CACHE),
  ));
});

async function withOpenedDocumentFallback(request, load = () => fetch(request)) {
  let response = null;
  try { response = await load(); } catch {}
  if (response && (response.ok || !NAVIGATION_FALLBACK_STATUS.has(response.status))) return response;
  const cache = await caches.open(DOCUMENT_CACHE);
  const cached = await cache.match(request);
  return cached || response || new Response('', { status: 503 });
}

async function cacheApplicationShell() {
''',
)

service_worker_test = "web/test/service-worker.test.mjs"
replace_once(
    service_worker_test,
    '''  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, URL, DOMException, console, setTimeout, clearTimeout });
''',
    '''  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, ReadableStream, URL, DOMException, console, setTimeout, clearTimeout });
''',
)
replace_once(
    service_worker_test,
    '''function navigationRequest(path) {
''',
    '''test('explicitly opened same-origin and cross-origin documents reopen offline from the dedicated cache', async () => {
  const runtime = await createRuntime();
  const urls = [
    `${BASE}opened-report.pdf`,
    'https://documents.example/opened-report.pdf',
  ];

  for (const url of urls) {
    runtime.setResponse(url, new Response('bounded-document-body', {
      headers: { 'content-type': 'application/pdf', 'cache-control': 'public, max-age=60' },
    }));
    await runtime.dispatch('message', {
      data: { type: 'cache-document', document: { url, mimeType: 'application/pdf' } },
      source: { postMessage() {} },
    });

    const documentCacheName = (await runtime.caches.keys())
      .find(name => name.startsWith('dropfinder-opened-documents-v2-'));
    assert.ok(documentCacheName);
    const documentCache = await runtime.caches.open(documentCacheName);
    assert.ok(await documentCache.match(url));

    runtime.setOffline(true);
    const response = await runtime.dispatch('fetch', { request: new Request(url) });
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'bounded-document-body');
    runtime.setOffline(false);
  }
});

test('ineligible opened documents do not become readable offline', async () => {
  const runtime = await createRuntime();
  const url = 'https://documents.example/private-report.pdf';
  runtime.setResponse(url, new Response('private-document', {
    headers: { 'content-type': 'application/pdf', 'cache-control': 'private, no-store' },
  }));
  await runtime.dispatch('message', {
    data: { type: 'cache-document', document: { url, mimeType: 'application/pdf' } },
    source: { postMessage() {} },
  });

  const documentCacheName = (await runtime.caches.keys())
    .find(name => name.startsWith('dropfinder-opened-documents-v2-'));
  if (documentCacheName) {
    const documentCache = await runtime.caches.open(documentCacheName);
    assert.equal(await documentCache.match(url), undefined);
  }

  runtime.setOffline(true);
  const response = await runtime.dispatch('fetch', { request: new Request(url) });
  assert.equal(response.status, 503);
});

function navigationRequest(path) {
''',
)
