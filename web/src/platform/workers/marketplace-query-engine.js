import { PlatformError, stableCompare } from '../contracts.js';

export const LINEAGES = Object.freeze(['indica', 'indica_hybrid', 'hybrid', 'sativa_hybrid', 'sativa', 'unknown']);
export const SORTS = Object.freeze([
  'lowest_price', 'highest_price', 'lowest_ppg', 'highest_ppg',
  'highest_total_thc', 'lowest_total_thc', 'strain_az', 'strain_za',
  'vendor_az', 'vendor_za',
]);

const DEFAULTS = Object.freeze({
  syncFallbackLimit: 10_000,
  pageSize: 120,
  maxQueuedRequests: 2,
  maxWorkerRestarts: 1,
});

export function normalizeSearch(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase()
    .replace(/[\p{P}\p{S}]+/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Worker-first deterministic filtering over a compact immutable index. */
export class MarketplaceQueryEngine {
  constructor(options = {}) {
    this.options = { ...DEFAULTS, ...options };
    this.workerFactory = options.workerFactory ?? defaultWorkerFactory;
    this.worker = null;
    this.generationId = null;
    this.rows = [];
    this.requestVersion = 0;
    this.pending = new Map();
    this.initializationWaiters = new Set();
    this.inFlightVersion = null;
    this.queuedWorkerRequest = null;
    this.crashCount = 0;
    this.workerRestarts = 0;
    this.mode = 'uninitialized';
  }

  async initialize(generationId, products) {
    try {
      if (!Array.isArray(products)) throw new PlatformError('invalid_index', 'Products must be an array');
      this.disposeWorker();
      for (const deferred of this.pending.values()) {
        deferred.reject(new DOMException('Superseded by a new catalog generation', 'AbortError'));
      }
      this.pending.clear();
      this.workerRestarts = 0;
      this.generationId = generationId;
      this.rows = products.map(compactProduct);
      try {
        this.worker = this.workerFactory?.();
      } catch {
        this.worker = null;
      }
      if (this.worker) {
        this.attachWorker(this.worker);
      } else {
        this.mode = 'sync';
        if (this.rows.length > this.options.syncFallbackLimit) {
          this.mode = 'failed';
          throw new PlatformError('worker_required', `Worker support is required above ${this.options.syncFallbackLimit} products`);
        }
      }
      this.resolveInitializationWaiters();
    } catch (error) {
      this.rejectInitializationWaiters(error);
      throw error;
    }
  }

  async query(input = {}) {
    if (!this.generationId) await this.waitForInitialization();
    if (!this.generationId) throw new PlatformError('not_initialized', 'Query engine is not initialized');
    if (this.mode === 'failed') {
      throw new PlatformError(
        'worker_unavailable_for_catalog_size',
        `Marketplace search is unavailable above ${this.options.syncFallbackLimit} products without a worker`,
      );
    }
    if (this.mode !== 'sync' && (this.mode !== 'worker' || !this.worker)) {
      throw new PlatformError('worker_unavailable', 'Marketplace search worker is unavailable');
    }

    const request = normalizeQuery(input, this.options.pageSize);
    const version = ++this.requestVersion;
    for (const [oldVersion, deferred] of this.pending) {
      if (oldVersion < version) {
        deferred.reject(new DOMException('Superseded by a newer query', 'AbortError'));
        this.pending.delete(oldVersion);
        if (this.queuedWorkerRequest?.version === oldVersion) this.queuedWorkerRequest = null;
      }
    }
    if (this.mode === 'sync') {
      return queueMicrotaskPromise(() => {
        if (version !== this.requestVersion) throw new DOMException('Superseded by a newer query', 'AbortError');
        return executeQuery(this.rows, request, version, this.generationId);
      });
    }

    return new Promise((resolve, reject) => {
      const deferred = { resolve, reject };
      this.pending.set(version, deferred);
      while (this.pending.size > this.options.maxQueuedRequests) {
        const oldest = this.pending.keys().next().value;
        if (oldest === version) break;
        this.pending.get(oldest)?.reject(new DOMException('Query queue was compacted', 'AbortError'));
        this.pending.delete(oldest);
        if (this.queuedWorkerRequest?.version === oldest) this.queuedWorkerRequest = null;
      }
      const work = { version, request, deferred };
      if (this.inFlightVersion == null) this.dispatchWorkerQuery(work);
      else this.queuedWorkerRequest = work;
    });
  }

  dispatchWorkerQuery(work) {
    const worker = this.worker;
    if (this.mode !== 'worker' || !worker) {
      if (this.pending.get(work.version) === work.deferred) this.pending.delete(work.version);
      work.deferred.reject(new PlatformError('worker_unavailable', 'Marketplace search worker is unavailable'));
      return;
    }
    this.inFlightVersion = work.version;
    try {
      worker.postMessage({
        type: 'query',
        generationId: this.generationId,
        version: work.version,
        request: work.request,
      });
    } catch (error) {
      if (this.inFlightVersion === work.version) this.inFlightVersion = null;
      if (this.pending.get(work.version) === work.deferred) this.pending.delete(work.version);
      work.deferred.reject(new PlatformError(
        'worker_dispatch_failed',
        'Marketplace search worker could not accept the query',
        error,
      ));
      this.dispatchQueuedWorkerQuery();
    }
  }

  dispatchQueuedWorkerQuery() {
    if (this.inFlightVersion != null) return;
    const work = this.queuedWorkerRequest;
    this.queuedWorkerRequest = null;
    if (!work || this.pending.get(work.version) !== work.deferred) return;
    this.dispatchWorkerQuery(work);
  }

  waitForInitialization() {
    if (this.generationId) return Promise.resolve();
    if (this.mode === 'disposed') {
      return Promise.reject(new DOMException('Engine disposed', 'AbortError'));
    }
    return new Promise((resolve, reject) => {
      this.initializationWaiters.add({ resolve, reject });
    });
  }

  resolveInitializationWaiters() {
    for (const waiter of this.initializationWaiters) waiter.resolve();
    this.initializationWaiters.clear();
  }

  rejectInitializationWaiters(error) {
    for (const waiter of this.initializationWaiters) waiter.reject(error);
    this.initializationWaiters.clear();
  }

  handleWorkerMessage(message, worker = this.worker) {
    if (!worker || worker !== this.worker || message?.type !== 'result') return;
    const completedInFlight = message.version === this.inFlightVersion;
    if (completedInFlight) this.inFlightVersion = null;
    const deferred = this.pending.get(message.version);
    if (deferred) {
      this.pending.delete(message.version);
      if (message.generationId !== this.generationId || message.version !== this.requestVersion) {
        deferred.reject(new DOMException('Stale worker response', 'AbortError'));
      } else {
        deferred.resolve(message.result);
      }
    }
    if (completedInFlight) this.dispatchQueuedWorkerQuery();
  }

  handleWorkerCrash(worker = this.worker) {
    if (!worker || worker !== this.worker) return;
    this.crashCount += 1;
    for (const deferred of this.pending.values()) deferred.reject(new PlatformError('worker_crashed', 'Marketplace worker crashed'));
    this.pending.clear();
    this.disposeWorker();
    if (this.workerRestarts < this.options.maxWorkerRestarts) {
      try {
        const replacement = this.workerFactory?.();
        if (replacement) {
          this.workerRestarts += 1;
          this.attachWorker(replacement);
          return;
        }
      } catch {}
    }
    if (this.rows.length <= this.options.syncFallbackLimit) this.mode = 'sync';
    else this.mode = 'failed';
  }

  attachWorker(worker) {
    this.worker = worker;
    this.inFlightVersion = null;
    this.queuedWorkerRequest = null;
    this.mode = 'worker';
    worker.onmessage = event => this.handleWorkerMessage(event.data, worker);
    worker.onerror = () => this.handleWorkerCrash(worker);
    worker.postMessage({ type: 'initialize', generationId: this.generationId, rows: this.rows });
  }

  disposeWorker() {
    const worker = this.worker;
    this.worker = null;
    this.inFlightVersion = null;
    this.queuedWorkerRequest = null;
    if (!worker) return;
    worker.onmessage = null;
    worker.onerror = null;
    worker.terminate?.();
  }

  dispose() {
    this.disposeWorker();
    const disposed = new DOMException('Engine disposed', 'AbortError');
    for (const deferred of this.pending.values()) deferred.reject(disposed);
    this.pending.clear();
    this.rejectInitializationWaiters(disposed);
    this.rows = [];
    this.generationId = null;
    this.mode = 'disposed';
    this.workerRestarts = 0;
  }
}

export function executeQuery(rows, request, version = 0, generationId = 'fixture') {
  const search = normalizeSearch(request.search);
  const vendors = new Set(request.vendors);
  const lineages = new Set(request.lineages);
  const selected = [];
  for (const product of rows) {
    const productSearch = product.searchText ?? normalizeSearch(`${product.vendor}\n${product.strain}`);
    if (search && !productSearch.includes(search)) continue;
    if (vendors.size && !vendors.has(product.vendorId)) continue;
    if (lineages.size && !lineages.has(product.lineage)) continue;
    if (!between(product.totalThc, request.minTotalThc, request.maxTotalThc)) continue;
    const variant = chooseVariant(product.variants, request.minWeight, request.maxWeight);
    if (!variant) continue;
    if (!between(variant.price, request.minPrice, request.maxPrice)) continue;
    if (!between(variant.ppg, request.minPpg, request.maxPpg)) continue;
    selected.push(projectRow(product, variant));
  }
  selected.sort(sorter(request.sort));
  const offset = Math.min(request.offset, selected.length);
  const limit = Math.min(request.limit, 500);
  const page = selected.slice(offset, offset + limit);
  const expandedProductId = request.expandedProductId && selected.some(row => row.productId === request.expandedProductId)
    ? request.expandedProductId : null;
  return Object.freeze({
    generationId,
    version,
    queryKey: queryIdentity(request),
    total: selected.length,
    offset,
    nextOffset: offset + page.length < selected.length ? offset + page.length : null,
    expandedProductId,
    rows: page,
  });
}

function queryIdentity(request) {
  return JSON.stringify({
    search: normalizeSearch(request.search),
    vendors: [...request.vendors].sort(),
    lineages: [...request.lineages].sort(),
    minTotalThc: request.minTotalThc, maxTotalThc: request.maxTotalThc,
    minWeight: request.minWeight, maxWeight: request.maxWeight,
    minPrice: request.minPrice, maxPrice: request.maxPrice,
    minPpg: request.minPpg, maxPpg: request.maxPpg,
    sort: request.sort,
  });
}

function chooseVariant(variants, minWeight, maxWeight) {
  let best = null;
  for (const variant of variants) {
    if (!between(variant.weight, minWeight, maxWeight)) continue;
    if (!best || compareVariant(variant, best) < 0) best = variant;
  }
  return best;
}

function compareVariant(a, b) {
  return numberCompare(a.ppg, b.ppg)
    || numberCompare(a.price, b.price)
    || numberCompare(a.weight, b.weight)
    || stableCompare(a.id, b.id);
}

function sorter(sort) {
  const direction = sort.endsWith('_za') || sort.startsWith('highest_') ? -1 : 1;
  const field = sort.includes('price') && !sort.includes('ppg') ? 'price'
    : sort.includes('ppg') ? 'ppg'
    : sort.includes('total_thc') ? 'totalThc'
    : sort.startsWith('vendor_') ? 'vendor'
    : 'strain';
  return (a, b) => direction * valueCompare(a[field], b[field])
    || stableCompare(a.productId, b.productId)
    || stableCompare(a.variantId, b.variantId);
}

function projectRow(product, variant) {
  return Object.freeze({
    productId: product.id,
    variantId: variant.id,
    vendorId: product.vendorId,
    vendor: product.vendor,
    strain: product.strain,
    lineage: product.lineage,
    totalThc: product.totalThc,
    weight: variant.weight,
    price: variant.price,
    ppg: variant.ppg,
    image: product.image,
    detailShard: product.detailShard,
  });
}

function compactProduct(product) {
  const id = String(product.id ?? product.product_id ?? '');
  if (!id) throw new PlatformError('invalid_product', 'Product is missing an id');
  const variants = (product.variants ?? []).map((variant, index) => {
    const weight = finiteOrNull(variant.weight ?? variant.grams);
    const price = finiteOrNull(variant.price);
    const ppg = finiteOrNull(variant.price_per_gram ?? (weight && price != null ? price / weight : null));
    return Object.freeze({
      id: String(variant.id ?? variant.variant_id ?? `${id}:${index}`),
      weight,
      price,
      ppg,
    });
  }).filter(v => v.weight != null && v.price != null && v.ppg != null);
  const vendor = String(product.vendor ?? product.vendor_name ?? '');
  const strain = String(product.strain ?? product.name ?? '');
  return Object.freeze({
    id,
    vendorId: String(product.vendor_id ?? product.source_id ?? product.vendor ?? ''),
    vendor,
    strain,
    searchText: normalizeSearch(`${vendor}\n${strain}`),
    lineage: LINEAGES.includes(product.lineage) ? product.lineage : 'unknown',
    totalThc: finiteOrNull(product.total_thc ?? product.totalThc),
    image: product.image ?? null,
    detailShard: product.detail_shard ?? null,
    variants,
  });
}

function normalizeQuery(input, defaultLimit) {
  const sort = SORTS.includes(input.sort) ? input.sort : 'lowest_ppg';
  const lineages = Array.isArray(input.lineages) ? input.lineages.filter(value => LINEAGES.includes(value)) : [];
  return Object.freeze({
    search: String(input.search ?? '').trim(),
    vendors: Array.isArray(input.vendors) ? input.vendors.map(String) : [],
    lineages,
    minTotalThc: finiteOrNull(input.minTotalThc), maxTotalThc: finiteOrNull(input.maxTotalThc),
    minWeight: finiteOrNull(input.minWeight), maxWeight: finiteOrNull(input.maxWeight),
    minPrice: finiteOrNull(input.minPrice), maxPrice: finiteOrNull(input.maxPrice),
    minPpg: finiteOrNull(input.minPpg), maxPpg: finiteOrNull(input.maxPpg),
    sort,
    offset: Math.max(0, Number.parseInt(input.offset ?? 0, 10) || 0),
    limit: Math.max(1, Number.parseInt(input.limit ?? defaultLimit, 10) || defaultLimit),
    expandedProductId: input.expandedProductId ? String(input.expandedProductId) : null,
  });
}

function between(value, min, max) {
  if (value == null) return min == null && max == null;
  return (min == null || value >= min) && (max == null || value <= max);
}
function finiteOrNull(value) {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function numberCompare(a, b) { return (a ?? Number.POSITIVE_INFINITY) - (b ?? Number.POSITIVE_INFINITY); }
function valueCompare(a, b) { return typeof a === 'number' || typeof b === 'number' ? numberCompare(a, b) : stableCompare(String(a), String(b)); }
function queueMicrotaskPromise(fn) { return new Promise((resolve, reject) => queueMicrotask(() => { try { resolve(fn()); } catch (error) { reject(error); } })); }

function defaultWorkerFactory() {
  if (typeof Worker === 'undefined') return null;
  return new Worker(new URL('./marketplace-query-worker.js', import.meta.url), { type: 'module', name: 'dropfinder-query' });
}
