import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const ORIGIN = 'https://app.test';
const BASE = `${ORIGIN}/cloud_pages/`;

class FakeCache {
  constructor(fetcher) {
    this.fetcher = fetcher;
    this.entries = new Map();
  }

  key(input) {
    return new URL(input?.url ?? String(input), BASE).href.split('#')[0];
  }

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

  async put(input, response) {
    this.entries.set(this.key(input), response.clone());
  }

  async addAll(inputs) {
    for (const input of inputs) {
      const response = await this.fetcher(input);
      if (!response.ok) throw new Error(`addAll HTTP ${response.status}`);
      await this.put(input, response);
    }
  }

  async keys() {
    return [...this.entries.keys()].map(url => new Request(url));
  }

  async delete(input) {
    return this.entries.delete(this.key(input));
  }
}

class FakeCacheStorage {
  constructor(fetcher) {
    this.fetcher = fetcher;
    this.caches = new Map();
  }

  async open(name) {
    if (!this.caches.has(name)) this.caches.set(name, new FakeCache(this.fetcher));
    return this.caches.get(name);
  }

  async keys() {
    return [...this.caches.keys()];
  }

  async delete(name) {
    return this.caches.delete(name);
  }

  async has(name) {
    return this.caches.has(name);
  }

  async match(input, options) {
    for (const cache of this.caches.values()) {
      const hit = await cache.match(input, options);
      if (hit) return hit;
    }
    return undefined;
  }
}

function json(value) {
  return new Response(JSON.stringify(value), {
    headers: { 'content-type': 'application/json' },
  });
}

const sha256Text = value => createHash('sha256').update(value).digest('hex');

async function createRuntime() {
  const listeners = new Map();
  const messages = [];
  const network = new Map();
  const fetcher = async input => {
    const url = new URL(input?.url ?? String(input), BASE).href;
    if (url === `${BASE}app-shell.json`) {
      return json({
        schema_version: 'dropfinder-app-shell-v1',
        assets: ['./', './index.html', './manifest.webmanifest', './icon.svg'],
      });
    }
    if ([BASE, `${BASE}index.html`, `${BASE}manifest.webmanifest`, `${BASE}icon.svg`].includes(url)) {
      return new Response(`asset:${url}`);
    }
    return network.get(url)?.clone() ?? new Response('', { status: 404 });
  };
  const caches = new FakeCacheStorage(fetcher);
  const self = {
    location: { origin: ORIGIN },
    clients: {
      claim: async () => {},
      matchAll: async () => [{ postMessage: message => messages.push(message) }],
    },
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  const context = vm.createContext({
    self,
    caches,
    fetch: fetcher,
    Request,
    Response,
    Headers,
    ReadableStream,
    URL,
    DOMException,
    crypto: webcrypto,
    console,
    setTimeout,
    clearTimeout,
  });
  const source = await readFile(new URL('../../cloud_pages/sw.js', import.meta.url), 'utf8');
  vm.runInContext(source, context, { filename: 'cloud_pages/sw.js' });

  return {
    messages,
    setJson(path, value) {
      network.set(new URL(path, BASE).href, json(value));
    },
    setResponse(path, response) {
      network.set(new URL(path, BASE).href, response);
    },
    async dispatch(name, data = {}) {
      const waits = [];
      let responsePromise;
      const event = {
        ...data,
        waitUntil: promise => waits.push(Promise.resolve(promise)),
        respondWith: promise => { responsePromise = Promise.resolve(promise); },
      };
      listeners.get(name)?.(event);
      await Promise.all(waits);
      return responsePromise;
    },
  };
}

test('prepared generation metadata survives legacy and v4 interleaving', async () => {
  const runtime = await createRuntime();

  const activeLegacy = 'legacy-active';
  runtime.setJson('data/catalog.json', {
    generated_at: activeLegacy,
    product_count: 0,
    products: [],
  });
  runtime.setJson('data/status.json', {
    generated_at: activeLegacy,
    product_count: 0,
  });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => (
    message.type === 'generation-active' && message.generationId === activeLegacy
  )));

  const v4Generation = 'v4-ready';
  const index = JSON.stringify({
    schema_version: 'dropfinder-marketplace-index-v4',
    generation_id: v4Generation,
    product_count: 0,
    in_stock_variant_count: 0,
    products: [],
  });
  runtime.setResponse('data/catalog-v4/index.json', new Response(index, {
    headers: { 'content-type': 'application/json' },
  }));
  runtime.setJson('data/catalog-v4/manifest.json', {
    schema_version: 'dropfinder-catalog-manifest-v4',
    generation_id: v4Generation,
    compact_index: {
      path: 'data/catalog-v4/index.json',
      sha256: sha256Text(index),
    },
    product_detail_shards: [],
  });
  await runtime.dispatch('fetch', {
    request: new Request(`${BASE}data/catalog-v4/manifest.json`),
  });
  assert.ok(runtime.messages.some(message => (
    message.type === 'generation-ready' && message.generationId === v4Generation
  )));

  const laterLegacy = 'legacy-ready';
  runtime.setJson('data/catalog.json', {
    generated_at: laterLegacy,
    product_count: 1,
    products: [{ id: 'later' }],
  });
  runtime.setJson('data/status.json', {
    generated_at: laterLegacy,
    product_count: 1,
  });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/catalog.json`) });
  await runtime.dispatch('fetch', { request: new Request(`${BASE}data/status.json`) });
  assert.ok(runtime.messages.some(message => (
    message.type === 'generation-ready' && message.generationId === laterLegacy
  )));

  const sourceMessages = [];
  await runtime.dispatch('message', {
    data: { type: 'activate-generation', generationId: v4Generation },
    source: { postMessage: message => sourceMessages.push(message) },
  });
  assert.equal(sourceMessages.some(message => message.type === 'generation-error'), false);
  assert.ok(runtime.messages.some(message => (
    message.type === 'generation-active' && message.generationId === v4Generation
  )));
});
