import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const ORIGIN = 'https://app.test';
const BASE = `${ORIGIN}/cloud_pages/`;

class FakeCache {
  constructor(fetcher) { this.fetcher = fetcher; this.entries = new Map(); this.putError = null; this.writeCount = 0; }
  failNextPut(error) { this.putError = error; }
  key(input) { return new URL(input?.url ?? String(input), BASE).href.split('#')[0]; }
  async match(input, options = {}) {
    const key = this.key(input);
    if (!options.ignoreSearch) return this.entries.get(key)?.clone() ?? undefined;
    const target = new URL(key); target.search = '';
    for (const [candidate, response] of this.entries) {
      const url = new URL(candidate); url.search = '';
      if (url.href === target.href) return response.clone();
    }
    return undefined;
  }
  async put(input, response) {
    if (this.putError) { const error = this.putError; this.putError = null; throw error; }
    this.writeCount += 1;
    this.entries.set(this.key(input), response.clone());
  }
  async addAll(inputs) {
    for (const input of inputs) {
      const response = await this.fetcher(input);
      if (!response.ok) throw new Error(`addAll HTTP ${response.status}`);
      await this.put(input, response);
    }
  }
  async keys() { return [...this.entries.keys()].map(url => new Request(url)); }
  async delete(input) { return this.entries.delete(this.key(input)); }
}

class FakeCacheStorage {
  constructor(fetcher) { this.fetcher = fetcher; this.caches = new Map(); }
  async open(name) { if (!this.caches.has(name)) this.caches.set(name, new FakeCache(this.fetcher)); return this.caches.get(name); }
  async keys() { return [...this.caches.keys()]; }
  async delete(name) { return this.caches.delete(name); }
  async has(name) { return this.caches.has(name); }
  async match(input, options) {
    for (const cache of this.caches.values()) {
      const hit = await cache.match(input, options);
      if (hit) return hit;
    }
    return undefined;
  }
}

async function createRuntime() {
  const listeners = new Map();
  const messages = [];
  const network = new Map();
  const fetches = [];
  let offline = false;
  const fetcher = async input => {
    if (offline) throw new TypeError('offline');
    const url = new URL(input?.url ?? String(input), BASE).href;
    fetches.push(url);
    if (url === `${BASE}app-shell.json`) return json({ schema_version: 'dropfinder-app-shell-v1', assets: ['./', './index.html', './manifest.webmanifest', './icon.svg'] });
    if ([BASE, `${BASE}index.html`, `${BASE}manifest.webmanifest`, `${BASE}icon.svg`].includes(url)) return new Response(`asset:${url}`);
    const response = network.get(url);
    if (!response) return new Response('', { status: 404 });
    return response.clone();
  };
  const caches = new FakeCacheStorage(fetcher);
  const self = {
    location: { origin: ORIGIN },
    clients: { claim: async () => {}, matchAll: async () => [{ postMessage: message => messages.push(message) }] },
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, ReadableStream, URL, DOMException, console, setTimeout, clearTimeout });
  const source = await readFile(new URL('../../cloud_pages/sw.js', import.meta.url), 'utf8');
  vm.runInContext(source, context, { filename: 'cloud_pages/sw.js' });

  async function dispatch(name, data = {}) {
    const waits = [];
    let responsePromise;
    const event = {
      ...data,
      waitUntil: promise => waits.push(Promise.resolve(promise)),
      respondWith: promise => { responsePromise = Promise.resolve(promise); },
    };
    listeners.get(name)?.(event);
    await Promise.all(waits);
    return responsePromise ? responsePromise : undefined;
  }
  return {
    network, caches, messages, fetches, dispatch,
    resetFetches() { fetches.length = 0; },
    isHashedAsset(path) { return context.isHashedAsset(path); },
    setOffline(value) { offline = value; },
    setResponse(path, response) { network.set(new URL(path, BASE).href, response); },
    setJson(path, value, headers = {}) { network.set(new URL(path, BASE).href, json(value, headers)); },
  };
}

