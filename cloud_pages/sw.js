/* DropFinder generated-snapshot service worker. Relative-path safe for gh-pages/raw.githack. */
const SW_VERSION = 'platform-v1';
const APP_CACHE = `dropfinder-app-${SW_VERSION}`;
const META_CACHE = 'dropfinder-generation-meta-v1';
const DOCUMENT_CACHE = 'dropfinder-opened-documents-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg'];
const MAX_DETAIL_ENTRIES = 96;
const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;

self.addEventListener('install', event => {
  event.waitUntil(caches.open(APP_CACHE).then(cache => cache.addAll(SHELL)));
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter(key => key.startsWith('dropfinder-app-') && key !== APP_CACHE)
      .map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', event => {
  const message = event.data;
  if (message?.type === 'generation-status') {
    event.source?.postMessage({ type: 'generation-status', ...(activeGeneration || {}) });
  } else if (message?.type === 'activate-generation') {
    event.waitUntil(activatePreparedGeneration(message.generationId, event.source));
  } else if (message?.type === 'cache-document') {
    event.waitUntil(cacheOpenedDocument(message.document, event.source));
  }
});

let activeGeneration = null;
let preparing = null;

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, APP_CACHE, './index.html'));
    return;
  }
  if (isHashedAsset(url.pathname)) {
    event.respondWith(cacheFirst(event.request, APP_CACHE));
    return;
  }
  if (isManifestOrIndex(url.pathname)) {
    event.respondWith(generationAwareMetadata(event.request));
    return;
  }
  if (isDetailShard(url.pathname)) {
    event.respondWith(generationDetail(event.request));
    return;
  }
  event.respondWith(staleWhileRevalidate(event.request, APP_CACHE));
});

