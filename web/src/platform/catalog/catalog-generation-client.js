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

const CACHE_RECORD_SCHEMA = 'dropfinder-generation-cache-v2';

/**
 * Atomic static-generation loader. It never publishes a generation until the
 * manifest and compact index have both validated against the same generation.
 */
export class CatalogGenerationClient {
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch?.bind(globalThis);
    if (!this.fetchImpl) throw new PlatformError('fetch_unavailable', 'Fetch is unavailable');
    this.cache = options.cache ?? createDefaultGenerationCache({
      cacheName: options.cacheName,
      cacheStorage: options.cacheStorage,
      deploymentUrl: options.deploymentUrl ?? this.options.manifestUrl,
    });
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
      const cached = await this.cache.getLastComplete();
      if (cached) {
        this.activate(cached, 'cache-fallback');
        return cached;
      }
      throw error;
    }
  }

  async refresh({ signal, allowCachedFallback = false } = {}) {
    if (this.pending) return this.pending;
    const controller = new AbortController();
    const linkedAbort = () => controller.abort(signal?.reason);
    signal?.addEventListener('abort', linkedAbort, { once: true });
    this.pending = this.loadCompleteGeneration(controller.signal)
      .catch(async error => {
        if (allowCachedFallback && error?.name !== 'AbortError') {
          const cached = await this.cache.getLastComplete();
          if (cached) return cached;
        }
        throw error;
      })
      .finally(() => {
        signal?.removeEventListener('abort', linkedAbort);
        this.pending = null;
      });
    const generation = await this.pending;
    if (generation.generationId !== this.active?.generationId) {
      await this.cache.putComplete(generation);
      this.activate(generation, 'network');
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
    const text = await response.text();
    await verifyHash(text, descriptor.sha256);
    let detail;
    try { detail = JSON.parse(text); }
    catch (cause) { throw new PlatformError('malformed_detail', 'Product detail data is malformed', cause); }
    if (detail.generation_id !== generation.generationId) {
      throw new PlatformError('generation_mismatch', 'Detail data belongs to another generation');
    }
    this.detailLru.set(cacheKey, detail);
    while (this.detailLru.size > this.options.maxDetailShards) {
      this.detailLru.delete(this.detailLru.keys().next().value);
    }
    return detail;
  }

  cancelObsolete(reason = 'Catalog request superseded') {
    for (const entry of this.inflight.values()) entry.controller.abort(reason);
    this.inflight.clear();
  }

  activate(generation, source) {
    const previous = this.active;
    this.cancelObsolete('Catalog generation changed');
    this.detailLru.clear();
    this.active = Object.freeze({ ...generation, source });
    for (const listener of this.listeners) listener({ type: 'generation-activated', previous, current: this.active });
  }

  async fetchDeduped(key, input, init) {
    const existing = this.inflight.get(key);
    if (existing) return existing.promise.then(response => response.clone());
    const controller = new AbortController();
    const abort = () => controller.abort(init.signal?.reason);
    init.signal?.addEventListener('abort', abort, { once: true });
    const promise = this.fetchBounded(input, { ...init, signal: controller.signal })
      .finally(() => {
        init.signal?.removeEventListener('abort', abort);
        this.inflight.delete(key);
      });
    this.inflight.set(key, { controller, promise });
    return promise.then(response => response.clone());
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
    this.cacheStorage = options.cacheStorage ?? globalThis.caches;
    this.cacheName = options.cacheName ?? 'dropfinder-client-generation-v2';
    this.deploymentUrl = canonicalDeploymentUrl(options.deploymentUrl ?? locationHref());
    this.deploymentKey = this.deploymentUrl;
    this.key = new URL('./__dropfinder__/last-complete-v2.json', this.deploymentUrl).href;
  }

  owns(value) {
    if (!value?.generationId || !value?.manifest || !value?.index) return false;
    if (!value.publicationBaseUrl) return false;
    return canonicalDeploymentUrl(value.publicationBaseUrl) === this.deploymentKey;
  }

  async getLastComplete() {
    try {
      if (!this.cacheStorage?.open) return null;
      const cache = await this.cacheStorage.open(this.cacheName);
      const response = await cache.match(this.key);
      if (!response) return null;
      const record = await response.json();
      if (record?.schemaVersion !== CACHE_RECORD_SCHEMA) return null;
      if (record.deploymentKey !== this.deploymentKey) return null;
      if (!this.owns(record.generation)) return null;
      return Object.freeze(record.generation);
    } catch { return null; }
  }

  async putComplete(value) {
    if (!this.cacheStorage?.open || !this.owns(value)) return;
    const cache = await this.cacheStorage.open(this.cacheName);
    const record = {
      schemaVersion: CACHE_RECORD_SCHEMA,
      deploymentKey: this.deploymentKey,
      generation: value,
    };
    await cache.put(
      this.key,
      new Response(JSON.stringify(record), { headers: { 'content-type': 'application/json' } }),
    );
  }
}

export function createDefaultGenerationCache(options = {}) {
  return (options.cacheStorage ?? globalThis.caches)?.open
    ? new BrowserGenerationCache(options)
    : new MemoryGenerationCache();
}

export class MemoryGenerationCache {
  constructor() { this.complete = null; }
  async getLastComplete() { return this.complete; }
  async putComplete(value) { this.complete = value; }
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

function canonicalDeploymentUrl(value) {
  const parsed = new URL(publicationBase(value), locationHref());
  parsed.search = '';
  parsed.hash = '';
  return parsed.href;
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
