import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
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
    return [...this.entries.keys()].map((url) => new Request(url));
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

function json(value, headers = {}) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

async function createRuntime() {
  const listeners = new Map();
  const messages = [];
  const network = new Map();
  const failures = new Map();
  const fetchCounts = new Map();

  const fetcher = async (input) => {
    const url = new URL(input?.url ?? String(input), BASE).href;
    fetchCounts.set(url, (fetchCounts.get(url) ?? 0) + 1);
    const remainingFailures = failures.get(url) ?? 0;
    if (remainingFailures > 0) {
      failures.set(url, remainingFailures - 1);
      throw new TypeError('transient network failure');
    }
    if (url === `${BASE}app-shell.json`) {
      return json({ schema_version: 'dropfinder-app-shell-v1', assets: ['./index.html'] });
    }
    if (url === `${BASE}index.html`) return new Response('shell');
    return network.get(url)?.clone() ?? new Response('', { status: 404 });
  };

  const caches = new FakeCacheStorage(fetcher);
  const self = {
    location: { origin: ORIGIN },
    clients: {
      claim: async () => {},
      matchAll: async () => [{ postMessage: (message) => messages.push(message) }],
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
    URL,
    DOMException,
    console,
    setTimeout,
    clearTimeout,
  });
  const source = await readFile(new URL('../../cloud_pages/sw.js', import.meta.url), 'utf8');
  vm.runInContext(source, context, { filename: 'cloud_pages/sw.js' });

  async function dispatch(name, data = {}) {
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
    caches,
    messages,
    network,
    dispatch,
    failNext(path, count = 1) {
      failures.set(new URL(path, BASE).href, count);
    },
    fetchCount(path) {
      return fetchCounts.get(new URL(path, BASE).href) ?? 0;
    },
  };
}

test('a failed generation preparation releases ownership and retries without restarting the worker', async () => {
  const runtime = await createRuntime();
  const generationId = 'retry-generation';
  runtime.network.set(new URL('data/catalog-manifest-v4.json', BASE).href, json({
    schema_version: 4,
    generation_id: generationId,
    compact_index: { url: './catalog-index.json' },
  }));
  runtime.network.set(new URL('data/catalog-index.json', BASE).href, json(
    { generation_id: generationId, products: [] },
    { 'x-dropfinder-generation': generationId },
  ));
  runtime.failNext('data/catalog-index.json');

  const first = await runtime.dispatch('fetch', {
    request: new Request(`${BASE}data/catalog-manifest-v4.json`),
  });
  assert.equal(first.status, 503);
  assert.equal(runtime.fetchCount('data/catalog-index.json'), 1);
  assert.equal((await runtime.caches.keys()).includes('dropfinder-data-retry-generation'), false);

  const second = await runtime.dispatch('fetch', {
    request: new Request(`${BASE}data/catalog-manifest-v4.json`),
  });
  assert.equal(second.status, 200);
  assert.equal(runtime.fetchCount('data/catalog-index.json'), 2);
  assert.ok(runtime.messages.some((message) =>
    message.type === 'generation-active' && message.generationId === generationId
  ));
});
