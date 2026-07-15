import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { CatalogGenerationClient, MemoryGenerationCache } from '../src/platform/catalog/catalog-generation-client.js';
import { MarketplaceQueryEngine, executeQuery } from '../src/platform/workers/marketplace-query-engine.js';
import { VirtualMarketplaceAdapter } from '../src/platform/virtualization/virtual-marketplace-adapter.js';
import { DocumentViewerCapability, classifyDocument } from '../src/platform/documents/document-viewer-capability.js';
import { PwaGenerationCoordinator } from '../src/platform/pwa/pwa-generation-coordinator.js';
import { registerPlatformCapabilities } from '../src/features/platform/register-platform-capabilities.js';

const sha256 = text => createHash('sha256').update(text).digest('hex');

function fixtureProducts(count = 20) {
  return Array.from({ length: count }, (_, index) => ({
    id: `p${index}`,
    vendor_id: `v${index % 3}`,
    vendor: ['Alpha', 'Beta', 'Gamma'][index % 3],
    strain: `Strain ${String(index).padStart(4, '0')}`,
    lineage: ['indica', 'hybrid', 'sativa'][index % 3],
    total_thc: 15 + (index % 20),
    variants: [
      { id: `p${index}-7`, grams: 7, price: 35 + index, price_per_gram: (35 + index) / 7 },
      { id: `p${index}-14`, grams: 14, price: 55 + index, price_per_gram: (55 + index) / 14 },
    ],
  }));
}

test('catalog client atomically validates generation and deduplicates detail requests', async () => {
  const index = JSON.stringify({ generation_id: 'g1', products: fixtureProducts(2) });
  const detail = JSON.stringify({ generation_id: 'g1', product: { id: 'p0' } });
  const manifest = {
    schema_version: 4, generation_id: 'g1',
    index: { url: 'https://example.test/index.json', bytes: index.length, sha256: sha256(index) },
    details: { p0: { url: 'https://example.test/details/p0.json', bytes: detail.length, sha256: sha256(detail) } },
  };
  const calls = [];
  const fetchImpl = async input => {
    const url = String(input); calls.push(url);
    if (url.endsWith('manifest.json')) return new Response(JSON.stringify(manifest), { headers: { 'content-length': String(JSON.stringify(manifest).length) } });
    if (url.endsWith('index.json')) return new Response(index, { headers: { 'content-length': String(index.length) } });
    if (url.endsWith('p0.json')) { await new Promise(resolve => setTimeout(resolve, 5)); return new Response(detail, { headers: { 'content-length': String(detail.length) } }); }
    return new Response('', { status: 404 });
  };
  const client = new CatalogGenerationClient({ manifestUrl: 'https://example.test/manifest.json', fetchImpl, cache: new MemoryGenerationCache(), maxRetries: 0 });
  const generation = await client.initialize();
  assert.equal(generation.generationId, 'g1');
  const [a, b] = await Promise.all([client.loadDetail('p0'), client.loadDetail('p0')]);
  assert.deepEqual(a, b);
  assert.equal(calls.filter(url => url.endsWith('p0.json')).length, 1);
});

test('catalog client rejects mixed generations and preserves cached complete generation', async () => {
  const cache = new MemoryGenerationCache();
  await cache.putComplete({ generationId: 'cached', manifest: {}, index: { products: [] }, activatedAt: 1, source: 'cache' });
  const fetchImpl = async input => {
    if (String(input).includes('manifest')) return new Response(JSON.stringify({ schema_version: 4, generation_id: 'new', index: { url: 'https://x/index' } }));
    return new Response(JSON.stringify({ generation_id: 'wrong', products: [] }));
  };
  const client = new CatalogGenerationClient({ manifestUrl: 'https://x/manifest', fetchImpl, cache, maxRetries: 0 });
  const result = await client.initialize();
  assert.equal(result.generationId, 'cached');
});

test('query engine chooses active variant by ppg then price, weight, stable id', () => {
  const rows = fixtureProducts(5).map(product => ({
    id: product.id, vendorId: product.vendor_id, vendor: product.vendor, strain: product.strain,
    lineage: product.lineage, totalThc: product.total_thc, image: null, detailShard: null,
    variants: product.variants.map(v => ({ id: v.id, weight: v.grams, price: v.price, ppg: v.price_per_gram })),
  }));
  const result = executeQuery(rows, {
    search: '', vendors: [], lineages: [], minTotalThc: null, maxTotalThc: null,
    minWeight: 7, maxWeight: 14, minPrice: null, maxPrice: null, minPpg: null, maxPpg: null,
    sort: 'lowest_ppg', offset: 0, limit: 100, expandedProductId: 'p1',
  });
  assert.equal(result.rows[0].weight, 14);
  assert.equal(result.expandedProductId, 'p1');
  assert.deepEqual(result.rows.map(row => row.productId), ['p0', 'p1', 'p2', 'p3', 'p4']);
});

