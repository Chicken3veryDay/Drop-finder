/* DropFinder generated-snapshot service worker. Relative-path safe for gh-pages/raw.githack. */
const SW_VERSION = 'platform-v2';
const APP_CACHE = `dropfinder-app-${SW_VERSION}`;
const META_CACHE = 'dropfinder-generation-meta-v1';
const DOCUMENT_CACHE = 'dropfinder-opened-documents-v1';
const SHELL_MANIFEST = './app-shell.json';
const FALLBACK_SHELL = ['./', './index.html', './manifest.webmanifest', './icon.svg', './data/catalog.json', './data/status.json', './data/runtime.json'];
const MAX_DETAIL_ENTRIES = 96;
const MAX_DOCUMENT_ENTRIES = 12;
const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;
const MAX_SHELL_ASSETS = 256;

let activeGeneration = null;
let preparing = null;
let restorePromise = restoreActiveGeneration();

self.addEventListener('install', event => {
  event.waitUntil(cacheApplicationShell());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    await restorePromise;
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
    event.waitUntil(restorePromise.then(() => event.source?.postMessage({ type: 'generation-status', ...(activeGeneration || {}) })));
  } else if (message?.type === 'activate-generation') {
    event.waitUntil(activatePreparedGeneration(message.generationId, event.source));
  } else if (message?.type === 'cache-document') {
    event.waitUntil(cacheOpenedDocument(message.document, event.source));
  }
});

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

async function cacheApplicationShell() {
  const cache = await caches.open(APP_CACHE);
  let assets = FALLBACK_SHELL;
  try {
    const response = await fetch(SHELL_MANIFEST, { cache: 'no-store' });
    const manifest = await response.json();
    if (response.ok && manifest.schema_version === 'dropfinder-app-shell-v1'
      && Array.isArray(manifest.assets) && manifest.assets.length > 0 && manifest.assets.length <= MAX_SHELL_ASSETS
      && manifest.assets.every(asset => typeof asset === 'string' && !asset.startsWith('/'))) {
      assets = [...new Set([SHELL_MANIFEST, ...manifest.assets])];
    }
  } catch {}
  await cache.addAll(assets);
}

