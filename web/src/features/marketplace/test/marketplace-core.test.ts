import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_FILTERS,
  SORT_OPTIONS,
  discountPercent,
  escapeSearchState,
  formatRating,
  formatTotalThc,
  getInStockVariants,
  hasValidDiscount,
  keepExpandedProduct,
  nextExpandedProduct,
  normalizeSearch,
  queryMarketplace,
  resolveDocument,
  resolveVariant,
  selectActiveVariant,
  type MarketplaceFilters,
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

test("normalizes punctuation and case without fuzzy expansion", () => {
  assert.equal(normalizeSearch("  WNC—CBD / Blue_Dream  "), "wnc cbd blue dream");
});

test("search is restricted to vendor and strain name", () => {
  assert.deepEqual(
    queryMarketplace(marketplaceFixtures, filters({ search: "Arete" }), "strain_az").rows.map((row) => row.product.id),
    ["arete-blue-dream"],
  );
  assert.deepEqual(
    queryMarketplace(marketplaceFixtures, filters({ search: "creative" }), "strain_az").rows.map((row) => row.product.id),
    [],
  );
});

test("vendor and lineage selections combine", () => {
  const result = queryMarketplace(
    marketplaceFixtures,
    filters({ vendorIds: ["arete", "holy-city"], lineages: ["indica"] }),
    "strain_az",
  );
  assert.deepEqual(result.rows.map((row) => row.product.id), ["holy-city-kosmic-kush"]);
});

test("all numeric ranges and combined filters apply to active row values", () => {
  const result = queryMarketplace(
    marketplaceFixtures,
    filters({
      totalThc: { min: 25, max: 32 },
      weight: { min: 10, max: 20 },
      price: { min: 70, max: 80 },
      pricePerGram: { min: 5, max: 5.5 },
    }),
    "lowest_price",
  );
  assert.deepEqual(result.rows.map((row) => row.product.id), ["arete-blue-dream", "holy-city-kosmic-kush"]);
});

test("missing potency is omitted only when a potency bound is active", () => {
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "strain_az").rows.some((row) => row.product.id === "wnc-pineapple-express"), true);
  assert.equal(queryMarketplace(marketplaceFixtures, filters({ totalThc: { min: 1 } }), "strain_az").rows.some((row) => row.product.id === "wnc-pineapple-express"), false);
});

test("active variant uses lowest PPG then price, weight, and stable ID", () => {
  const blue = marketplaceFixtures[0]!;
  assert.equal(selectActiveVariant(blue, {})?.id, "blue-14");
  assert.equal(selectActiveVariant(blue, { min: 20 })?.id, "blue-28");
  assert.equal(selectActiveVariant(blue, { max: 4 })?.id, "blue-3.5");
});

test("out-of-stock and malformed variants can never render", () => {
  const malformed = marketplaceFixtures.at(-1)!;
  const soldOut = {
    ...marketplaceFixtures[0]!,
    id: "sold-out",
    variants: [{ ...marketplaceFixtures[0]!.variants[0]!, id: "sold-out-variant", inStock: false }],
  } as any;
  assert.deepEqual(getInStockVariants(malformed), []);
  assert.deepEqual(getInStockVariants(soldOut), []);
  assert.equal(queryMarketplace([...marketplaceFixtures, soldOut], filters(), "strain_az").rows.some((row) => row.product.id === malformed.id || row.product.id === soldOut.id), false);
});

test("row price, URL, and documents stay on the same selected variant", () => {
  const blue = marketplaceFixtures[0]!;
  const active = selectActiveVariant(blue, {})!;
  assert.equal(active.id, "blue-14");
  assert.equal(active.currentPrice, 72);
  assert.equal(active.productUrl.endsWith("variant=14"), true);
  assert.equal(resolveDocument(active, "coa")?.id, "coa-blue-14");
  assert.equal(resolveDocument(active, "terpene")?.id, "terp-blue-14");
  assert.equal(resolveVariant(blue, "blue-3.5", active).coa?.id, "coa-blue-3.5");
});

test("available size count includes every valid in-stock size", () => {
  const row = queryMarketplace(marketplaceFixtures, filters({ weight: { min: 10, max: 20 } }), "strain_az").rows.find((item) => item.product.id === "arete-blue-dream")!;
  assert.equal(row.availableSizeCount, 3);
  assert.equal(row.activeVariant.id, "blue-14");
});

test("discount formatting rejects contradictory original prices", () => {
  const discounted = marketplaceFixtures[0]!.variants[1]!;
  const contradictory = marketplaceFixtures[4]!.variants[0]!;
  assert.equal(hasValidDiscount(discounted), true);
  assert.equal(discountPercent(discounted), 20);
  assert.equal(hasValidDiscount(contradictory), false);
  assert.equal(discountPercent(contradictory), null);
});

test("Total THC is whole-number shopper output with quiet unavailable state", () => {
  assert.equal(formatTotalThc(27.49), "27%");
  assert.equal(formatTotalThc(27.5), "28%");
  assert.equal(formatTotalThc(null), "—");
  assert.equal(formatTotalThc(120), "—");
});

test("ratings require both valid score and count", () => {
  assert.equal(formatRating(4.7, 182), "4.7 (182)");
  assert.equal(formatRating(4.7, 0), null);
  assert.equal(formatRating(6, 2), null);
});

test("only one expanded row remains open and filtered-out expansion closes", () => {
  assert.equal(nextExpandedProduct(null, "a"), "a");
  assert.equal(nextExpandedProduct("a", "a"), null);
  assert.equal(nextExpandedProduct("a", "b"), "b");
  const rows = queryMarketplace(marketplaceFixtures, filters({ vendorIds: ["arete"] }), "strain_az").rows;
  assert.equal(keepExpandedProduct("arete-blue-dream", rows), "arete-blue-dream");
  assert.equal(keepExpandedProduct("holy-city-kosmic-kush", rows), null);
});

test("Escape clears search before blurring it", () => {
  assert.deepEqual(escapeSearchState("blue", true), { value: "", shouldBlur: false });
  assert.deepEqual(escapeSearchState("", true), { value: "", shouldBlur: true });
});

test("exact sort set and deterministic ordering", () => {
  assert.deepEqual(SORT_OPTIONS, [
    "lowest_price",
    "highest_price",
    "lowest_price_per_gram",
    "highest_price_per_gram",
    "strain_az",
    "strain_za",
    "vendor_az",
    "vendor_za",
  ]);
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "lowest_price").rows[0]!.product.id, "green-unicorn-sunrise");
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "highest_price").rows[0]!.product.id, "holy-city-kosmic-kush");
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "strain_az").rows[0]!.product.strainName, "Blue Dream");
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "strain_za").rows[0]!.product.strainName, "Sunrise");
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "vendor_az").rows[0]!.product.vendorName, "Arete");
  assert.equal(queryMarketplace(marketplaceFixtures, filters(), "vendor_za").rows[0]!.product.vendorName, "WNC CBD");
});
