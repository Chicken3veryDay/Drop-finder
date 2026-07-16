import { PlatformError, assertGenerationEnvelope, abortError } from '../contracts.js';

const DEFAULTS = Object.freeze({
  manifestUrl: './data/catalog-v4/manifest.json',
  schemaVersion: null,
  staleMs: 5 * 60_000,
  maxRetries: 2,
  maxDetailShards: 64,
  maxIndexBytes: 24 * 1024 * 1024,
  maxDetailBytes: 2 * 1024 * 1024,
});

/**
 * Atomic static-generation loader. It never publishes a generation until the
 * manifest and compact index have both validated against the same generation.
 */
export class CatalogGenerationClient {
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch?.bind(globalThis);
    if (!this.fetchImpl) throw new PlatformError('fetch_unavailable', 'Fetch is unavailable');
    this.cache = options.cache ?? createDefaultGenerationCache(options.cacheName);
    this.active = null;
    this.pending = null;
    this.inflight = new Map();
    this.detailLru = new Map();
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  snapshot() {
    return this.active;
  }

  async initialize({ signal, force = false } = {}) {
    if (!force && this.active && Date.now() - this.active.activatedAt <= this.options.staleMs) return this.active;
    try {
      return await this.refresh({ signal, allowCachedFallback: true });
    } catch (error) {
      if (error?.name === 'AbortError') throw error;
      const cached = await this.cache.getLastComplete();
      throwIfAborted(signal);
      if (cached) {
        this.activate(cached, 'cache-fallback');
        return cached;
      }
      throw error;
    }
  }

  async refresh({ signal, allowCachedFallback = false } = {}) {
    let entry = this.pending;
    if (!entry) {
      const controller = new AbortController();
      entry = createSharedRequest(
        controller,
        this.loadCompleteGeneration(controller.signal),
        {
          onSettled: current => {
            if (this.pending === current) this.pending = null;
          },
          onOrphaned: current => {
            if (this.pending === current) this.pending = null;
          },
        },
      );
      this.pending = entry;
    }

    let generation;
    try {
      generation = await consumeSharedRequest(entry, signal);
    } catch (error) {
      if (allowCachedFallback && error?.name !== 'AbortError') {
        const cached = await this.cache.getLastComplete();
        throwIfAborted(signal);
        if (cached) {
          if (cached.generationId !== this.active?.generationId) this.activate(cached, 'cache-fallback');
          return cached;
        }
      }
      throw error;
    }

    throwIfAborted(signal);
    if (generation.generationId !== this.active?.generationId) {
      await this.cache.putComplete(generation);
      throwIfAborted(signal);
      if (generation.generationId !== this.active?.generationId) this.activate(generation, 'network');
    }
    return generation;
  }

  async loadCompleteGeneration(signal) {
    const manifestResponse = await this.fetchBounded(this.options.manifestUrl, {
      signal,
      maxBytes: 512 * 1024,
      cache: 'no-store',
    });
    const manifest = assertGenerationEnvelope(await manifestResponse.json(), this.options.schemaVersion);
    const manifestUrl = manifestResponse.url || new URL(this.options.manifestUrl, locationHref()).href;
    const publicationBaseUrl = publicationBase(manifestUrl);
    const descriptor = manifest.compact_index ?? manifest.index;
    const indexUrl = resolvePublicationUrl(descriptor.path ?? descriptor.url, manifestUrl, publicationBaseUrl);
    const indexResponse = await this.fetchBounded(indexUrl, {
      signal,
      maxBytes: Math.min(descriptor.bytes ?? this.options.maxIndexBytes, this.options.maxIndexBytes),
      cache: 'no-store',
    });
    const indexText = await indexResponse.text();
    await verifyHash(indexText, descriptor.sha256);
    let index;
    try { index = JSON.parse(indexText); }
    catch (cause) { throw new PlatformError('malformed_index', 'Catalog index is malformed', cause); }
    if (index.generation_id !== manifest.generation_id) {
      throw new PlatformError('generation_mismatch', 'Manifest and index generations do not match');
    }
    if (!Array.isArray(index.products)) {
      throw new PlatformError('invalid_index', 'Catalog index products are missing');
    }
    return Object.freeze({
      generationId: manifest.generation_id,
      manifest,
      index,
      manifestUrl,
      publicationBaseUrl,
      activatedAt: Date.now(),
      source: 'network',
    });
  }

