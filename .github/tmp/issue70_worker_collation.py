from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/features/marketplace/marketplace-core.ts",
    'const collator = new Intl.Collator(undefined, {\n',
    'const collator = new Intl.Collator("en", {\n',
)

engine = Path("web/src/platform/workers/marketplace-query-engine.js")
text = engine.read_text(encoding="utf-8")
anchor = "export const SORTS = Object.freeze([\n"
collator = "const collator = new Intl.Collator('en', {\n  sensitivity: 'base',\n  numeric: true,\n  usage: 'sort',\n});\n\n"
if collator not in text:
    if text.count(anchor) != 1:
        raise SystemExit(f"worker collator anchor count: {text.count(anchor)}")
    text = text.replace(anchor, collator + anchor, 1)
old_sort = """  return (a, b) => direction * valueCompare(a[field], b[field])
    || stableCompare(a.productId, b.productId)
    || stableCompare(a.variantId, b.variantId);
"""
new_sort = """  const compare = field === 'vendor' || field === 'strain' ? collator.compare.bind(collator) : valueCompare;
  return (a, b) => direction * compare(a[field], b[field])
    || collator.compare(a.productId, b.productId)
    || collator.compare(a.variantId, b.variantId);
"""
if text.count(old_sort) != 1:
    raise SystemExit(f"worker sort anchor count: {text.count(old_sort)}")
engine.write_text(text.replace(old_sort, new_sort, 1), encoding="utf-8")

Path("web/src/features/marketplace/marketplace-sort-parity.test.ts").write_text('''import { describe, expect, it } from "vitest";
// @ts-expect-error The worker engine is intentionally JavaScript and has no declaration file.
import { executeQuery } from "../../platform/workers/marketplace-query-engine.js";
import { DEFAULT_FILTERS, queryMarketplace, type MarketplaceProduct, type SortOption } from "./marketplace-core";

type WorkerRow = { productId: string };

const names = [
  { id: "p-eclair-a", strain: "Éclair", vendor: "Vendor 10" },
  { id: "p-eclair-b", strain: "Eclair", vendor: "Vendor 2" },
  { id: "p-strain-10", strain: "Strain 10", vendor: "Éclair Farms" },
  { id: "p-strain-2", strain: "Strain 2", vendor: "Eclair Farms" },
];
const products: MarketplaceProduct[] = names.map((entry, index) => ({
  id: entry.id,
  vendorId: `vendor-${index}`,
  vendorName: entry.vendor,
  strainName: entry.strain,
  lineage: "hybrid",
  variants: [{
    id: `variant-${index}`,
    grams: 3.5,
    sourceWeightLabel: "3.5g",
    currentPrice: 20 + index,
    pricePerGram: (20 + index) / 3.5,
    inStock: true,
    productUrl: `https://example.test/products/${entry.id}`,
  }],
}));
const compactRows = products.map((product) => ({
  id: product.id,
  vendorId: product.vendorId,
  vendor: product.vendorName,
  strain: product.strainName,
  lineage: product.lineage,
  totalThc: null,
  variants: product.variants.map((variant) => ({
    id: variant.id,
    weight: variant.grams,
    price: variant.currentPrice,
    ppg: variant.pricePerGram,
  })),
}));
const request = (sort: SortOption, offset = 0, limit = 100) => ({
  search: "",
  vendors: [],
  lineages: [],
  minTotalThc: null,
  maxTotalThc: null,
  minWeight: null,
  maxWeight: null,
  minPrice: null,
  maxPrice: null,
  minPpg: null,
  maxPpg: null,
  sort,
  offset,
  limit,
  expandedProductId: null,
});

describe("marketplace name collation parity", () => {
  for (const sort of ["strain_az", "strain_za", "vendor_az", "vendor_za"] as const) {
    it(`keeps synchronous and worker ${sort} ordering identical`, () => {
      const featureIds = queryMarketplace(products, DEFAULT_FILTERS, sort).rows.map((row) => row.product.id);
      const workerIds = executeQuery(compactRows, request(sort)).rows.map((row: WorkerRow) => row.productId);
      expect(workerIds).toEqual(featureIds);
    });

    it(`keeps ${sort} stable across page boundaries`, () => {
      const featureIds = queryMarketplace(products, DEFAULT_FILTERS, sort).rows.map((row) => row.product.id);
      const first = executeQuery(compactRows, request(sort, 0, 2)).rows.map((row: WorkerRow) => row.productId);
      const second = executeQuery(compactRows, request(sort, 2, 2)).rows.map((row: WorkerRow) => row.productId);
      expect([...first, ...second]).toEqual(featureIds);
    });
  }

  it("uses numeric segments and deterministic accent/case ties", () => {
    const ids = queryMarketplace(products, DEFAULT_FILTERS, "strain_az").rows.map((row) => row.product.id);
    expect(ids).toEqual(["p-eclair-a", "p-eclair-b", "p-strain-2", "p-strain-10"]);
  });
});
''', encoding="utf-8")