test('service worker installs shell from metadata and activates a complete legacy generation', async () => {
  const runtime = await createRuntime();
  await runtime.dispatch('install');
  const appCaches = (await runtime.caches.keys()).filter(name => name.startsWith('dropfinder-app-'));
  assert.equal(appCaches.length, 1);
  const appCache = await runtime.caches.open(appCaches[0]);
  assert.ok(await appCache.match(`${BASE}app-shell.json`));
  assert.ok(await appCache.match(`${BASE}index.html`));

  const generation = '2026-07-15T00:00:00Z';
  runtime.setJson('data/catalog.json', { generated_at: generation, product_count: 1, products: [{ id: 'p1' }] });
  runtime.setJson('data/status.json', { generated_at: generation, product_count: 1 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === generation));

  runtime.setOffline(true);
  const cached = await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json?offline=1`) });
  assert.equal(cached.status, 200);
  assert.equal((await cached.json()).product_count, 1);
});

test('service worker routes current Vite assets cache-first without network revalidation', async () => {
  const runtime = await createRuntime();
  await runtime.dispatch('install');

  const shell = JSON.parse(await readFile(new URL('../../cloud_pages/app-shell.json', import.meta.url), 'utf8'));
  const generatedAssets = shell.assets.filter(asset => asset.startsWith('./assets/'));
  assert.ok(generatedAssets.length > 0);

  const appCacheName = (await runtime.caches.keys()).find(name => name.startsWith('dropfinder-app-'));
  const appCache = await runtime.caches.open(appCacheName);
  for (const asset of generatedAssets) {
    const url = new URL(asset, BASE).href;
    await appCache.put(url, new Response(`cached:${asset}`));
    runtime.network.set(new URL(`${asset}?cache-bust=ignored`, BASE).href, new Response(`network:${asset}`));
  }

  runtime.resetFetches();
  const writesBefore = appCache.writeCount;
  for (const asset of generatedAssets) {
    const response = await runtime.dispatch('fetch', { request: new Request(new URL(`${asset}?cache-bust=ignored`, BASE)) });
    assert.equal(await response.text(), `cached:${asset}`);
  }

  assert.deepEqual(runtime.fetches, []);
  assert.equal(appCache.writeCount, writesBefore);
});

test('hashed-asset classification follows the configured Vite filename contract', async () => {
  const runtime = await createRuntime();
  const viteConfig = await readFile(new URL('../vite.config.ts', import.meta.url), 'utf8');
  assert.match(viteConfig, /entryFileNames:\s*["']assets\/app-\[hash\]\.js["']/);
  assert.match(viteConfig, /chunkFileNames:\s*["']assets\/chunk-\[hash\]\.js["']/);
  assert.match(viteConfig, /assetFileNames:\s*["']assets\/\[name\]-\[hash\]\[extname\]["']/);

  for (const path of [
    '/cloud_pages/assets/app-D1_HGx2j.js',
    '/cloud_pages/assets/chunk-CgeV8iME.js',
    '/cloud_pages/assets/index-UDKaS5UJ.css',
    '/cloud_pages/assets/marketplace-query-worker-CNdCK8BC.js',
    '/cloud_pages/assets/pdf.worker.min-B9x_2-qa.mjs',
    '/cloud_pages/assets/font-B9x_2-qa.woff2',
    '/cloud_pages/assets/image-B9x_2-qa.avif',
  ]) assert.equal(runtime.isHashedAsset(path), true, path);

  for (const path of [
    '/cloud_pages/index.html',
    '/cloud_pages/manifest.webmanifest',
    '/cloud_pages/assets/app.js',
    '/cloud_pages/assets/chunk-latest.js',
    '/cloud_pages/assets/chunk-latest-build.js',
    '/cloud_pages/data/catalog-B9x_2-qa.json',
  ]) assert.equal(runtime.isHashedAsset(path), false, path);
});

test('service worker does not activate incomplete snapshots and switches only after an explicit update', async () => {
  const runtime = await createRuntime();
  const first = 'g1';
  runtime.setJson('data/catalog.json', { generated_at: first, product_count: 0, products: [] });
  runtime.setJson('data/status.json', { generated_at: first, product_count: 0 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });

  const second = 'g2';
  runtime.setJson('data/catalog.json', { generated_at: second, product_count: 1, products: [{ id: 'p2' }] });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  assert.equal(runtime.messages.some(message => message.type === 'generation-ready' && message.generationId === second), false);
  runtime.setJson('data/status.json', { generated_at: second, product_count: 1 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => message.type === 'generation-ready' && message.generationId === second));

  const sourceMessages = [];
  await runtime.dispatch('message', { data: { type: 'activate-generation', generationId: second }, source: { postMessage: message => sourceMessages.push(message) } });
  assert.ok(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === second));
});

test('service worker rejects detail shards from another active generation', async () => {
  const runtime = await createRuntime();
  const generation = 'g1';
  runtime.setJson('data/catalog.json', { generated_at: generation, product_count: 0, products: [] });
  runtime.setJson('data/status.json', { generated_at: generation, product_count: 0 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  const response = await runtime.dispatch('fetch', { request: new Request(`${BASE}data/details/00.json?generation=g2`) });
  assert.equal(response.status, 409);
});

test('navigation uses cached shell for transient HTTP and transport failures', async () => {
  const runtime = await createRuntime();
  await runtime.dispatch('install');

  runtime.setResponse('transient', new Response('cdn unavailable', { status: 503 }));
  const transient = await runtime.dispatch('fetch', { request: navigationRequest('transient') });
  assert.equal(transient.status, 200);
  assert.match(await transient.text(), /index\.html/);

  runtime.setOffline(true);
  const offline = await runtime.dispatch('fetch', { request: navigationRequest('offline') });
  assert.equal(offline.status, 200);
  assert.match(await offline.text(), /index\.html/);
});

test('navigation keeps fresh response when cache persistence fails', async () => {
  const runtime = await createRuntime();
  await runtime.dispatch('install');
  const [appCacheName] = (await runtime.caches.keys()).filter(name => name.startsWith('dropfinder-app-'));
  const appCache = await runtime.caches.open(appCacheName);
  const quota = new Error('quota');
  quota.name = 'QuotaExceededError';
  appCache.failNextPut(quota);

  runtime.setResponse('fresh', new Response('fresh-shell', { status: 200 }));
  const response = await runtime.dispatch('fetch', { request: navigationRequest('fresh') });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'fresh-shell');
  assert.ok(runtime.messages.some(message => message.type === 'cache-quota' && message.resource === 'navigation'));

  appCache.failNextPut(new Error('storage unavailable'));
  runtime.setResponse('fresh-again', new Response('fresh-shell-again', { status: 200 }));
  const second = await runtime.dispatch('fetch', { request: navigationRequest('fresh-again') });
  assert.equal(await second.text(), 'fresh-shell-again');
  assert.ok(runtime.messages.some(message => message.type === 'cache-error' && message.resource === 'navigation'));
});

test('navigation preserves deliberate non-fallback HTTP statuses', async () => {
  const runtime = await createRuntime();
  await runtime.dispatch('install');
  runtime.setResponse('missing', new Response('not found', { status: 404 }));

  const response = await runtime.dispatch('fetch', { request: navigationRequest('missing') });
  assert.equal(response.status, 404);
  assert.equal(await response.text(), 'not found');
});

test('navigation returns concise offline response when network and cache are unavailable', async () => {
  const runtime = await createRuntime();
  runtime.setOffline(true);

  const response = await runtime.dispatch('fetch', { request: navigationRequest('offline') });
  assert.equal(response.status, 503);
  assert.equal(await response.text(), 'Offline');
});

test('explicitly opened same-origin and cross-origin documents reopen offline from the dedicated cache', async () => {
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

test('service worker leaves Vite and source modules to the development server', async () => {
  const runtime = await createRuntime();
  for (const path of [
    '/@vite/client',
    '/@react-refresh',
    '/@id/__x00__virtual:module',
    '/@fs/tmp/source.js',
    '/src/main.tsx',
    '/node_modules/example/index.js?v=one',
  ]) {
    runtime.resetFetches();
    const handled = await runtime.dispatch('fetch', { request: new Request(`${ORIGIN}${path}`) });
    assert.equal(handled, undefined, path);
    assert.deepEqual(runtime.fetches, [], path);
  }
});

test('application cache keeps query-versioned mutable module identities distinct', async () => {
  const runtime = await createRuntime();
  const firstUrl = `${BASE}module.js?v=one`;
  const secondUrl = `${BASE}module.js?v=two`;
  runtime.setResponse(firstUrl, new Response('export default "one"', { headers: { 'content-type': 'text/javascript' } }));
  runtime.setResponse(secondUrl, new Response('export default "two"', { headers: { 'content-type': 'text/javascript' } }));

  const first = await runtime.dispatch('fetch', { request: new Request(firstUrl) });
  assert.equal(await first.text(), 'export default "one"');
  const second = await runtime.dispatch('fetch', { request: new Request(secondUrl) });
  assert.equal(await second.text(), 'export default "two"');

  const appCacheName = (await runtime.caches.keys()).find(name => name.startsWith('dropfinder-app-'));
  assert.ok(appCacheName);
  const appCache = await runtime.caches.open(appCacheName);
  assert.equal(await (await appCache.match(firstUrl)).text(), 'export default "one"');
  assert.equal(await (await appCache.match(secondUrl)).text(), 'export default "two"');
});

function navigationRequest(path) {
  return { method: 'GET', mode: 'navigate', url: new URL(path, BASE).href };
}

function json(value, headers = {}) {
  return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json', ...headers } });
}
