import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketplaceFeature } from "./MarketplaceFeature.js";
import type {
  MarketplaceAsyncQueryCapability,
  MarketplaceProduct,
  MarketplaceQueryCapability,
  MarketplaceRowProjection,
} from "./marketplace-core.js";

const product: MarketplaceProduct = {
  id: "product-1",
  vendorId: "vendor-1",
  vendorName: "Example Vendor",
  strainName: "Blue Example",
  lineage: "hybrid",
  totalThcDisplay: 24.5,
  variants: [
    {
      id: "variant-1",
      grams: 3.5,
      sourceWeightLabel: "3.5 g",
      currentPrice: 30,
      pricePerGram: 30 / 3.5,
      inStock: true,
      productUrl: "https://example.test/products/blue-example",
    },
  ],
};

const row: MarketplaceRowProjection = {
  product,
  activeVariant: product.variants[0]!,
  availableSizeCount: 1,
  stableIndex: 0,
};

describe("MarketplaceFeature query execution", () => {
  it("does not execute the synchronous fallback while the async engine is active", async () => {
    const synchronousQuery = vi.fn<MarketplaceQueryCapability["query"]>(() => ({
      rows: [row],
      total: 1,
    }));
    const asynchronousQuery = vi.fn<MarketplaceAsyncQueryCapability["query"]>(async (
      _products,
      _filters,
      _sort,
      options,
    ) => ({
      queryKey: options.queryKey,
      offset: options.offset,
      rows: [row],
      total: 1,
      nextOffset: null,
    }));
    const user = userEvent.setup();

    render(
      <MarketplaceFeature
        products={[product]}
        queryEngine={{ query: synchronousQuery }}
        asyncQueryEngine={{ query: asynchronousQuery }}
      />,
    );

    expect(await screen.findByRole("list", { name: "1 marketplace results" })).toBeInTheDocument();
    expect(synchronousQuery).not.toHaveBeenCalled();
    expect(asynchronousQuery).toHaveBeenCalledTimes(1);

    await user.type(screen.getByRole("searchbox", { name: "Search vendor or strain" }), "blue");
    await waitFor(() => {
      expect(asynchronousQuery.mock.calls.at(-1)?.[1].search).toBe("blue");
    });
    expect(synchronousQuery).not.toHaveBeenCalled();
  });

  it("does not restart page zero when only detail-enrichment fields change", async () => {
    const asynchronousQuery = vi.fn<MarketplaceAsyncQueryCapability["query"]>(async (
      products,
      _filters,
      _sort,
      options,
    ) => ({
      queryKey: options.queryKey,
      offset: options.offset,
      rows: [{
        ...row,
        product: products[0]!,
        activeVariant: products[0]!.variants[0]!,
      }],
      total: 1,
      nextOffset: null,
    }));
    const asyncEngine: MarketplaceAsyncQueryCapability = { query: asynchronousQuery };
    const view = render(
      <MarketplaceFeature
        products={[product]}
        asyncQueryEngine={asyncEngine}
      />,
    );

    expect(await screen.findByRole("list", { name: "1 marketplace results" })).toBeInTheDocument();
    expect(asynchronousQuery).toHaveBeenCalledTimes(1);

    const enrichedProduct: MarketplaceProduct = {
      ...product,
      vendorFaviconUrl: "https://example.test/favicon.png",
      variants: [{
        ...product.variants[0]!,
        imageUrl: "https://example.test/blue-example.jpg",
      }],
    };
    view.rerender(
      <MarketplaceFeature
        products={[enrichedProduct]}
        asyncQueryEngine={asyncEngine}
      />,
    );

    await waitFor(() => expect(asynchronousQuery).toHaveBeenCalledTimes(1));
  });

  it("retains the synchronous query fallback when no async engine is available", () => {
    const synchronousQuery = vi.fn<MarketplaceQueryCapability["query"]>(() => ({
      rows: [row],
      total: 1,
    }));

    render(
      <MarketplaceFeature
        products={[product]}
        queryEngine={{ query: synchronousQuery }}
      />,
    );

    expect(synchronousQuery).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("list", { name: "1 marketplace results" })).toBeInTheDocument();
  });
});
