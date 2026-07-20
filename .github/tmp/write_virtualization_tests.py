from pathlib import Path

Path('web/src/features/integration/marketplace-virtualization.test.tsx').write_text('''import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MarketplaceRowProjection } from "../marketplace/marketplace-core";
import { VirtualizedMarketplace } from "./register-marketplace-props";

const variant = { id: "v1", grams: 3.5, sourceWeightLabel: "3.5g", currentPrice: 30, pricePerGram: 30 / 3.5, inStock: true as const, productUrl: "https://example.test/product" };
const row = (id: string, stableIndex: number): MarketplaceRowProjection => ({ product: { id, vendorId: "vendor", vendorName: "Vendor", strainName: `Strain ${id}`, lineage: "hybrid", variants: [variant] }, activeVariant: variant, availableSizeCount: 1, stableIndex });

class FakeVirtualModel {
  replaceCalls: Array<Record<string, unknown>> = [];
  focus = vi.fn(() => 0);
  blur = vi.fn();
  setViewport = vi.fn((scrollTop: number) => { this.scrolledPastFirst = scrollTop > 500; });
  measure = vi.fn(() => false);
  subscribe = vi.fn(() => () => undefined);
  loadedRange = vi.fn(() => ({ startPx: 0, endPx: 2000 }));
  totalHeight = vi.fn(() => 2000);
  scrolledPastFirst = false;
  currentRows = [row("p1", 0), row("p2", 1)];
  replacePages(input: { pages: Array<{ offset: number; rows: Array<{ productId: string; row: MarketplaceRowProjection }> }>; total: number } & Record<string, unknown>) { this.replaceCalls.push(input); this.currentRows = input.pages.flatMap((page) => page.rows.map((entry) => entry.row)); }
  window() { const rows = this.scrolledPastFirst ? this.currentRows.filter((entry) => entry.product.id !== "p1") : this.currentRows; return { items: rows.map((entry) => ({ productId: entry.product.id, row: entry, logicalIndex: entry.stableIndex + 1 })), topSpacer: 0, bottomSpacer: 0, totalCount: this.currentRows.length }; }
}

const props = (model: FakeVirtualModel, queryKey: string, rows = model.currentRows) => ({ model: model as never, rows, pages: [{ offset: 0, rows }], queryKey, total: rows.length, expandedProductId: null, renderRow: (entry: MarketplaceRowProjection) => <button type="button">{entry.product.id}</button>, renderExpanded: () => null });

describe("integrated marketplace virtualization", () => {
  it("resets on semantic query changes and preserves same-query enrichment", () => {
    const model = new FakeVirtualModel();
    const view = render(<VirtualizedMarketplace {...props(model, "query-a")} />);
    const viewport = view.getByLabelText("Marketplace results viewport") as HTMLDivElement;
    expect(model.replaceCalls.at(-1)?.preserveAnchor).toBe(false);
    viewport.scrollTop = 320;
    const enriched = model.currentRows.map((entry) => ({ ...entry, product: { ...entry.product, rating: 4.8, reviewCount: 25 } }));
    view.rerender(<VirtualizedMarketplace {...props(model, "query-a", enriched)} />);
    expect(model.replaceCalls.at(-1)?.preserveAnchor).toBe(true);
    expect(viewport.scrollTop).toBe(320);
    view.rerender(<VirtualizedMarketplace {...props(model, "query-b", enriched)} />);
    expect(model.replaceCalls.at(-1)?.preserveAnchor).toBe(false);
    expect(viewport.scrollTop).toBe(0);
  });

  it("bridges row focus, exposes logical position, and transfers focus before unmount", () => {
    const model = new FakeVirtualModel();
    const view = render(<VirtualizedMarketplace {...props(model, "query-a")} />);
    const viewport = view.getByLabelText("Marketplace results viewport") as HTMLDivElement;
    const firstButton = view.getByRole("button", { name: "p1" });
    const firstRow = firstButton.closest('[role="listitem"]');
    expect(firstRow).toHaveAttribute("aria-posinset", "1");
    expect(firstRow).toHaveAttribute("aria-setsize", "2");
    firstButton.focus();
    expect(model.focus).toHaveBeenCalledWith("p1");
    viewport.scrollTop = 600;
    fireEvent.scroll(viewport);
    expect(model.blur).toHaveBeenCalledWith("p1");
    expect(document.activeElement).toBe(viewport);
  });
});
''', encoding='utf-8')

Path('web/test/virtual-focus-anchor.test.mjs').write_text('''import test from "node:test";
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
''', encoding='utf-8')
