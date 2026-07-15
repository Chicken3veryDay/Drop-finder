const CACHE = 'dropfinder-e2e-shell-v1';
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['./harness.html', './harness.js', './sample.pdf'])).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== location.origin) return;
  event.respondWith(caches.open(CACHE).then(async cache => {
    const hit = await cache.match(event.request);
    if (hit) return hit;
    try { const response = await fetch(event.request); if (response.ok) await cache.put(event.request, response.clone()); return response; }
    catch { return hit || new Response('Offline', { status: 503 }); }
  }));
});
self.addEventListener('message', event => {
  if (event.data?.type === 'generation-status') event.source?.postMessage({ type: 'generation-status', id: 'e2e-generation-1' });
  if (event.data?.type === 'activate-generation') event.source?.postMessage({ type: 'generation-active', generationId: event.data.generationId });
  if (event.data?.type === 'simulate-update') event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => clients.forEach(client => client.postMessage({ type: 'generation-ready', generationId: event.data.generationId }))));
});
