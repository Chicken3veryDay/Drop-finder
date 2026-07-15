import { performance } from 'node:perf_hooks';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { executeQuery, SORTS } from '../../src/platform/workers/marketplace-query-engine.js';
import { VirtualMarketplaceAdapter } from '../../src/platform/virtualization/virtual-marketplace-adapter.js';
import { CatalogGenerationClient, MemoryGenerationCache } from '../../src/platform/catalog/catalog-generation-client.js';
import { DocumentViewerCapability } from '../../src/platform/documents/document-viewer-capability.js';
import { createSyntheticCatalog } from '../../src/platform/testing/fixture-factory.js';

const sizes = [1_000, 10_000, 50_000];
const budgets = {
  1_000: { queryP95: 100, rapidTyping: 100, sortP95: 100 },
  10_000: { queryP95: 100, rapidTyping: 100, sortP95: 100 },
  50_000: { queryP95: 250, rapidTyping: 250, sortP95: 250 },
};

const baseRequest = Object.freeze({
  search: 'strain 2', vendors: [], lineages: ['hybrid', 'sativa'],
  minTotalThc: 15, maxTotalThc: 38, minWeight: 7, maxWeight: 28,
  minPrice: 20, maxPrice: 180, minPpg: 3, maxPpg: 8,
  sort: 'lowest_ppg', offset: 0, limit: 120, expandedProductId: null,
});

function compact(product) {
  return {
    id: product.id,
    vendorId: product.vendor_id,
    vendor: product.vendor,
    strain: product.strain,
    lineage: product.lineage,
    totalThc: product.total_thc,
    image: product.image,
    detailShard: product.detail_shard,
    variants: product.variants.map(variant => ({ id: variant.id, weight: variant.weight, price: variant.price, ppg: variant.price_per_gram })),
  };
}
function percentile(samples, fraction) {
  const sorted = [...samples].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * fraction))];
}
function measure(fn, iterations = 7, warmups = 3) {
  for (let index = 0; index < warmups; index += 1) fn();
  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const start = performance.now(); fn(); samples.push(performance.now() - start);
  }
  return { p50: percentile(samples, 0.5), p95: percentile(samples, 0.95), max: Math.max(...samples) };
}
function round(value) { return Number(value.toFixed(2)); }

const report = [];
for (const size of sizes) {
  global.gc?.();
  const memoryBefore = process.memoryUsage().heapUsed;
  const fixtureStart = performance.now();
  const products = createSyntheticCatalog(size, { seed: 90_009 });
  const fixtureMs = performance.now() - fixtureStart;
  const compactRows = products.map(compact);
  const memoryAfter = process.memoryUsage().heapUsed;
  const serialized = JSON.stringify({ generation_id: `g-${size}`, products });
  const parse = measure(() => JSON.parse(serialized), 5, 1);
  const query = measure(() => executeQuery(compactRows, baseRequest), 7, 3);
  const rapid = measure(() => {
    for (const search of ['s', 'st', 'str', 'stra', 'strain', 'strain 2']) executeQuery(compactRows, { ...baseRequest, search });
  }, 5, 2);
  const sort = measure(() => {
    for (const sortName of SORTS) executeQuery(compactRows, { ...baseRequest, sort: sortName });
  }, 5, 2);

  const adapter = new VirtualMarketplaceAdapter({ estimatedRowHeight: 176, overscanPx: 420 });
  adapter.replace({ rows: compactRows.slice(0, Math.min(size, 2_000)).map(row => ({ productId: row.id })), total: size, version: 1 });
  const scrollSamples = [];
  let maxRenderedRows = 0;
  for (let position = 0; position <= adapter.totalHeight(); position += 1_500) {
    const start = performance.now();
    adapter.setViewport(position, 900);
    const window = adapter.window();
    scrollSamples.push(performance.now() - start);
    maxRenderedRows = Math.max(maxRenderedRows, window.renderedCount);
  }
  const expansion = measure(() => {
    adapter.measure('p-000010', 360);
    adapter.measure('p-000010', 176);
  }, 15, 2);

  const budget = budgets[size];
  const result = {
    size,
    fixtureMs: round(fixtureMs),
    parseP95: round(parse.p95),
    queryP50: round(query.p50),
    queryP95: round(query.p95),
    rapidTypingP95: round(rapid.p95),
    allSortsP95: round(sort.p95),
    scrollWindowP95: round(percentile(scrollSamples, 0.95)),
    expansionP95: round(expansion.p95),
    maxRenderedRows,
    retainedHeapMiB: round((memoryAfter - memoryBefore) / 1024 / 1024),
  };
  result.passed = result.queryP95 <= budget.queryP95
    && result.rapidTypingP95 <= budget.rapidTyping
    && result.allSortsP95 <= budget.sortP95
    && result.maxRenderedRows <= 20
    && (size !== 10_000 || result.queryP95 <= 50);
  report.push(result);
}

