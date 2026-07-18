import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

const ORIGIN = 'https://app.test';

class FakeCache {
  constructor(fetcher, base) {
    this.fetcher = fetcher;
    this.base = base;
    this.entries = new Map();
  }
  key(input) { return new URL(input?.url ?? String(input), this.base).href.split('#')[0]; }
  async match(input, options = {}) {
    const key = this.key(input);
    if (!options.ignoreSearch) return this.entries.get(key)?.clone();
    const target = new URL(key);
    target.search = '';
    for (const [candidate, response] of this.entries) {
      const url = new URL(candidate);
      url.search = '';
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
  async keys() { return [...this.entries.keys()].map((url) => new Request(url)); }
  async delete(input) { return this.entries.delete(this.key(input)); }
}

class FakeCacheStorage {
  constructor() {
    this.caches = new Map();
    this.fetcher = async () => new Response('', { status: 404 });
    this.base = `${ORIGIN}/`;
  }
  setRuntime(fetcher, base) {
    this.fetcher = fetcher;
    this.base = base;
  }
  async open(name) {
    if (!this.caches.has(name)) this.caches.set(name, new FakeCache(this.fetcher, this.base));
    return this.caches.get(name);
  }
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

function json(value, headers = {}) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

async function createRuntime({ base, cacheStorage }) {
  const listeners = new Map();
  const messages = [];
  const network = new Map();
  let offline = false;
  const fetcher = async (input) => {
    if (offline) throw new TypeError('offline');
    const url = new URL(input?.url ?? String(input), base).href;
    if (url === `${base}app-shell.json`) {
      return json({ schema_version: 'dropfinder-app-shell-v1', assets: ['./', './index.html'] });
    }
    if (url === base || url === `${base}index.html`) return new Response(`asset:${url}`);
    return network.get(url)?.clone() ?? new Response('', { status: 404 });
  };
  cacheStorage.setRuntime(fetcher, base);
  const self = {
    location: { origin: new URL(base).origin, href: `${base}sw.js` },
    registration: { scope: base },
    clients: {
      claim: async () => {},
      matchAll: async () => [{ postMessage: (message) => messages.push(message) }],
    },
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  const context = vm.createContext({
    self,
    caches: cacheStorage,
    fetch: fetcher,
    Request,
    Response,
    Headers,
    URL,
    DOMException,
    console,
    setTimeout,
    clearTimeout,
  });
  const source = await readFile(new URL('../../cloud_pages/sw.js', import.meta.url), 'utf8');
  vm.runInContext(source, context, { filename: 'cloud_pages/sw.js' });

  async function dispatch(name, data = {}) {
    cacheStorage.setRuntime(fetcher, base);
    const waits = [];
    let responsePromise;
    const event = {
      ...data,
      waitUntil: (promise) => waits.push(Promise.resolve(promise)),
      respondWith: (promise) => { responsePromise = Promise.resolve(promise); },
    };
    listeners.get(name)?.(event);
    await Promise.all(waits);
    return responsePromise;
  }

  return {
    base,
    messages,
    dispatch,
    setOffline(value) { offline = value; },
    setJson(path, value, headers = {}) {
      network.set(new URL(path, base).href, json(value, headers));
    },
  };
}

async function activateLegacy(runtime, generation, productId) {
  const products = productId ? [{ id: productId }] : [];
  runtime.setJson('data/catalog.json', {
    generated_at: generation,
    product_count: products.length,
    products,
  });
  runtime.setJson('data/status.json', {
    generated_at: generation,
    product_count: products.length,
  });
  await runtime.dispatch('fetch', { request: new Request(`${runtime.base}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${runtime.base}data/status.json`) });
}

test('same-origin deployment workers retain separate shell, metadata, and generation caches', async () => {
  const cacheStorage = new FakeCacheStorage();
  const main = await createRuntime({
    base: `${ORIGIN}/Chicken3veryDay/Drop-finder/main/`,
    cacheStorage,
  });
  await main.dispatch('install');
  await activateLegacy(main, 'main-generation', 'main-product');

  const production = await createRuntime({
    base: `${ORIGIN}/Chicken3veryDay/Drop-finder/gh-pages/`,
    cacheStorage,
  });
  await production.dispatch('install');
  await activateLegacy(production, 'production-generation', 'production-product');
  await main.dispatch('activate');
  await production.dispatch('activate');

  const names = await cacheStorage.keys();
  assert.equal(names.filter((name) => name.startsWith('dropfinder-app-')).length, 2);
  assert.equal(names.filter((name) => name.startsWith('dropfinder-generation-meta-v2-')).length, 2);
  assert.equal(names.filter((name) => name.startsWith('dropfinder-data-v2-')).length, 2);

  main.setOffline(true);
  production.setOffline(true);
  const mainFallback = await main.dispatch('fetch', {
    request: new Request(`${main.base}data/catalog.json?offline=1`),
  });
  const productionFallback = await production.dispatch('fetch', {
    request: new Request(`${production.base}data/catalog.json?offline=1`),
  });
  assert.equal((await mainFallback.json()).products[0].id, 'main-product');
  assert.equal((await productionFallback.json()).products[0].id, 'production-product');
});

test('missing owned generation cache invalidates active metadata on worker restart', async () => {
  const cacheStorage = new FakeCacheStorage();
  const base = `${ORIGIN}/Chicken3veryDay/Drop-finder/gh-pages/`;
  const runtime = await createRuntime({ base, cacheStorage });
  await activateLegacy(runtime, 'g1', 'p1');
  const generationCache = (await cacheStorage.keys()).find((name) => name.startsWith('dropfinder-data-v2-'));
  assert.ok(generationCache);
  await cacheStorage.delete(generationCache);

  const restarted = await createRuntime({ base, cacheStorage });
  const status = [];
  await restarted.dispatch('message', {
    data: { type: 'generation-status' },
    source: { postMessage: (message) => status.push(message) },
  });

  assert.equal(status.length, 1);
  assert.equal(status[0].type, 'generation-status');
  assert.equal('generationId' in status[0], false);
});
