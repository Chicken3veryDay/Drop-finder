import { MarketplaceQueryEngine } from '../../../src/platform/workers/marketplace-query-engine.js';
import { VirtualMarketplaceAdapter } from '../../../src/platform/virtualization/virtual-marketplace-adapter.js';
import { DocumentViewerCapability } from '../../../src/platform/documents/document-viewer-capability.js';
import { PwaGenerationCoordinator } from '../../../src/platform/pwa/pwa-generation-coordinator.js';
import { createSyntheticCatalog } from '../../../src/platform/testing/fixture-factory.js';

const main = document.querySelector('#main');
const viewport = document.querySelector('#viewport');
const feed = document.querySelector('#feed');
const status = document.querySelector('#status');
const search = document.querySelector('#search');
const sort = document.querySelector('#sort');
const weight = document.querySelector('#weight');
const overlay = document.querySelector('#overlay');
const dialog = document.querySelector('#dialog');
const canvas = document.querySelector('#pdf-canvas');
const fallback = document.querySelector('#document-fallback');
const pageStatus = document.querySelector('#page-status');
const products = createSyntheticCatalog(10_000, { seed: 9 });
const engine = new MarketplaceQueryEngine();
const virtual = new VirtualMarketplaceAdapter({ estimatedRowHeight: 96, overscanPx: 260, pageSize: 300, maxRetainedPages: 10 });
const viewer = new DocumentViewerCapability({ maxBytes: 4 * 1024 * 1024, maxPages: 10 });
const pwa = new PwaGenerationCoordinator();
let queryVersion = 0;
let nextOffset = null;
let expandedProductId = null;
let renderingDocument = false;
let lastFocusedDescriptor = null;
const eventLog = [];

await engine.initialize('e2e-generation-1', products);
virtual.subscribe(() => renderRows());
viewer.subscribe(state => { if (state.status === 'closed') overlay.hidden = true; void renderDocument(state); });
pwa.subscribe(event => { eventLog.push(event); status.textContent = `PWA event: ${event.type}`; });
try { await pwa.register('./sw-fixture.js', { scope: './' }); } catch (error) { eventLog.push({ type: 'registration-error', message: error.message }); }

async function runQuery({ preserveAnchor = false, append = false, offset = 0 } = {}) {
  const selectedWeight = weight.value ? Number(weight.value) : null;
  const version = ++queryVersion;
  main.dataset.queryCurrent = 'false';
  try {
    const result = await engine.query({
      search: search.value,
      sort: sort.value,
      minWeight: selectedWeight,
      maxWeight: selectedWeight,
      offset,
      limit: 300,
      expandedProductId,
    });
    if (version !== queryVersion) return;
    nextOffset = result.nextOffset;
    expandedProductId = result.expandedProductId;
    if (append) virtual.appendPage(offset, result.rows, result.queryKey);
    else virtual.replace({ rows: result.rows, total: result.total, version: result.version, queryKey: result.queryKey, preserveAnchor });
    feed.dataset.resultCount = String(result.total);
    main.dataset.queryVersion = String(result.version);
    main.dataset.queryCurrent = 'true';
    status.textContent = `${result.total.toLocaleString()} results`;
  } catch (error) {
    if (error?.name !== 'AbortError') status.textContent = `Query failed: ${error.message}`;
  }
}

function renderRows() {
  const focused = document.activeElement?.closest?.('[data-marketplace-row]');
  if (focused) lastFocusedDescriptor = { key: focused.dataset.productId, action: document.activeElement.dataset.action };
  const windowState = virtual.window();
  feed.replaceChildren();
  feed.style.paddingTop = `${windowState.topSpacer}px`;
  feed.style.paddingBottom = `${windowState.bottomSpacer}px`;
  windowState.items.forEach((row, localIndex) => {
    const expanded = expandedProductId === row.productId;
    const detailsId = `details-${row.productId}`;
    const article = document.createElement('article');
    article.className = 'row';
    article.dataset.marketplaceRow = '';
    article.dataset.productId = row.productId;
    article.dataset.expanded = String(expanded);
    article.setAttribute('aria-posinset', String(windowState.start + localIndex + 1));
    article.setAttribute('aria-setsize', String(windowState.totalCount));
    article.innerHTML = `<div><h2>${escapeHtml(row.strain)}</h2><p>${escapeHtml(row.vendor)} · ${row.lineage}</p></div><div><strong>$${row.price.toFixed(2)}</strong><p>${row.weight} g · $${row.ppg.toFixed(2)}/g · ${row.totalThc?.toFixed(1) ?? '—'}% THC</p></div><div class="actions"><button type="button" data-action="expand" aria-expanded="${expanded}" aria-controls="${detailsId}">${expanded ? 'Collapse' : 'Expand'}</button><button type="button" data-action="document">Open COA</button></div>`;
    const details = document.createElement('div');
    details.className = 'details';
    details.id = detailsId;
    details.hidden = !expanded;
    details.textContent = `Expanded details for ${row.strain}. Variant ${row.variantId}.`;
    article.append(details);
    article.querySelector('[data-action="expand"]').addEventListener('click', event => {
      expandedProductId = expanded ? null : row.productId;
      virtual.measure(row.productId, expanded ? 96 : 220);
      renderRows();
      requestAnimationFrame(() => articleFor(row.productId)?.querySelector('[data-action="expand"]')?.focus());
      event.stopPropagation();
    });
    article.querySelector('[data-action="document"]').addEventListener('click', event => openPdf(row, event.currentTarget));
    feed.append(article);
    requestAnimationFrame(() => virtual.measure(row.productId, article.getBoundingClientRect().height));
  });
  if (lastFocusedDescriptor) requestAnimationFrame(() => articleFor(lastFocusedDescriptor.key)?.querySelector(`[data-action="${lastFocusedDescriptor.action}"]`)?.focus({ preventScroll: true }));
  main.dataset.renderedRows = String(windowState.renderedCount);
}

