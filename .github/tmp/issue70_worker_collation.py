import re
from pathlib import Path

contracts = Path("web/src/platform/contracts.js")
text = contracts.read_text(encoding="utf-8")
if "export function marketplaceNameCompare" not in text:
    text = text.replace(
        "export function stableCompare(a, b) {\n  return a < b ? -1 : a > b ? 1 : 0;\n}\n",
        "const marketplaceNameCollator = new Intl.Collator('en', {\n"
        "  sensitivity: 'base',\n"
        "  numeric: true,\n"
        "  usage: 'sort',\n"
        "});\n\n"
        "export function marketplaceNameCompare(a, b) {\n"
        "  return marketplaceNameCollator.compare(String(a), String(b));\n"
        "}\n\n"
        "export function stableCompare(a, b) {\n"
        "  return a < b ? -1 : a > b ? 1 : 0;\n"
        "}\n",
        1,
    )
if "export function marketplaceNameCompare" not in text:
    raise SystemExit("shared marketplace comparator was not installed")
contracts.write_text(text, encoding="utf-8")

core = Path("web/src/features/marketplace/marketplace-core.ts")
text = core.read_text(encoding="utf-8")
if "marketplaceNameCompare, stableCompare" not in text:
    text = text.replace(
        'import type { ReactNode } from "react";\n',
        'import type { ReactNode } from "react";\nimport { marketplaceNameCompare, stableCompare } from "../../platform/contracts.js";\n',
        1,
    )
text = re.sub(
    r'const collator = new Intl\.Collator\(undefined, \{\n\s+sensitivity: "base",\n\s+numeric: true,\n\s+usage: "sort",\n\}\);\n\n',
    '',
    text,
    count=1,
)
for old, new in {
    "collator.compare(a.id, b.id)": "stableCompare(a.id, b.id)",
    "collator.compare(a.product.strainName, b.product.strainName)": "marketplaceNameCompare(a.product.strainName, b.product.strainName)",
    "collator.compare(b.product.strainName, a.product.strainName)": "marketplaceNameCompare(b.product.strainName, a.product.strainName)",
    "collator.compare(a.product.vendorName, b.product.vendorName)": "marketplaceNameCompare(a.product.vendorName, b.product.vendorName)",
    "collator.compare(b.product.vendorName, a.product.vendorName)": "marketplaceNameCompare(b.product.vendorName, a.product.vendorName)",
    "collator.compare(a.product.id, b.product.id)": "stableCompare(a.product.id, b.product.id)",
}.items():
    text = text.replace(old, new)
if "collator.compare" in text or "marketplaceNameCompare" not in text:
    raise SystemExit("feature comparator conversion incomplete")
core.write_text(text, encoding="utf-8")

engine = Path("web/src/platform/workers/marketplace-query-engine.js")
text = engine.read_text(encoding="utf-8")
text = text.replace(
    "import { PlatformError, stableCompare } from '../contracts.js';",
    "import { marketplaceNameCompare, PlatformError, stableCompare } from '../contracts.js';",
    1,
)
text = text.replace(
    "  return (a, b) => direction * valueCompare(a[field], b[field])\n"
    "    || stableCompare(a.productId, b.productId)\n"
    "    || stableCompare(a.variantId, b.variantId);",
    "  const compare = field === 'vendor' || field === 'strain' ? marketplaceNameCompare : valueCompare;\n"
    "  return (a, b) => direction * compare(a[field], b[field])\n"
    "    || stableCompare(a.productId, b.productId)\n"
    "    || stableCompare(a.variantId, b.variantId);",
    1,
)
if "marketplaceNameCompare" not in text or "direction * valueCompare(a[field], b[field])" in text:
    raise SystemExit("worker comparator conversion incomplete")
engine.write_text(text, encoding="utf-8")

Path("web/src/features/marketplace/marketplace-sort-parity.test.ts").write_text('''import { describe, expect, it } from "vitest";
import { executeQuery } from "../../platform/workers/marketplace-query-engine.js";
import { DEFAULT_FILTERS, queryMarketplace, type MarketplaceProduct, type SortOption } from "./marketplace-core";

const names = [
  { id: "p-eclair-a", strain: "Éclair", vendor: "Vendor 10" },
  { id: "p-eclair-b", strain: "Eclair", vendor: "Vendor 2" },
  { id: "p-strain-10", strain: "Strain 10", vendor: "Éclair Farms" },
  { id: "p-strain-2", strain: "Strain 2", vendor: "Eclair Farms" },
];
const products: MarketplaceProduct[] = names.map((entry, index) => ({
  id: entry.id, vendorId: `vendor-${index}`, vendorName: entry.vendor, strainName: entry.strain, lineage: "hybrid",
  variants: [{ id: `variant-${index}`, grams: 3.5, sourceWeightLabel: "3.5g", currentPrice: 20 + index,
    pricePerGram: (20 + index) / 3.5, inStock: true, productUrl: `https://example.test/products/${entry.id}` }],
}));
const compactRows = products.map((product) => ({
  id: product.id, vendorId: product.vendorId, vendor: product.vendorName, strain: product.strainName,
  lineage: product.lineage, totalThc: null,
  variants: product.variants.map((variant) => ({ id: variant.id, weight: variant.grams, price: variant.currentPrice, ppg: variant.pricePerGram })),
}));
const request = (sort: SortOption, offset = 0, limit = 100) => ({ search: "", vendors: [], lineages: [], minTotalThc: null,
  maxTotalThc: null, minWeight: null, maxWeight: null, minPrice: null, maxPrice: null, minPpg: null, maxPpg: null,
  sort, offset, limit, expandedProductId: null });

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
