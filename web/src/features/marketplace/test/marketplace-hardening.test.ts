import assert from "node:assert/strict";
import { it as test } from "vitest";
import {
  DEFAULT_FILTERS,
  getInStockVariants,
  hasConsistentPricePerGram,
  inRange,
  isHttpUrl,
  isRenderableDocument,
  queryMarketplace,
  resolveDocument,
  type MarketplaceFilters,
  type MarketplaceProduct,
  type MarketplaceVariant,
} from "../marketplace-core.js";
import { marketplaceFixtures } from "./fixtures.js";

const filters = (patch: Partial<MarketplaceFilters> = {}): MarketplaceFilters => ({
  ...DEFAULT_FILTERS,
  ...patch,
  totalThc: patch.totalThc ?? {},
  weight: patch.weight ?? {},
  price: patch.price ?? {},
  pricePerGram: patch.pricePerGram ?? {},
});

test("public links accept only bounded HTTP(S) URLs", () => {
  assert.equal(isHttpUrl("https://example.com/report.pdf"), true);
  assert.equal(isHttpUrl("http://example.com/report.pdf"), true);
  assert.equal(isHttpUrl("javascript:alert(1)"), false);
  assert.equal(isHttpUrl("data:text/html,bad"), false);
  assert.equal(isHttpUrl("https://user:pass@example.com/report.pdf"), false);
  assert.equal(isHttpUrl("http://localhost/report.pdf"), false);
  assert.equal(isHttpUrl("http://127.0.0.1/report.pdf"), false);
  assert.equal(isHttpUrl("https://"), false);
  assert.equal(isHttpUrl(`https://example.com/${"x".repeat(5000)}`), false);
});

test("document resolution rejects unsafe URLs and kind mismatches", () => {
  const base = marketplaceFixtures[0]!.variants[0]!;
  const unsafe: MarketplaceVariant = {
    ...base,
    coa: { id: "bad", kind: "coa", url: "javascript:alert(1)", format: "pdf" },
  };
  const mismatched: MarketplaceVariant = {
    ...base,
    coa: { id: "wrong-kind", kind: "terpene", url: "https://example.com/report.pdf", format: "pdf" },
  };

  assert.equal(resolveDocument(unsafe, "coa"), null);
  assert.equal(resolveDocument(mismatched, "coa"), null);
  assert.equal(isRenderableDocument(base.coa, "coa"), true);
});

test("price-per-gram must agree with current price and weight", () => {
  const valid = marketplaceFixtures[0]!.variants[1]!;
  const inconsistent = { ...valid, id: "bad-ppg", pricePerGram: 1 };
  assert.equal(hasConsistentPricePerGram(valid), true);
  assert.equal(hasConsistentPricePerGram(inconsistent), false);

  const product: MarketplaceProduct = {
    ...marketplaceFixtures[0]!,
    id: "inconsistent-product",
    variants: [inconsistent],
  };
  assert.deepEqual(getInStockVariants(product), []);
});

test("duplicate weights collapse deterministically to the best valid offer", () => {
  const original = marketplaceFixtures[0]!.variants[1]!;
  const worse = {
    ...original,
    id: "blue-14-worse",
    currentPrice: 84,
    pricePerGram: 6,
  };
  const product: MarketplaceProduct = {
    ...marketplaceFixtures[0]!,
    id: "duplicate-weight-product",
    variants: [worse, original],
  };

  const variants = getInStockVariants(product);
  assert.equal(variants.length, 1);
  assert.equal(variants[0]!.id, "blue-14");
});

test("duplicate product identities publish only one row", () => {
  const duplicate = {
    ...marketplaceFixtures[0]!,
    vendorName: "Conflicting duplicate",
  };
  const result = queryMarketplace(
    [marketplaceFixtures[0]!, duplicate],
    filters(),
    "lowest_price_per_gram",
  );
  assert.equal(result.total, 1);
  assert.equal(result.rows[0]!.product.vendorName, "Arete");
});

test("invalid ranges fail closed without mutating typed filter values", () => {
  assert.equal(inRange(10, { min: 20, max: 5 }), false);
  assert.equal(
    queryMarketplace(
      marketplaceFixtures,
      filters({ price: { min: 100, max: 20 } }),
      "lowest_price",
    ).total,
    0,
  );
});

test("non-HTTP product URLs cannot enter marketplace rows", () => {
  const product: MarketplaceProduct = {
    ...marketplaceFixtures[0]!,
    id: "unsafe-product-url",
    variants: [
      {
        ...marketplaceFixtures[0]!.variants[0]!,
        id: "unsafe-url",
        productUrl: "javascript:alert(1)",
      },
    ],
  };
  assert.equal(queryMarketplace([product], filters(), "lowest_price").total, 0);
});
