const CACHE = 'dropfinder-e2e-root-v2';
const SHELL = [
  '/tests/e2e/fixtures/harness.html',
  '/tests/e2e/fixtures/harness.js',
  '/tests/e2e/fixtures/sample.pdf',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => key.startsWith('dropfinder-e2e-') && key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== location.origin) return;
  event.respondWith(caches.open(CACHE).then(async cache => {
    try {
      const response = await fetch(event.request);
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch {
      return (await cache.match(event.request))
        || (await cache.match(event.request, { ignoreSearch: true }))
        || new Response('Offline', { status: 503 });
    }
  }));
});

self.addEventListener('message', event => {
  if (event.data?.type === 'generation-status') event.source?.postMessage({ type: 'generation-status', id: 'e2e-generation-1' });
  if (event.data?.type === 'activate-generation') event.source?.postMessage({ type: 'generation-active', generationId: event.data.generationId });
  if (event.data?.type === 'simulate-update') {
    event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clients => clients.forEach(client => client.postMessage({ type: 'generation-ready', generationId: event.data.generationId }))));
  }
});
