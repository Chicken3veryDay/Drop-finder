import assert from "node:assert/strict";
import { it as test } from "vitest";
import { DEFAULT_FILTERS, type MarketplaceAsyncQueryPage, type MarketplaceRowProjection } from "../marketplace-core.js";
import {
  MARKETPLACE_MAX_RETAINED_PAGES,
  MARKETPLACE_PAGE_SIZE,
  acceptMarketplacePageZero,
  acceptMarketplaceRetainedPage,
  emptyMarketplacePageWindow,
  marketplaceQueryIdentity,
  marketplaceRetainedBaseOffset,
  marketplaceRetainedRows,
  nextMarketplacePageOffset,
  previousMarketplacePageOffset,
} from "../marketplace-pagination.js";
import { marketplaceFixtures } from "./fixtures.js";

function row(index: number): MarketplaceRowProjection {
  const source = marketplaceFixtures[index % marketplaceFixtures.length]!;
  const product = {
    ...source,
    id: `product-${index}`,
    variants: source.variants.map((variant, variantIndex) => ({
      ...variant,
      id: `product-${index}-variant-${variantIndex}`,
      productUrl: `https://example.test/product-${index}`,
    })),
  };
  return {
    product,
    activeVariant: product.variants[0]!,
    availableSizeCount: product.variants.length,
    stableIndex: index,
  };
}

function page(queryKey: string, offset: number, total = 2_000): MarketplaceAsyncQueryPage {
  const rows = Array.from({ length: MARKETPLACE_PAGE_SIZE }, (_, index) => row(offset + index));
  return {
    queryKey,
    offset,
    rows,
    total,
    nextOffset: offset + rows.length < total ? offset + rows.length : null,
  };
}

const filters = (patch = {}) => ({
  ...DEFAULT_FILTERS,
  ...patch,
  totalThc: {},
  weight: {},
  price: {},
  pricePerGram: {},
});

test("query identity includes generation, product index, filters, and sort", () => {
  const base = {
    catalogGenerationId: "generation-a",
    productType: "cannabis_flower",
    products: marketplaceFixtures,
    filters: filters(),
    sort: "lowest_price_per_gram" as const,
  };
  const identity = marketplaceQueryIdentity(base);
  assert.notEqual(identity, marketplaceQueryIdentity({ ...base, catalogGenerationId: "generation-b" }));
  assert.notEqual(identity, marketplaceQueryIdentity({ ...base, filters: filters({ search: "blue dream" }) }));
  assert.notEqual(identity, marketplaceQueryIdentity({ ...base, sort: "highest_price" }));
  assert.notEqual(identity, marketplaceQueryIdentity({ ...base, products: marketplaceFixtures.slice(1) }));
});

test("new query identity starts empty and accepts only its page zero", () => {
  const oldState = acceptMarketplacePageZero(emptyMarketplacePageWindow("old"), page("old", 0));
  assert.equal(oldState.pages.length, 1);
  const replacement = emptyMarketplacePageWindow("new");
  assert.equal(replacement.pages.length, 0);
  assert.equal(replacement.total, 0);
  assert.equal(replacement.pageZeroAccepted, false);
  assert.equal(acceptMarketplacePageZero(replacement, page("old", 0)), replacement);
  const accepted = acceptMarketplacePageZero(replacement, page("new", 0));
  assert.equal(accepted.pageZeroAccepted, true);
  assert.equal(accepted.pages[0]?.offset, 0);
});

test("stale identity and stale offset pages cannot append", () => {
  const initial = acceptMarketplacePageZero(emptyMarketplacePageWindow("query"), page("query", 0));
  assert.equal(acceptMarketplaceRetainedPage(initial, page("stale", 120), "forward"), initial);
  assert.equal(acceptMarketplaceRetainedPage(initial, page("query", 240), "forward"), initial);
  const next = acceptMarketplaceRetainedPage(initial, page("query", 120), "forward");
  assert.notEqual(next, initial);
  assert.equal(acceptMarketplaceRetainedPage(next, page("query", 120), "forward"), next);
});

test("forward loading retains a bounded contiguous page window", () => {
  let state = acceptMarketplacePageZero(emptyMarketplacePageWindow("query"), page("query", 0));
  for (let offset = MARKETPLACE_PAGE_SIZE; offset < MARKETPLACE_PAGE_SIZE * 12; offset += MARKETPLACE_PAGE_SIZE) {
    state = acceptMarketplaceRetainedPage(state, page("query", offset), "forward");
  }
  assert.equal(state.pages.length, MARKETPLACE_MAX_RETAINED_PAGES);
  assert.equal(marketplaceRetainedBaseOffset(state), MARKETPLACE_PAGE_SIZE * 4);
  assert.equal(state.pages.at(-1)?.offset, MARKETPLACE_PAGE_SIZE * 11);
  assert.equal(marketplaceRetainedRows(state).length, MARKETPLACE_PAGE_SIZE * MARKETPLACE_MAX_RETAINED_PAGES);
  assert.equal(nextMarketplacePageOffset(state), MARKETPLACE_PAGE_SIZE * 12);
});

test("backward navigation refetches an evicted page and evicts the far edge", () => {
  let state = acceptMarketplacePageZero(emptyMarketplacePageWindow("query"), page("query", 0));
  for (let offset = MARKETPLACE_PAGE_SIZE; offset < MARKETPLACE_PAGE_SIZE * 10; offset += MARKETPLACE_PAGE_SIZE) {
    state = acceptMarketplaceRetainedPage(state, page("query", offset), "forward");
  }
  const previous = previousMarketplacePageOffset(state);
  assert.equal(previous, MARKETPLACE_PAGE_SIZE);
  state = acceptMarketplaceRetainedPage(state, page("query", previous!), "backward");
  assert.equal(marketplaceRetainedBaseOffset(state), MARKETPLACE_PAGE_SIZE);
  assert.equal(state.pages.length, MARKETPLACE_MAX_RETAINED_PAGES);
  assert.equal(state.pages.at(-1)?.offset, MARKETPLACE_PAGE_SIZE * 8);
});