  async loadDetail(productId, { signal, prefetch = false } = {}) {
    throwIfAborted(signal);
    const generation = this.active;
    if (!generation) throw new PlatformError('not_initialized', 'Catalog generation is not initialized');
    const legacy = generation.manifest.details?.[productId] ?? generation.index.detail_shards?.[productId];
    const product = generation.index.products.find(row => String(row.product_id ?? row.id ?? '') === String(productId));
    const shard = Number(product?.detail_shard);
    const shardName = Number.isInteger(shard) ? `${String(shard).padStart(3, '0')}.json` : null;
    const catalog = shardName
      ? generation.manifest.product_detail_shards?.find(row => String(row.path ?? row.url ?? '').endsWith(`/${shardName}`))
      : null;
    const descriptor = legacy ?? catalog;
    if (!descriptor) throw new PlatformError('detail_missing', 'Product details are unavailable');
    const detailUrl = resolvePublicationUrl(
      descriptor.url ?? descriptor.path,
      generation.manifestUrl ?? locationHref(),
      generation.publicationBaseUrl ?? locationHref(),
    );
    const cacheKey = `${generation.generationId}:${detailUrl}`;
    if (this.detailLru.has(cacheKey)) {
      throwIfAborted(signal);
      const hit = this.detailLru.get(cacheKey);
      this.detailLru.delete(cacheKey);
      this.detailLru.set(cacheKey, hit);
      return hit;
    }
    const response = await this.fetchDeduped(cacheKey, detailUrl, {
      signal,
      maxBytes: Math.min(descriptor.bytes ?? this.options.maxDetailBytes, this.options.maxDetailBytes),
      cache: prefetch ? 'force-cache' : 'default',
    });
    throwIfAborted(signal);
    const text = await response.text();
    throwIfAborted(signal);
    await verifyHash(text, descriptor.sha256);
    throwIfAborted(signal);
    let detail;
    try { detail = JSON.parse(text); }
    catch (cause) { throw new PlatformError('malformed_detail', 'Product detail data is malformed', cause); }
    if (detail.generation_id !== generation.generationId) {
      throw new PlatformError('generation_mismatch', 'Detail data belongs to another generation');
    }
    throwIfAborted(signal);
    this.detailLru.set(cacheKey, detail);
    while (this.detailLru.size > this.options.maxDetailShards) {
      this.detailLru.delete(this.detailLru.keys().next().value);
    }
    return detail;
  }

  cancelObsolete(reason = 'Catalog request superseded') {
    const entries = [...this.inflight.values()];
    this.inflight.clear();
    for (const entry of entries) abortSharedRequest(entry, reason, { notifyOrphaned: false });
  }

  activate(generation, source) {
    const previous = this.active;
    this.cancelObsolete('Catalog generation changed');
    this.detailLru.clear();
    this.active = Object.freeze({ ...generation, source });
    for (const listener of this.listeners) listener({ type: 'generation-activated', previous, current: this.active });
  }

  async fetchDeduped(key, input, init) {
    let entry = this.inflight.get(key);
    if (!entry) {
      const controller = new AbortController();
      const requestInit = { ...init };
      delete requestInit.signal;
      entry = createSharedRequest(
        controller,
        this.fetchBounded(input, { ...requestInit, signal: controller.signal }),
        {
          onSettled: current => {
            if (this.inflight.get(key) === current) this.inflight.delete(key);
          },
          onOrphaned: current => {
            if (this.inflight.get(key) === current) this.inflight.delete(key);
          },
        },
      );
      this.inflight.set(key, entry);
    }
    return consumeSharedRequest(entry, init.signal, response => response.clone());
  }

  async fetchBounded(input, { signal, maxBytes, ...init }) {
    if (signal?.aborted) throw abortError();
    let lastError;
    for (let attempt = 0; attempt <= this.options.maxRetries; attempt += 1) {
      try {
        const response = await this.fetchImpl(input, { ...init, signal });
        if (!response.ok) throw new PlatformError('http_error', `Catalog request failed with ${response.status}`);
        const declared = Number(response.headers.get('content-length'));
        if (Number.isFinite(declared) && declared > maxBytes) {
          throw new PlatformError('asset_oversized', 'Catalog asset exceeds its size limit');
        }
        return boundedResponse(response, maxBytes);
      } catch (error) {
        if (signal?.aborted || error?.name === 'AbortError') throw abortError();
        lastError = error;
        if (attempt >= this.options.maxRetries) break;
        await delay(50 * (2 ** attempt), signal);
      }
    }
    throw lastError;
  }
}