test('query engine supersedes rapid synchronous queries', async () => {
  const engine = new MarketplaceQueryEngine({ workerFactory: () => null, syncFallbackLimit: 100 });
  await engine.initialize('g1', fixtureProducts(40));
  const first = engine.query({ search: 'Strain 0001' });
  const second = engine.query({ search: 'Strain 0002' });
  await assert.rejects(first, error => error.name === 'AbortError');
  const result = await second;
  assert.equal(result.rows[0].productId, 'p2');
});

test('virtual adapter keeps DOM window bounded and preserves anchor through measurement', () => {
  const adapter = new VirtualMarketplaceAdapter({ estimatedRowHeight: 100, overscanPx: 100 });
  adapter.replace({ rows: fixtureProducts(1000).map(p => ({ productId: p.id })), total: 50_000, version: 1 });
  adapter.setViewport(20_000, 600);
  const before = adapter.captureAnchor();
  adapter.measure('p10', 300);
  const after = adapter.captureAnchor();
  const window = adapter.window();
  assert.equal(after.key, before.key);
  assert.equal(after.delta, before.delta);
  assert.ok(window.renderedCount < 20, `rendered ${window.renderedCount}`);
  assert.equal(window.ariaRowCount, 50_000);
});

test('virtual adapter deduplicates pages and page requests', async () => {
  const adapter = new VirtualMarketplaceAdapter();
  adapter.replace({ rows: [{ productId: 'p0' }], total: 3, version: 1 });
  let loads = 0;
  const loader = async () => { loads += 1; return { version: 1, rows: [{ productId: 'p1' }, { productId: 'p1' }, { productId: 'p2' }] }; };
  await Promise.all([adapter.requestPage(1, loader), adapter.requestPage(1, loader)]);
  assert.equal(loads, 1);
  assert.equal(adapter.items.length, 3);
});

test('document capability classifies safe viewer paths and bounds PDFs', async () => {
  assert.equal(classifyDocument({ url: 'https://x/lab.pdf' }), 'pdf');
  assert.equal(classifyDocument({ url: 'https://x/report.png' }), 'image');
  assert.equal(classifyDocument({ url: 'javascript:alert(1)' }), 'unsupported');
  const fakePdf = { numPages: 2, destroy: async () => {}, getPage: async () => ({}) };
  const viewer = new DocumentViewerCapability({
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-length': '3' } }),
    loadPdfJs: async () => ({ getDocument: () => ({ promise: Promise.resolve(fakePdf) }) }),
    maxBytes: 4,
  });
  await viewer.open({ url: 'https://x/lab.pdf', mimeType: 'application/pdf' }, { productId: 'p1', variantId: 'v1' });
  assert.equal(viewer.snapshot().status, 'ready');
  assert.equal(viewer.snapshot().pages, 2);
  viewer.goToPage(99);
  assert.equal(viewer.snapshot().page, 2);
  await viewer.close();
  assert.equal(viewer.snapshot().status, 'closed');
});

test('PWA coordinator exposes typed update events without reload loops', async () => {
  const messages = [];
  const listeners = new Map();
  const worker = { postMessage: message => messages.push(message) };
  const registration = { waiting: worker, addEventListener: () => {} };
  const serviceWorker = {
    controller: worker,
    register: async () => registration,
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: () => {},
  };
  const coordinator = new PwaGenerationCoordinator({ navigator: { serviceWorker } });
  const events = [];
  coordinator.subscribe(event => events.push(event));
  await coordinator.register();
  listeners.get('message')({ data: { type: 'generation-ready', generationId: 'g2' } });
  await coordinator.activateReadyGeneration('g2');
  assert.equal(events[0].generationId, 'g2');
  assert.ok(messages.some(message => message.type === 'activate-generation'));
});

test('feature registration exports all five versioned capabilities', () => {
  const registered = new Map();
  const registry = { registerCapability: (name, descriptor) => registered.set(name, descriptor) };
  const capabilities = registerPlatformCapabilities(registry, {
    catalog: { fetchImpl: async () => new Response('{}') },
    query: { workerFactory: () => null },
    documents: { fetchImpl: async () => new Response('') },
    pwa: { navigator: {} },
  });
  assert.equal(Object.keys(capabilities).length, 5);
  assert.deepEqual([...registered.keys()], ['platform.catalog', 'platform.query', 'platform.virtualization', 'platform.documents', 'platform.pwa']);
});
