import { describe, expect, it } from "vitest";
// @ts-expect-error The production worker is an intentionally untyped JavaScript module; this test validates its runtime contract.
import { executeQuery } from "../../platform/workers/marketplace-query-engine.js";
import {
  DEFAULT_FILTERS,
  queryMarketplace,
  type MarketplaceFilters,
  type MarketplaceProduct,
  type NumericRange,
} from "./marketplace-core.js";

const variants = [
  { id: "1g", grams: 1, sourceWeightLabel: "1g", currentPrice: 14, pricePerGram: 14, inStock: true as const, productUrl: "https://example.test/1g" },
  { id: "3.5g", grams: 3.5, sourceWeightLabel: "3.5g", currentPrice: 40, pricePerGram: 40 / 3.5, inStock: true as const, productUrl: "https://example.test/3.5g" },
  { id: "7g", grams: 7, sourceWeightLabel: "7g", currentPrice: 75, pricePerGram: 75 / 7, inStock: true as const, productUrl: "https://example.test/7g" },
  { id: "14g", grams: 14, sourceWeightLabel: "14g", currentPrice: 140, pricePerGram: 10, inStock: true as const, productUrl: "https://example.test/14g" },
  { id: "28g", grams: 28, sourceWeightLabel: "28g", currentPrice: 265, pricePerGram: 265 / 28, inStock: true as const, productUrl: "https://example.test/28g" },
];

const product: MarketplaceProduct = {
  id: "white-runtz",
  vendorId: "vendor-1",
  vendorName: "Example Vendor",
  strainName: "White Runtz THCa",
  lineage: "hybrid",
  totalThcDisplay: 27,
  variants,
};

const workerProduct = {
  id: product.id,
  vendorId: product.vendorId,
  vendor: product.vendorName,
  strain: product.strainName,
  lineage: product.lineage,
  totalThc: product.totalThcDisplay,
  image: null,
  detailShard: null,
  variants: variants.map((variant) => ({
    id: variant.id,
    weight: variant.grams,
    price: variant.currentPrice,
    ppg: variant.pricePerGram,
  })),
};

function range(value?: NumericRange): NumericRange {
  return value ?? {};
}

function filters(overrides: Partial<MarketplaceFilters> = {}): MarketplaceFilters {
  return {
    ...DEFAULT_FILTERS,
    ...overrides,
    totalThc: range(overrides.totalThc),
    weight: range(overrides.weight),
    price: range(overrides.price),
    pricePerGram: range(overrides.pricePerGram),
  };
}

function parityCase(overrides: Partial<MarketplaceFilters>) {
  const currentFilters = filters(overrides);
  const sync = queryMarketplace([product], currentFilters, "lowest_price_per_gram");
  const worker = executeQuery([workerProduct], {
    search: currentFilters.search,
    vendors: [...currentFilters.vendorIds],
    lineages: [...currentFilters.lineages],
    minTotalThc: currentFilters.totalThc.min ?? null,
    maxTotalThc: currentFilters.totalThc.max ?? null,
    minWeight: currentFilters.weight.min ?? null,
    maxWeight: currentFilters.weight.max ?? null,
    minPrice: currentFilters.price.min ?? null,
    maxPrice: currentFilters.price.max ?? null,
    minPpg: currentFilters.pricePerGram.min ?? null,
    maxPpg: currentFilters.pricePerGram.max ?? null,
    sort: "lowest_ppg",
    offset: 0,
    limit: 100,
    expandedProductId: null,
  });
  return {
    sync: sync.rows.map((row) => `${row.product.id}:${row.activeVariant.id}`),
    worker: worker.rows.map((row: { productId: string; variantId: string }) => `${row.productId}:${row.variantId}`),
    syncTotal: sync.total,
    workerTotal: worker.total,
  };
}

describe("marketplace active-offer query parity", () => {
  it.each([
    ["unbounded", {}, ["white-runtz:28g"]],
    ["max price excludes the active 28g offer", { price: { max: 50 } }, []],
    ["minimum ppg excludes the active 28g offer", { pricePerGram: { min: 10 } }, []],
    ["maximum ppg retains the active 28g offer", { pricePerGram: { max: 10 } }, ["white-runtz:28g"]],
    ["weight max 7 selects 7g before price evaluation", { weight: { max: 7 }, price: { max: 50 } }, []],
    ["weight max 3.5 selects the passing 3.5g offer", { weight: { max: 3.5 }, price: { max: 50 } }, ["white-runtz:3.5g"]],
    ["combined potency weight price and ppg bounds", {
      totalThc: { min: 25, max: 30 },
      weight: { min: 7, max: 14 },
      price: { min: 100, max: 150 },
      pricePerGram: { min: 9, max: 11 },
    }, ["white-runtz:14g"]],
    ["invalid price range fails closed", { price: { min: 100, max: 50 } }, []],
  ] as const)("matches worker semantics for %s", (_name, overrides, expected) => {
    const result = parityCase(overrides);
    expect(result.sync).toEqual(expected);
    expect(result.worker).toEqual(expected);
    expect(result.worker).toEqual(result.sync);
    expect(result.workerTotal).toBe(result.syncTotal);
  });
});
