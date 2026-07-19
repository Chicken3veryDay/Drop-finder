from pathlib import Path

path = Path("web/test/platform.test.mjs")
text = path.read_text(encoding="utf-8")
old = """test('virtual adapter evicts old pages from retained rows', () => {
  const adapter = new VirtualMarketplaceAdapter({ maxRetainedPages: 3 });
  adapter.replace({ rows: [{ productId: 'base' }], total: 20, version: 1 });
  adapter.appendPage(1, [{ productId: 'p1' }]);
  adapter.appendPage(2, [{ productId: 'p2' }]);
  adapter.appendPage(3, [{ productId: 'p3' }]);
  assert.equal(adapter.loadedPages.size, 3);
  assert.equal(adapter.items.some(row => row.productId === 'p1'), false);
  assert.deepEqual(adapter.items.map(row => row.productId), ['base', 'p2', 'p3']);
});
"""
new = """test('virtual adapter evicts the retained page farthest from the viewport', () => {
  const adapter = new VirtualMarketplaceAdapter({ maxRetainedPages: 3 });
  adapter.replace({ rows: [{ productId: 'base' }], total: 20, version: 1 });
  adapter.appendPage(1, [{ productId: 'p1' }]);
  adapter.appendPage(2, [{ productId: 'p2' }]);
  adapter.appendPage(3, [{ productId: 'p3' }]);
  assert.equal(adapter.loadedPages.size, 3);
  assert.equal(adapter.items.some(row => row.productId === 'p2'), false);
  assert.deepEqual(adapter.items.map(row => row.productId), ['base', 'p1', 'p3']);
});
"""
if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"legacy virtualization test: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
