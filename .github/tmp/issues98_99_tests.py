from pathlib import Path

Path("web/test/virtual-query-focus-policy.test.mjs").write_text(r'''import test from 'node:test';
import assert from 'node:assert/strict';
import { VirtualMarketplaceAdapter } from '../src/platform/virtualization/virtual-marketplace-adapter.js';

function page(order) {
  return order.map((productId, stableIndex) => ({ productId, row: { stableIndex } }));
}

const ids = Array.from({ length: 100 }, (_, index) => `p${index}`);

test('semantic query replacement resets a stale anchor while same-query enrichment preserves it', () => {
  const model = new VirtualMarketplaceAdapter({ estimatedRowHeight: 176, overscanPx: 420 });
  model.replacePages({ pages: [{ offset: 0, rows: page(ids) }], total: 100, version: 1, queryKey: 'ascending' });
  model.setViewport(50 * 176, 600);

  const enriched = page(ids).map((row) => ({ ...row, row: { ...row.row, enriched: true } }));
  const preserved = model.replacePages({
    pages: [{ offset: 0, rows: enriched }],
    total: 100,
    version: 2,
    queryKey: 'ascending',
    preserveAnchor: true,
  });
  assert.ok(preserved > 8_000, preserved);

  const reset = model.replacePages({
    pages: [{ offset: 0, rows: page([...ids].reverse()) }],
    total: 100,
    version: 3,
    queryKey: 'descending',
    preserveAnchor: false,
  });
  assert.equal(reset, 0);
  assert.equal(model.viewport.scrollTop, 0);
  assert.equal(model.window().items[0].productId, 'p99');
});

test('focused rows clamp the viewport until focus leaves without expanding the window', () => {
  const model = new VirtualMarketplaceAdapter({ estimatedRowHeight: 176, overscanPx: 420 });
  model.replacePages({ pages: [{ offset: 0, rows: page(ids) }], total: 100, version: 1, queryKey: 'all' });
  model.setViewport(0, 600);

  const pinnedScrollTop = model.focus('p3');
  assert.equal(typeof pinnedScrollTop, 'number');
  assert.equal(model.setViewport(2_000, 600), pinnedScrollTop);
  assert.ok(model.window().items.some((item) => item.productId === 'p3'));
  assert.ok(model.window().renderedCount < 20);

  assert.equal(model.blur('p3'), true);
  assert.equal(model.setViewport(2_000, 600), 2_000);
  assert.ok(!model.window().items.some((item) => item.productId === 'p3'));
});

test('replacing results clears a focused key that no longer exists', () => {
  const model = new VirtualMarketplaceAdapter();
  model.replacePages({ pages: [{ offset: 0, rows: page(ids.slice(0, 10)) }], total: 10, version: 1, queryKey: 'all' });
  model.setViewport(0, 600);
  model.focus('p3');
  assert.equal(model.focusedKey, 'p3');

  model.replacePages({
    pages: [{ offset: 0, rows: page(ids.slice(4, 10)) }],
    total: 6,
    version: 2,
    queryKey: 'filtered',
    preserveAnchor: false,
  });
  assert.equal(model.focusedKey, null);
});
''', encoding="utf-8")

Path("web/src/features/integration/virtual-marketplace-focus.test.tsx").write_text(r'''import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VirtualMarketplaceAdapter } from "../../platform/virtualization/virtual-marketplace-adapter.js";
import type { MarketplaceRowProjection } from "../marketplace/marketplace-core";
import { VirtualizedMarketplace } from "./register-marketplace-props";

const originalResizeObserver = globalThis.ResizeObserver;
const originalRect = HTMLElement.prototype.getBoundingClientRect;
const clientHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");

function rows(count = 30): MarketplaceRowProjection[] {
  return Array.from({ length: count }, (_, index) => {
    const variant = {
      id: `v${index}`,
      grams: 7,
      sourceWeightLabel: "7g",
      currentPrice: 35,
      pricePerGram: 5,
      inStock: true as const,
      productUrl: `https://example.test/p${index}`,
    };
    return {
      product: {
        id: `p${index}`,
        vendorId: "vendor",
        vendorName: "Vendor",
        strainName: `Product ${index}`,
        lineage: "hybrid",
        variants: [variant],
      },
      activeVariant: variant,
      availableSizeCount: 1,
      stableIndex: index,
    };
  });
}

beforeEach(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  } as unknown as typeof ResizeObserver;
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 });
  HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
    x: 0, y: 0, width: 800, height: 176, top: 0, right: 800, bottom: 176, left: 0,
    toJSON: () => ({}),
  }));
});

afterEach(() => {
  globalThis.ResizeObserver = originalResizeObserver;
  HTMLElement.prototype.getBoundingClientRect = originalRect;
  if (clientHeight) Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeight);
});

describe("virtual marketplace semantic scroll and focus policy", () => {
  it("resets DOM scroll for a new query and preserves it for same-query enrichment", () => {
    const model = new VirtualMarketplaceAdapter();
    const original = rows();
    const props = {
      model,
      rows: original,
      total: original.length,
      renderRow: (row: MarketplaceRowProjection) => <button>{row.product.id}</button>,
    };
    const view = render(<VirtualizedMarketplace {...props} queryKey="ascending" />);
    view.rerender(<VirtualizedMarketplace {...props} queryKey="ascending" />);
    const viewport = screen.getByRole("list", { name: "Marketplace results" });
    viewport.scrollTop = 1_500;
    fireEvent.scroll(viewport);

    const enriched = original.map((row) => ({ ...row, product: { ...row.product, totalThcDisplay: 20 } }));
    view.rerender(<VirtualizedMarketplace {...props} rows={enriched} queryKey="ascending" />);
    expect(viewport.scrollTop).toBeGreaterThan(0);

    view.rerender(<VirtualizedMarketplace {...props} rows={[...original].reverse().map((row, stableIndex) => ({ ...row, stableIndex }))} queryKey="descending" />);
    expect(viewport.scrollTop).toBe(0);
  });

  it("keeps a focused row mounted and restores focus to the list when filtering removes it", () => {
    const model = new VirtualMarketplaceAdapter();
    const original = rows();
    const props = {
      model,
      rows: original,
      total: original.length,
      renderRow: (row: MarketplaceRowProjection) => <button>{row.product.id}</button>,
    };
    const view = render(<VirtualizedMarketplace {...props} queryKey="all" />);
    view.rerender(<VirtualizedMarketplace {...props} queryKey="all" />);
    const viewport = screen.getByRole("list", { name: "Marketplace results" });
    const focused = screen.getByRole("button", { name: "p3" });
    focused.focus();
    expect(document.activeElement).toBe(focused);
    const pinnedScrollTop = viewport.scrollTop;

    viewport.scrollTop = 2_000;
    fireEvent.scroll(viewport);
    expect(viewport.scrollTop).toBe(pinnedScrollTop);
    expect(document.activeElement).toBe(focused);

    const filtered = original.filter((row) => row.product.id !== "p3").map((row, stableIndex) => ({ ...row, stableIndex }));
    view.rerender(<VirtualizedMarketplace {...props} rows={filtered} total={filtered.length} queryKey="without-p3" />);
    expect(document.activeElement).toBe(viewport);
  });
});
''', encoding="utf-8")