async function generationAwareMetadata(request) {
  await restorePromise;
  try {
    const response = await fetch(request, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const url = new URL(request.url);
    const identity = await readGenerationIdentity(response.clone());
    if (identity.generationId) {
      if (isLegacyCatalogMember(url.pathname)) {
        await prepareLegacyGeneration(identity.generationId, request, response.clone());
      } else {
        await prepareGeneration(identity.generationId, request.url, response.clone(), identity.payload);
      }
    }
    return response;
  } catch {
    const cached = await matchActiveGeneration(request);
    const legacy = await caches.match(request, { ignoreSearch: true });
    return cached || legacy || new Response(JSON.stringify({ error: 'offline_unavailable' }), {
      status: 503, headers: { 'content-type': 'application/json' },
    });
  }
}

async function readGenerationIdentity(response) {
  const header = response.headers.get('x-dropfinder-generation');
  let payload = null;
  if (response.headers.get('content-type')?.includes('json') || !header) {
    try { payload = await response.json(); } catch {}
  }
  return { generationId: header || payload?.generation_id || payload?.generated_at || null, payload };
}

async function prepareLegacyGeneration(generationId, request, response) {
  if (activeGeneration?.id === generationId) return;
  const cacheName = generationCacheName(generationId);
  const cache = await caches.open(cacheName);
  await safeCachePut(cache, request, response);
  const catalogUrl = new URL('./catalog.json', request.url).href;
  const statusUrl = new URL('./status.json', request.url).href;
  const [catalogResponse, statusResponse] = await Promise.all([
    cache.match(catalogUrl, { ignoreSearch: true }),
    cache.match(statusUrl, { ignoreSearch: true }),
  ]);
  if (!catalogResponse || !statusResponse) return;
  let catalog; let status;
  try {
    [catalog, status] = await Promise.all([catalogResponse.clone().json(), statusResponse.clone().json()]);
  } catch { return; }
  if (catalog.generated_at !== generationId || status.generated_at !== generationId
    || catalog.product_count !== catalog.products?.length
    || status.product_count !== catalog.product_count) return;
  await markPrepared({ id: generationId, cacheName, kind: 'legacy', preparedAt: Date.now() });
}

async function prepareGeneration(generationId, seedUrl, seedResponse, seedPayload = null) {
  if (activeGeneration?.id === generationId || preparing?.id === generationId) return;
  const cacheName = generationCacheName(generationId);
  preparing = { id: generationId, cacheName };
  const cache = await caches.open(cacheName);
  await safeCachePut(cache, seedUrl, seedResponse);
  const realCatalogV4 = seedUrl.includes('/data/catalog-v4/');
  const manifestResponse = seedUrl.includes('catalog-manifest-v4.json') || seedUrl.endsWith('/catalog-v4/manifest.json')
    ? await cache.match(seedUrl, { ignoreSearch: true })
    : await fetch(new URL(realCatalogV4 ? './manifest.json' : './catalog-manifest-v4.json', seedUrl), { cache: 'no-store' });
  if (!manifestResponse?.ok) { preparing = null; return; }
  const manifest = seedPayload?.index || seedPayload?.compact_index ? seedPayload : await manifestResponse.clone().json();
  const descriptor = manifest.compact_index ?? manifest.index;
  const supportedSchema = manifest.schema_version === 4 || manifest.schema_version === 'dropfinder-catalog-manifest-v4';
  if (manifest.generation_id !== generationId || !supportedSchema || !(descriptor?.url || descriptor?.path)) { preparing = null; return; }
  const publicationBase = catalogPublicationBase(seedUrl);
  const required = [new URL(descriptor.path ?? descriptor.url, publicationBase).href];
  const vendorDescriptor = manifest.vendor_profiles;
  if (vendorDescriptor?.url || vendorDescriptor?.path) required.push(new URL(vendorDescriptor.path ?? vendorDescriptor.url, publicationBase).href);
  for (const vendor of Object.values(manifest.vendors || {})) if (vendor?.url || vendor?.path) required.push(new URL(vendor.path ?? vendor.url, publicationBase).href);
  const responses = await Promise.all(required.map(url => fetch(url, { cache: 'no-store' })));
  const identities = await Promise.all(responses.map(response => response.ok ? readGenerationIdentity(response.clone()) : { generationId: null }));
  if (responses.some(response => !response.ok) || identities.some(identity => identity.generationId !== generationId)) {
    await caches.delete(cacheName); preparing = null; return;
  }
  await Promise.all(responses.map((response, index) => safeCachePut(cache, required[index], response)));
  preparing = null;
  await markPrepared({ id: generationId, cacheName, kind: 'v4', preparedAt: Date.now() });
}

async function markPrepared(prepared) {
  const metadata = await caches.open(META_CACHE);
  await metadata.put('./prepared.json', jsonResponse(prepared));
  await activatePreparedGeneration(prepared.id, null);
}

async function activatePreparedGeneration(generationId, source) {
  await restorePromise;
  const metadata = await caches.open(META_CACHE);
  const preparedResponse = await metadata.match('./prepared.json');
  const prepared = preparedResponse ? await preparedResponse.json() : null;
  if (!prepared || prepared.id !== generationId || !(await caches.has(prepared.cacheName))) {
    source?.postMessage({ type: 'generation-error', generationId, code: 'generation_incomplete' });
    return;
  }
  const previous = activeGeneration;
  activeGeneration = { id: prepared.id, cacheName: prepared.cacheName, kind: prepared.kind };
  await metadata.put('./active.json', jsonResponse(activeGeneration));
  await cleanupGenerations(new Set([activeGeneration.cacheName, previous?.cacheName].filter(Boolean)));
  await broadcast({ type: 'generation-active', generationId });
}

async function restoreActiveGeneration() {
  try {
    const metadata = await caches.open(META_CACHE);
    const response = await metadata.match('./active.json');
    activeGeneration = response ? await response.json() : null;
  } catch { activeGeneration = null; }
}

async function generationDetail(request) {
  await restorePromise;
  const generation = request.headers.get('x-dropfinder-generation') || new URL(request.url).searchParams.get('generation');
  if (activeGeneration && generation && generation !== activeGeneration.id) return new Response('', { status: 409 });
  const cache = activeGeneration ? await caches.open(activeGeneration.cacheName) : null;
  const hit = await cache?.match(request, { ignoreSearch: true });
  if (hit) return hit;
  try {
    const response = await fetch(request);
    if (!response.ok) return response;
    const identity = await readGenerationIdentity(response.clone());
    if (activeGeneration && identity.generationId && identity.generationId !== activeGeneration.id) return new Response('', { status: 409 });
    if (cache) {
      await safeCachePut(cache, request, response.clone());
      await trimCache(cache, MAX_DETAIL_ENTRIES, url => isDetailShard(new URL(url).pathname));
    }
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
    const cacheControl = response.headers.get('cache-control') || '';
    if (!response.ok || response.type === 'opaque' || /private|no-store/i.test(cacheControl)
      || (Number.isFinite(length) && length > MAX_DOCUMENT_BYTES)) return;
    const bytes = await response.clone().arrayBuffer();
    if (bytes.byteLength > MAX_DOCUMENT_BYTES) return;
    const cache = await caches.open(DOCUMENT_CACHE);
    await safeCachePut(cache, request, response);
    await trimCache(cache, MAX_DOCUMENT_ENTRIES, () => true);
  } catch (error) {
    if (error?.name === 'QuotaExceededError') source?.postMessage({ type: 'cache-quota', resource: 'document' });
  }
}

async function safeCachePut(cache, request, response) {
  try { await cache.put(request, response); }
  catch (error) {
    if (error?.name === 'QuotaExceededError') await broadcast({ type: 'cache-quota', resource: 'generation' });
    throw error;
  }
}
async function matchActiveGeneration(request) {
  await restorePromise;
  return activeGeneration ? caches.open(activeGeneration.cacheName).then(cache => cache.match(request, { ignoreSearch: true })) : null;
}
async function cleanupGenerations(keep) {
  const keys = await caches.keys();
  await Promise.all(keys.filter(key => key.startsWith('dropfinder-data-') && !keep.has(key)).map(key => caches.delete(key)));
}
async function trimCache(cache, max, predicate) {
  const keys = (await cache.keys()).filter(request => predicate(request.url));
  await Promise.all(keys.slice(0, Math.max(0, keys.length - max)).map(request => cache.delete(request)));
}
function catalogPublicationBase(url) {
  const parsed = new URL(url);
  const marker = '/data/catalog-v4/';
  const index = parsed.pathname.lastIndexOf(marker);
  if (index >= 0) {
    parsed.pathname = parsed.pathname.slice(0, index + 1);
    parsed.search = '';
    parsed.hash = '';
  }
  return parsed.href;
}
function generationCacheName(id) { return `dropfinder-data-${String(id).replace(/[^a-z0-9._-]/gi, '_')}`; }
function isHashedAsset(path) { return /\.[a-f0-9]{8,}\.(?:js|css|woff2?|png|svg|webp)$/i.test(path); }
function isManifestOrIndex(path) { return /(?:catalog-manifest-v4|catalog-index|vendor-profiles|catalog|status)\.json$/i.test(path) || /\/catalog-v4\/(?:manifest|index)\.json$/i.test(path); }
function isLegacyCatalogMember(path) { return /\/(?:catalog|status)\.json$/i.test(path) && !path.includes('catalog-manifest-v4'); }
function isDetailShard(path) { return /(?:details?|shards?)\/.*\.json$/i.test(path); }
async function cacheFirst(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request, { ignoreSearch: true }); if (hit) return hit; const response = await fetch(request); if (response.ok) await safeCachePut(cache, request, response.clone()); return response; }
async function staleWhileRevalidate(request, cacheName) { const cache = await caches.open(cacheName); const hit = await cache.match(request, { ignoreSearch: true }); const network = fetch(request).then(response => { if (response.ok) safeCachePut(cache, request, response.clone()); return response; }).catch(() => null); if (hit) { void network; return hit; } return (await network) || new Response('', { status: 503 }); }
async function networkFirst(request, cacheName, fallback) { const cache = await caches.open(cacheName); try { const response = await fetch(request); if (response.ok) await safeCachePut(cache, request, response.clone()); return response; } catch { return (await cache.match(request, { ignoreSearch: true })) || (await cache.match(fallback, { ignoreSearch: true })) || new Response('Offline', { status: 503 }); } }
async function broadcast(message) { for (const client of await self.clients.matchAll({ type: 'window', includeUncontrolled: true })) client.postMessage(message); }
function jsonResponse(value) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }); }