viewport.addEventListener('scroll', () => {
  virtual.setViewport(viewport.scrollTop, viewport.clientHeight);
  if (nextOffset != null && viewport.scrollTop + viewport.clientHeight > virtual.totalHeight() - 900) {
    const offset = nextOffset; nextOffset = null; void runQuery({ append: true, offset });
  }
}, { passive: true });
new ResizeObserver(() => virtual.setViewport(viewport.scrollTop, viewport.clientHeight)).observe(viewport);
search.addEventListener('input', () => runQuery());
sort.addEventListener('change', () => runQuery());
weight.addEventListener('change', () => runQuery());

async function openPdf(row, invoker) {
  document.querySelector('#document-title').textContent = `${row.strain} COA`;
  document.querySelector('#open-original').href = './sample.pdf';
  const opening = viewer.open({ id: `coa-${row.productId}`, url: './sample.pdf', mimeType: 'application/pdf' }, { productId: row.productId, variantId: row.variantId, invoker });
  overlay.hidden = false;
  dialog.focus();
  await opening;
}
async function renderDocument(state) {
  pageStatus.textContent = state.pages ? `Page ${state.page} of ${state.pages}` : 'Loading document';
  fallback.hidden = true; canvas.hidden = state.type !== 'pdf' || state.status !== 'ready';
  if (state.status === 'error' || state.status === 'unsupported' || state.status === 'external-only') {
    fallback.hidden = false; fallback.textContent = state.error?.message ?? 'Open the original document.'; return;
  }
  if (state.status !== 'ready' || state.type !== 'pdf' || renderingDocument) return;
  renderingDocument = true;
  try { await viewer.renderPage(canvas); }
  finally { renderingDocument = false; }
}
document.querySelector('#close-dialog').addEventListener('click', () => closeDialog());
document.querySelector('#previous-page').addEventListener('click', () => { viewer.goToPage(viewer.snapshot().page - 1); void renderDocument(viewer.snapshot()); });
document.querySelector('#next-page').addEventListener('click', () => { viewer.goToPage(viewer.snapshot().page + 1); void renderDocument(viewer.snapshot()); });
document.querySelector('#zoom-in').addEventListener('click', () => { viewer.zoomIn(); void renderDocument(viewer.snapshot()); });
document.querySelector('#zoom-out').addEventListener('click', () => { viewer.zoomOut(); void renderDocument(viewer.snapshot()); });
document.querySelector('#fit-width').addEventListener('click', () => { viewer.setFitWidth(true); void renderDocument(viewer.snapshot()); });
document.querySelector('#unsupported').addEventListener('click', async event => {
  document.querySelector('#document-title').textContent = 'Unsupported document';
  const opening = viewer.open({ url: './unknown.bin', mimeType: 'application/octet-stream' }, { invoker: event.currentTarget });
  overlay.hidden = false;
  dialog.focus();
  await opening;
});
document.querySelector('#simulate-update').addEventListener('click', () => navigator.serviceWorker.controller?.postMessage({ type: 'simulate-update', generationId: 'e2e-generation-2' }));
document.addEventListener('keydown', event => { if (!overlay.hidden) viewer.handleKeyDown(event, dialog); });
overlay.addEventListener('click', event => { if (event.target === overlay) void closeDialog(); });
async function closeDialog() { overlay.hidden = true; await viewer.close(); }

virtual.setViewport(0, viewport.clientHeight);
await runQuery();
main.dataset.ready = 'true';
window.__platformHarness = {
  engine, virtual, viewer, pwa, eventLog,
  stats: () => ({ renderedRows: Number(main.dataset.renderedRows), queryVersion: Number(main.dataset.queryVersion), total: Number(feed.dataset.resultCount) }),
  serviceWorkerReady: navigator.serviceWorker?.ready,
};

function articleFor(key) { return feed.querySelector(`[data-product-id="${CSS.escape(key)}"]`); }
function escapeHtml(value) { const node = document.createElement('span'); node.textContent = String(value); return node.innerHTML; }
