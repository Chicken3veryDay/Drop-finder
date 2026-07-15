import { describe, expect, it } from "vitest";
import { validProduct } from "../test/fixtures";
import { validateCatalogManifest, validateMarketplaceProduct } from "./validators";

const clone = <T>(value: T): T => structuredClone(value);

describe("validateMarketplaceProduct", () => {
  it("accepts the versioned in-stock marketplace contract", () => {
    expect(validateMarketplaceProduct(validProduct)).toEqual({ ok: true, value: validProduct });
  });

  it("rejects out-of-stock variants so they cannot reach rendering", () => {
    const product = clone(validProduct) as unknown as Record<string, any>;
    product.variants[0].stock = { state: "out_of_stock", available: false, observedAt: "2026-07-14T20:00:00Z" };
    const result = validateMarketplaceProduct(product);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.issues.map((issue) => issue.path)).toContain("variants[0].stock.state");
  });

  it("requires Total THC to expose the rounded whole-percent display value", () => {
    const product = clone(validProduct) as unknown as Record<string, any>;
    product.totalThc.roundedDisplayPercent = 26;
    const result = validateMarketplaceProduct(product);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.issues).toContainEqual(expect.objectContaining({ path: "totalThc.roundedDisplayPercent" }));
  });

  it("rejects duplicate variant identities", () => {
    const product = clone(validProduct) as unknown as Record<string, any>;
    product.variants.push(clone(product.variants[0]));
    const result = validateMarketplaceProduct(product);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.issues).toContainEqual(expect.objectContaining({ path: "variants" }));
  });
});

describe("validateCatalogManifest", () => {
  it("accepts relative page and index metadata", () => {
    const manifest = {
      schemaVersion: "1.0.0",
      catalogVersion: "2026-07-14T20:00:00Z",
      generatedAt: "2026-07-14T20:00:00Z",
      index: {
        url: "./data/catalog-index.json",
        sha256: "a".repeat(64),
        generatedAt: "2026-07-14T20:00:00Z",
        productCount: 1,
        pageCount: 1,
      },
      pages: [{
        id: "page-0001",
        url: "./data/catalog-page-0001.json",
        sha256: "b".repeat(64),
        productCount: 1,
        firstProductKey: "vendor-a:blue-dream",
        lastProductKey: "vendor-a:blue-dream",
      }],
    };
    expect(validateCatalogManifest(manifest)).toEqual({ ok: true, value: manifest });
  });
});
