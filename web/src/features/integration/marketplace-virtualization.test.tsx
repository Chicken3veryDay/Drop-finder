import { fireEvent, render } from "@testing-library/react";
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