const detail = JSON.stringify({ generation_id: 'detail-g', product: { id: 'p0' } });
const index = JSON.stringify({ generation_id: 'detail-g', products: [] });
const manifest = JSON.stringify({
  schema_version: 4,
  generation_id: 'detail-g',
  index: { url: 'https://bench.invalid/index.json', bytes: index.length, sha256: sha(index) },
  details: { p0: { url: 'https://bench.invalid/details/p0.json', bytes: detail.length, sha256: sha(detail) } },
});
let networkCalls = 0;
const client = new CatalogGenerationClient({
  manifestUrl: 'https://bench.invalid/manifest.json', cache: new MemoryGenerationCache(), maxRetries: 0,
  fetchImpl: async input => {
    networkCalls += 1;
    const url = String(input);
    if (url.endsWith('manifest.json')) return jsonResponse(manifest, url);
    if (url.endsWith('index.json')) return jsonResponse(index, url);
    return jsonResponse(detail, url);
  },
});
const activationStart = performance.now();
await client.initialize();
const activationMs = performance.now() - activationStart;
const detailStart = performance.now();
await client.loadDetail('p0');
const detailFirstMs = performance.now() - detailStart;
const cachedStart = performance.now();
await client.loadDetail('p0');
const detailCachedMs = performance.now() - cachedStart;

const fakePdf = { numPages: 4, destroy: async () => {}, getPage: async () => ({}) };
const viewer = new DocumentViewerCapability({
  fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
  loadPdfJs: async () => ({ getDocument: () => ({ promise: Promise.resolve(fakePdf) }) }),
});
const documentStart = performance.now();
await viewer.open({ url: 'https://bench.invalid/sample.pdf', mimeType: 'application/pdf' });
const documentOpenMs = performance.now() - documentStart;
await viewer.close();

const supplemental = {
  catalogActivationMs: round(activationMs),
  firstDetailMs: round(detailFirstMs),
  cachedDetailMs: round(detailCachedMs),
  networkCalls,
  documentControllerOpenMs: round(documentOpenMs),
  detailCacheHit: networkCalls === 3,
};

console.table(report);
console.log(JSON.stringify({
  environment: {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
    cpuModel: os.cpus()[0]?.model,
    cpuCount: os.cpus().length,
    totalMemoryGiB: round(os.totalmem() / 1024 / 1024 / 1024),
    exposedGc: Boolean(global.gc),
  },
  report,
  supplemental,
}, null, 2));
if (report.some(result => !result.passed) || !supplemental.detailCacheHit) process.exitCode = 1;

function sha(text) { return createHash('sha256').update(text).digest('hex'); }
function jsonResponse(text, url) {
  const response = new Response(text, { headers: { 'content-type': 'application/json', 'content-length': String(text.length) } });
  Object.defineProperty(response, 'url', { value: url });
  return response;
}
