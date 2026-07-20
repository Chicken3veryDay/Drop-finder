from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


contracts = "web/src/platform/contracts.js"
replace_once(
    contracts,
    """export function stableCompare(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}
""",
    """const marketplaceNameCollator = new Intl.Collator('en', {
  sensitivity: 'base',
  numeric: true,
  usage: 'sort',
});

export function marketplaceNameCompare(a, b) {
  return marketplaceNameCollator.compare(String(a), String(b));
}

export function stableCompare(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}
""",
)

core = "web/src/features/marketplace/marketplace-core.ts"
replace_once(
    core,
    'import type { ReactNode } from "react";\n',
    'import type { ReactNode } from "react";\nimport { marketplaceNameCompare, stableCompare } from "../../platform/contracts.js";\n',
)
replace_once(
    core,
    """const collator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
  usage: "sort",
});

""",
    "",
)
text = Path(core).read_text(encoding="utf-8")
replacements = {
    "collator.compare(a.id, b.id)": "stableCompare(a.id, b.id)",
    "collator.compare(a.product.strainName, b.product.strainName)": "marketplaceNameCompare(a.product.strainName, b.product.strainName)",
    "collator.compare(b.product.strainName, a.product.strainName)": "marketplaceNameCompare(b.product.strainName, a.product.strainName)",
    "collator.compare(a.product.vendorName, b.product.vendorName)": "marketplaceNameCompare(a.product.vendorName, b.product.vendorName)",
    "collator.compare(b.product.vendorName, a.product.vendorName)": "marketplaceNameCompare(b.product.vendorName, a.product.vendorName)",
    "collator.compare(a.product.id, b.product.id)": "stableCompare(a.product.id, b.product.id)",
}
for old, new in replacements.items():
    count = text.count(old)
    if count < 1:
        raise SystemExit(f"{core}: missing comparator anchor {old!r}")
    text = text.replace(old, new)
if "collator.compare" in text:
    raise SystemExit(f"{core}: unconverted collator call remains")
Path(core).write_text(text, encoding="utf-8")

engine = "web/src/platform/workers/marketplace-query-engine.js"
replace_once(
    engine,
    "import { PlatformError, stableCompare } from '../contracts.js';\n",
    "import { marketplaceNameCompare, PlatformError, stableCompare } from '../contracts.js';\n",
)
replace_once(
    engine,
    """  return (a, b) => direction * valueCompare(a[field], b[field])
    || stableCompare(a.productId, b.productId)
    || stableCompare(a.variantId, b.variantId);
""",
    """  const compare = field === 'vendor' || field === 'strain' ? marketplaceNameCompare : valueCompare;
  return (a, b) => direction * compare(a[field], b[field])
    || stableCompare(a.productId, b.productId)
    || stableCompare(a.variantId, b.variantId);
""",
)

Path("web/src/features/marketplace/marketplace-sort-parity.test.ts").write_text('''import { describe, expect, it } from "vitest";
import { executeQuery } from "../../platform/workers/marketplace-query-engine.js";
import {
  DEFAULT_FILTERS,
  queryMarketplace,
  type MarketplaceProduct,
  type SortOption,
} from "./marketplace-core";

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
      const workerIds = executeQuery(compactRows, request(sort)).rows.map((row) => row.productId);
      expect(workerIds).toEqual(featureIds);
    });

    it(`keeps ${sort} stable across page boundaries`, () => {
      const featureIds = queryMarketplace(products, DEFAULT_FILTERS, sort).rows.map((row) => row.product.id);
      const first = executeQuery(compactRows, request(sort, 0, 2)).rows.map((row) => row.productId);
      const second = executeQuery(compactRows, request(sort, 2, 2)).rows.map((row) => row.productId);
      expect([...first, ...second]).toEqual(featureIds);
    });
  }

  it("uses numeric segments and deterministic accent/case ties", () => {
    const ids = queryMarketplace(products, DEFAULT_FILTERS, "strain_az").rows.map((row) => row.product.id);
    expect(ids).toEqual(["p-eclair-a", "p-eclair-b", "p-strain-2", "p-strain-10"]);
  });
});
''', encoding="utf-8")
