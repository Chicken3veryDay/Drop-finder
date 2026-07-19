import test from 'node:test';
import assert from 'node:assert/strict';
import { VirtualMarketplaceAdapter } from '../src/platform/virtualization/virtual-marketplace-adapter.js';

function page(offset, size = 120) {
  return {
    offset,
    rows: Array.from({ length: size }, (_, index) => ({
      productId: `product-${offset + index}`,
      row: { stableIndex: offset + index },
    })),
  };
}

test('virtual page window retains real offsets and stable global scroll height', () => {
  const model = new VirtualMarketplaceAdapter({ estimatedRowHeight: 100, maxRetainedPages: 8 });
  const pages = Array.from({ length: 8 }, (_, index) => page(120 * (index + 10)));
  model.replacePages({ pages, total: 50_000, version: 1, queryKey: 'query' });
  const range = model.loadedRange();
  assert.deepEqual(range.pageOffsets, pages.map(item => item.offset));
  assert.equal(range.startOffset, 1_200);
  assert.equal(range.endOffset, 2_160);
  assert.equal(range.startPx, 120_000);
  assert.equal(model.totalHeight(), 5_000_000);
  assert.equal(model.items.length, 960);
});

test('replacing the bounded window preserves a retained viewport anchor', () => {
  const model = new VirtualMarketplaceAdapter({ estimatedRowHeight: 100, maxRetainedPages: 3 });
  model.replacePages({
    pages: [page(0), page(120), page(240)],
    total: 1_000,
    version: 1,
    queryKey: 'query',
  });
  model.setViewport(25_050, 800);
  const anchorBefore = model.captureAnchor();
  assert.equal(anchorBefore?.key, 'product-250');
  model.replacePages({
    pages: [page(120), page(240), page(360)],
    total: 1_000,
    version: 1,
    queryKey: 'query',
    preserveAnchor: true,
  });
  assert.equal(model.captureAnchor()?.key, 'product-250');
  assert.equal(model.viewport.scrollTop, 25_050);
});

test('virtual page window rejects an unbounded retained-page set', () => {
  const model = new VirtualMarketplaceAdapter({ maxRetainedPages: 2 });
  assert.throws(() => model.replacePages({
    pages: [page(0), page(120), page(240)],
    total: 500,
    version: 1,
    queryKey: 'query',
  }), error => error?.code === 'page_window_oversized');
});

test('stale page requests cannot enter a newer virtual query identity', async () => {
  const model = new VirtualMarketplaceAdapter({ maxRetainedPages: 2 });
  model.replacePages({ pages: [page(0)], total: 500, version: 1, queryKey: 'query-a' });
  let release;
  const pending = model.requestPage(120, () => new Promise(resolve => {
    release = () => resolve({ rows: page(120).rows, queryKey: 'query-a' });
  }), 'query-a');
  model.replacePages({ pages: [page(0)], total: 500, version: 2, queryKey: 'query-b' });
  release();
  await pending;
  assert.deepEqual(model.loadedRange().pageOffsets, [0]);
  assert.equal(model.resultVersion, 'query-b');
});
