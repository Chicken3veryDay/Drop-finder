import test from "node:test";
import assert from "node:assert/strict";
import { VirtualMarketplaceAdapter } from "../src/platform/virtualization/virtual-marketplace-adapter.js";

const row = (id, stableIndex) => ({ productId: id, row: { stableIndex } });

test("virtual rows expose logical result positions", () => {
  const adapter = new VirtualMarketplaceAdapter({ estimatedRowHeight: 100 });
  adapter.replacePages({ pages: [{ offset: 120, rows: [row("p120", 120), row("p121", 121)] }], total: 1000, version: 1, queryKey: "q" });
  adapter.setViewport(12000, 300);
  const window = adapter.window();
  assert.equal(window.items[0].logicalIndex, 121);
  assert.equal(window.ariaRowCount, 1000);
});

test("virtual focus lifecycle is explicit", () => {
  const adapter = new VirtualMarketplaceAdapter({ estimatedRowHeight: 100 });
  const events = [];
  adapter.subscribe((snapshot) => events.push(snapshot));
  adapter.replace({ rows: [row("p0", 0), row("p1", 1)], total: 2, version: 1, queryKey: "q" });
  adapter.setViewport(0, 100);
  assert.equal(adapter.focus("p1"), 100);
  assert.equal(events.at(-1).focusedKey, "p1");
  adapter.blur("p1");
  assert.equal(events.at(-1).focusedKey, null);
});
