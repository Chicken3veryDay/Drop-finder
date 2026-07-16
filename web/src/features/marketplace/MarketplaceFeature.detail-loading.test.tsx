import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FlowerMarketplaceFeature } from "./index";
import type {
  MarketplaceAsyncQueryPage,
  MarketplaceProduct,
  MarketplaceProductDetail,
  MarketplaceRowProjection,
} from "./marketplace-core";

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
};

const product: MarketplaceProduct = {
  id: "product-1",
  vendorId: "vendor-1",
  vendorName: "Fixture Vendor",
  strainName: "Blue Dream",
  lineage: "hybrid",
  totalThcDisplay: 24,
  variants: [
    {
      id: "variant-1",
      grams: 3.5,
      sourceWeightLabel: "3.5 g",
      currentPrice: 35,
      pricePerGram: 10,
      inStock: true,
      productUrl: "https://vendor.example/blue-dream",
    },
  ],
};

const row: MarketplaceRowProjection = {
  product,
  activeVariant: product.variants[0]!,
  availableSizeCount: 1,
  stableIndex: 0,
};

const page: MarketplaceAsyncQueryPage = {
  rows: [row],
  total: 1,
  nextOffset: null,
};

describe("FlowerMarketplaceFeature detail loading", () => {
  it("keeps one current-generation request alive across query loading rerenders", async () => {
    const user = userEvent.setup();
    const expandedQuery = deferred<MarketplaceAsyncQueryPage>();
    const detailRequest = deferred<MarketplaceProductDetail>();
    let detailSettled = false;
    let prematureAborts = 0;

    const asyncQueryEngine = {
      query: vi.fn((
        _products,
        _filters,
        _sort,
        options: { expandedProductId: string | null },
      ) => options.expandedProductId ? expandedQuery.promise : Promise.resolve(page)),
    };
    const loadDetail = vi.fn((_productId: string, signal: AbortSignal) => {
      signal.addEventListener("abort", () => {
        if (!detailSettled) prematureAborts += 1;
      }, { once: true });
      return detailRequest.promise;
    });

    render(
      <FlowerMarketplaceFeature
        products={[product]}
        catalogGenerationId="generation-2"
        asyncQueryEngine={asyncQueryEngine}
        loadDetail={loadDetail}
      />,
    );

    const productRow = await screen.findByRole("button", { name: /Blue Dream/i });
    await user.click(productRow);

    await waitFor(() => {
      expect(asyncQueryEngine.query).toHaveBeenCalledTimes(2);
      expect(loadDetail).toHaveBeenCalledTimes(1);
    });

    expect(prematureAborts).toBe(0);

    await act(async () => {
      expandedQuery.resolve(page);
      await expandedQuery.promise;
    });

    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(prematureAborts).toBe(0);

    detailSettled = true;
    await act(async () => {
      detailRequest.resolve({
        productId: product.id,
        effects: ["Calm"],
        growEnvironment: "indoor",
      });
      await detailRequest.promise;
    });

    expect(await screen.findByText("Calm")).toBeInTheDocument();
    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(prematureAborts).toBe(0);
  });
});