async function generationAwareMetadata(request) {
  try {
    const response = await fetch(request, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const generation = response.headers.get('x-dropfinder-generation');
    if (generation) await prepareGeneration(generation, request.url, response.clone());
    return response;
  } catch {
    const cached = await matchActiveGeneration(request);
    const legacy = await caches.match(request);
    return cached || legacy || new Response(JSON.stringify({ error: 'offline_unavailable' }), {
      status: 503, headers: { 'content-type': 'application/json' },
    });
  }
}

async function prepareGeneration(generationId, seedUrl, seedResponse) {
  if (activeGeneration?.id === generationId || preparing?.id === generationId) return;
  const cacheName = generationCacheName(generationId);
  preparing = { id: generationId, cacheName };
  const cache = await caches.open(cacheName);
  await cache.put(seedUrl, seedResponse);
  const manifestResponse = seedUrl.includes('catalog-manifest-v4.json')
    ? await cache.match(seedUrl)
    : await fetch(new URL('./catalog-manifest-v4.json', seedUrl), { cache: 'no-store' });
  if (!manifestResponse?.ok) { preparing = null; return; }
  const manifest = await manifestResponse.clone().json();
  if (manifest.generation_id !== generationId || !manifest.index?.url) { preparing = null; return; }
  const required = [new URL(manifest.index.url, seedUrl).href];
  for (const descriptor of Object.values(manifest.vendors || {})) if (descriptor?.url) required.push(new URL(descriptor.url, seedUrl).href);
  const responses = await Promise.all(required.map(url => fetch(url, { cache: 'no-store' })));
  if (responses.some(response => !response.ok || response.headers.get('x-dropfinder-generation') !== generationId)) {
    await caches.delete(cacheName); preparing = null; return;
  }
  await Promise.all(responses.map((response, index) => cache.put(required[index], response)));
  const metadata = await caches.open(META_CACHE);
  await metadata.put('./prepared.json', jsonResponse({ id: generationId, cacheName, preparedAt: Date.now() }));
  preparing = null;
  await broadcast({ type: 'generation-ready', generationId });
}

async function activatePreparedGeneration(generationId, source) {
  const metadata = await caches.open(META_CACHE);
  const preparedResponse = await metadata.match('./prepared.json');
  const prepared = preparedResponse ? await preparedResponse.json() : null;
  if (!prepared || prepared.id !== generationId || !(await caches.has(prepared.cacheName))) {
    source?.postMessage({ type: 'generation-error', generationId, code: 'generation_incomplete' });
    return;
  }
  const previous = activeGeneration;
  activeGeneration = { id: prepared.id, cacheName: prepared.cacheName };
  await metadata.put('./active.json', jsonResponse(activeGeneration));
  await cleanupGenerations(new Set([activeGeneration.cacheName, previous?.cacheName].filter(Boolean)));
  await broadcast({ type: 'generation-active', generationId });
}

async function restoreActiveGeneration() {
  const metadata = await caches.open(META_CACHE);
  const response = await metadata.match('./active.json');
  activeGeneration = response ? await response.json() : null;
}
restoreActiveGeneration();

async function generationDetail(request) {
  const generation = request.headers.get('x-dropfinder-generation') || new URL(request.url).searchParams.get('generation');
  if (activeGeneration && generation && generation !== activeGeneration.id) return new Response('', { status: 409 });
  const cache = activeGeneration ? await caches.open(activeGeneration.cacheName) : null;
  const hit = await cache?.match(request);
  if (hit) return hit;
  try {
    const response = await fetch(request);
    if (!response.ok) return response;
    const responseGeneration = response.headers.get('x-dropfinder-generation');
    if (activeGeneration && responseGeneration && responseGeneration !== activeGeneration.id) return new Response('', { status: 409 });
    await cache?.put(request, response.clone());
    if (cache) await trimCache(cache, MAX_DETAIL_ENTRIES, url => isDetailShard(new URL(url).pathname));
    return response;
  } catch {
    return hit || new Response('', { status: 503 });
  }
}

async function cacheOpenedDocument(document, source) {
  if (!document?.url) return;
  try {
    const request = new Request(document.url, { credentials: 'omit', referrerPolicy: 'no-referrer' });
    const response = await fetch(request);
    const length = Number(response.headers.get('content-length'));
    if (!response.ok || (Number.isFinite(length) && length > MAX_DOCUMENT_BYTES)) return;
    const bytes = await response.clone().arrayBuffer();
    if (bytes.byteLength > MAX_DOCUMENT_BYTES) return;
    const cache = await caches.open(DOCUMENT_CACHE);
    await cache.put(request, response);
  } catch (error) {
    if (error?.name === 'QuotaExceededError') source?.postMessage({ type: 'cache-quota', resource: 'document' });
  }
}

async function matchActiveGeneration(request) {
  if (!activeGeneration) await restoreActiveGeneration();
  return activeGeneration ? caches.open(activeGeneration.cacheName).then(cache => cache.match(request)) : null;
}
async function cleanupGenerations(keep) {
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith('dropfinder-data-') && !keep.has(key)).map(key => caches.delete(key)));
}
async function trimCache(cache, max, predicate) {
  const keys = (await cache.keys()).filter(request => predicate(request.url));
  await Promise.all(keys.slice(0, Math.max(0, keys.length - max)).map(request => cache.delete(request)));
}
function generationCacheName(id) { return `dropfinder-data-${String(id).replace(/[^a-z0-9._-]/gi, '_')}`; }
function isHashedAsset(path) { return /\.[a-f0-9]{8,}\.(?:js|css|woff2?|png|svg|webp)$/i.test(path); }
function isManifestOrIndex(path) { return /(?:catalog-manifest-v4|catalog-index|vendor-profiles|catalog|status)\.json$/i.test(path); }
function isDetailShard(path) { return /(?:details?|shards?)\/.*\.json$/i.test(path); }
async function cacheFirst(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request); if (hit) return hit; const response = await fetch(request); if (response.ok) await cache.put(request, response.clone()); return response; }
async function staleWhileRevalidate(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request); const network = fetch(request).then(response => { if (response.ok) cache.put(request, response.clone()); return response; }).catch(() => null); if (hit) { void network; return hit; } return (await network) || new Response('', { status: 503 }); }
async function networkFirst(request, cacheName, fallback) { const cache = await caches.open(cacheName); try { const response = await fetch(request); if (response.ok) await cache.put(request, response.clone()); return response; } catch { return (await cache.match(request)) || (await cache.match(fallback)) || new Response('Offline', { status: 503 }); } }
async function broadcast(message) { for (const client of await self.clients.matchAll({ type: 'window', includeUncontrolled: true })) client.postMessage(message); }
function jsonResponse(value) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }); }