export class BrowserGenerationCache {
  constructor(options = {}) {
    this.cacheName = options.cacheName ?? 'dropfinder-client-generation-v1';
    this.key = new URL('/__dropfinder__/last-complete.json', globalThis.location?.origin ?? 'https://dropfinder.invalid').href;
  }
  async getLastComplete() {
    try {
      const cache = await globalThis.caches.open(this.cacheName);
      const response = await cache.match(this.key);
      if (!response) return null;
      const value = await response.json();
      if (!value?.generationId || !value?.manifest || !value?.index) return null;
      return Object.freeze(value);
    } catch { return null; }
  }
  async putComplete(value) {
    const cache = await globalThis.caches.open(this.cacheName);
    await cache.put(this.key, new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }));
  }
}

export function createDefaultGenerationCache(cacheName) {
  return globalThis.caches?.open ? new BrowserGenerationCache({ cacheName }) : new MemoryGenerationCache();
}

export class MemoryGenerationCache {
  constructor() { this.complete = null; }
  async getLastComplete() { return this.complete; }
  async putComplete(value) { this.complete = value; }
}

function createSharedRequest(controller, operation, { onSettled, onOrphaned } = {}) {
  const entry = {
    controller,
    consumers: new Set(),
    settled: false,
    orphaned: false,
    onOrphaned,
    promise: null,
  };
  entry.promise = Promise.resolve(operation).finally(() => {
    entry.settled = true;
    onSettled?.(entry);
  });
  entry.promise.catch(() => undefined);
  return entry;
}

function consumeSharedRequest(entry, signal, project = value => value) {
  if (signal?.aborted) {
    abortSharedIfUnused(entry, signal.reason);
    return Promise.reject(abortError());
  }

  const consumer = {};
  entry.consumers.add(consumer);
  return new Promise((resolve, reject) => {
    let finished = false;
    const finish = () => {
      if (finished) return false;
      finished = true;
      signal?.removeEventListener('abort', onAbort);
      entry.consumers.delete(consumer);
      return true;
    };
    const onAbort = () => {
      if (!finish()) return;
      abortSharedIfUnused(entry, signal?.reason);
      reject(abortError());
    };

    signal?.addEventListener('abort', onAbort, { once: true });
    if (signal?.aborted) {
      onAbort();
      return;
    }

    entry.promise.then(
      value => {
        if (!finish()) return;
        try { resolve(project(value)); }
        catch (error) { reject(error); }
      },
      error => {
        if (!finish()) return;
        reject(error);
      },
    );
  });
}

function abortSharedIfUnused(entry, reason) {
  if (entry.consumers.size === 0) abortSharedRequest(entry, reason);
}

function abortSharedRequest(entry, reason, { notifyOrphaned = true } = {}) {
  if (entry.settled || entry.orphaned) return;
  entry.orphaned = true;
  if (notifyOrphaned) entry.onOrphaned?.(entry);
  entry.controller.abort(reason);
}

function throwIfAborted(signal) {
  if (signal?.aborted) throw abortError();
}

async function boundedResponse(response, maxBytes) {
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maxBytes) throw new PlatformError('asset_oversized', 'Catalog asset exceeds its size limit');
  return new Response(buffer, { status: response.status, statusText: response.statusText, headers: response.headers });
}

async function verifyHash(text, expected) {
  if (!expected || !globalThis.crypto?.subtle) return;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  const actual = [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
  if (actual !== expected.toLowerCase()) throw new PlatformError('hash_mismatch', 'Catalog asset hash validation failed');
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => { clearTimeout(timer); reject(abortError()); }, { once: true });
  });
}

function publicationBase(manifestUrl) {
  try {
    const parsed = new URL(manifestUrl, locationHref());
    const marker = '/data/catalog-v4/';
    const index = parsed.pathname.lastIndexOf(marker);
    if (index >= 0) {
      parsed.pathname = parsed.pathname.slice(0, index + 1);
      parsed.search = '';
      parsed.hash = '';
      return parsed.href;
    }
    return new URL('./', parsed).href;
  } catch {
    return locationHref();
  }
}

function resolvePublicationUrl(value, manifestUrl, publicationBaseUrl) {
  const path = String(value ?? '');
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith('./') || path.startsWith('../')) return new URL(path, manifestUrl).href;
  return new URL(path, publicationBaseUrl).href;
}


function locationHref() {
  return globalThis.location?.href ?? 'https://dropfinder.invalid/';
}
