const CACHE = 'dropfinder-e2e-root-v5';
const SHELL = [
  '/tests/e2e/fixtures/harness.html',
  '/tests/e2e/fixtures/harness.js',
  '/tests/e2e/fixtures/sample.pdf',
];
const pendingWrites = new Set();

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => key.startsWith('dropfinder-e2e-') && key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.includes('/pdfjs-dist/') || url.pathname.includes('/.vite/deps/pdfjs-dist_')) {
    event.respondWith(fetch(event.request));
    return;
  }

  const network = fetch(event.request).then(response => ({
    response,
    cacheCopy: response.ok ? response.clone() : null,
  }));
  const write = network.then(async ({ cacheCopy }) => {
    if (!cacheCopy) return;
    const cache = await caches.open(CACHE);
    await cache.put(event.request, cacheCopy);
  }).catch(() => {});
  trackWrite(write);
  event.waitUntil(write);
  event.respondWith(network.then(({ response }) => response).catch(async () => {
    const cache = await caches.open(CACHE);
    return (await cache.match(event.request))
      || (await cache.match(event.request, { ignoreSearch: true }))
      || new Response('Offline', { status: 503 });
  }));
});

self.addEventListener('message', event => {
  if (event.data?.type === 'generation-status') event.source?.postMessage({ type: 'generation-status', id: 'e2e-generation-1' });
  if (event.data?.type === 'activate-generation') event.source?.postMessage({ type: 'generation-active', generationId: event.data.generationId });
  if (event.data?.type === 'flush-cache') {
    event.waitUntil(Promise.allSettled([...pendingWrites]).then(() => {
      event.source?.postMessage({ type: 'e2e-cache-ready', requestId: event.data.requestId });
    }));
  }
  if (event.data?.type === 'simulate-update') {
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clients => clients.forEach(client => client.postMessage({ type: 'generation-ready', generationId: event.data.generationId }))));
  }
});

function trackWrite(promise) {
  pendingWrites.add(promise);
  promise.finally(() => pendingWrites.delete(promise));
}
