import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const ORIGIN = 'https://app.test';
const BASE = `${ORIGIN}/cloud_pages/`;

class FakeCache {
  constructor(fetcher) { this.fetcher = fetcher; this.entries = new Map(); }
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
  async put(input, response) { this.entries.set(this.key(input), response.clone()); }
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
  let offline = false;
  const fetcher = async input => {
    if (offline) throw new TypeError('offline');
    const url = new URL(input?.url ?? String(input), BASE).href;
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
  const context = vm.createContext({ self, caches, fetch: fetcher, Request, Response, Headers, URL, DOMException, console, setTimeout, clearTimeout });
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
    network, caches, messages, dispatch,
    setOffline(value) { offline = value; },
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

test('service worker keeps the active generation until a replacement is complete, then switches atomically', async () => {
  const runtime = await createRuntime();
  const first = 'g1';
  runtime.setJson('data/catalog.json', { generated_at: first, product_count: 0, products: [] });
  runtime.setJson('data/status.json', { generated_at: first, product_count: 0 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === first));

  const second = 'g2';
  runtime.setJson('data/catalog.json', { generated_at: second, product_count: 1, products: [{ id: 'p2' }] });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  assert.equal(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === second), false);

  const statusMessages = [];
  await runtime.dispatch('message', { data: { type: 'generation-status' }, source: { postMessage: message => statusMessages.push(message) } });
  assert.equal(statusMessages.at(-1)?.id, first);

  runtime.setJson('data/status.json', { generated_at: second, product_count: 1 });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => message.type === 'generation-active' && message.generationId === second));

  await runtime.dispatch('message', { data: { type: 'generation-status' }, source: { postMessage: message => statusMessages.push(message) } });
  assert.equal(statusMessages.at(-1)?.id, second);

  runtime.setOffline(true);
  const cached = await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json?offline=1`) });
  assert.equal((await cached.json()).generated_at, second);
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

function json(value, headers = {}) {
  return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json', ...headers } });
}
