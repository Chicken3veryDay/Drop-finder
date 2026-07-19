import { describe, expect, it, vi } from "vitest";
import { CanonicalCatalogGenerationClient, canonicalizeCatalogIndex } from "./canonical-catalog-generation-client.js";

const malformedIndex = {
  generation_id: "g1",
  products: [{
    product_id: "p1",
    vendor_id: "v1",
    vendor_name: "Vendor",
    strain_name: "Blue Dream",
    variants: [
      { variant_id: "valid-7", grams: 7, current_price: 35, price_per_gram: 5, product_url: "https://example.test/valid", in_stock: true },
      { variant_id: "valid-7", grams: 14, current_price: 70, price_per_gram: 5, product_url: "https://example.test/duplicate-id", in_stock: true },
      { variant_id: "duplicate-weight", grams: 7, current_price: 42, price_per_gram: 6, product_url: "https://example.test/duplicate-weight", in_stock: true },
      { variant_id: "inconsistent", grams: 14, current_price: 14, price_per_gram: 2, product_url: "https://example.test/inconsistent", in_stock: true },
      { variant_id: "unsafe", grams: 28, current_price: 28, price_per_gram: 1, product_url: "javascript:alert(1)", in_stock: true },
      { variant_id: "sold-out", grams: 56, current_price: 112, price_per_gram: 2, product_url: "https://example.test/sold-out", in_stock: false },
    ],
  }, {
    product_id: "p2",
    vendor_id: "v1",
    vendor_name: "Vendor",
    strain_name: "No valid variant",
    variants: [{
      variant_id: "credential-url",
      grams: 7,
      current_price: 7,
      price_per_gram: 1,
      product_url: "https://user:secret@example.test/product",
      in_stock: true,
    }],
  }],
};

describe("CanonicalCatalogGenerationClient", () => {
  it("applies the marketplace renderability contract before publication to consumers", async () => {
    const result = await canonicalizeCatalogIndex(malformedIndex);
    expect(result.products).toHaveLength(1);
    expect(result.products[0].product_id).toBe("p1");
    expect(result.products[0].variants).toEqual([malformedIndex.products[0].variants[0]]);
  });

  it("canonicalizes a fresh cached fallback before activating or returning it", async () => {
    const cachedAt = Date.now();
    const cached = {
      generationId: "g1",
      manifest: { generation_id: "g1", generated_at: new Date(cachedAt).toISOString() },
      index: malformedIndex,
      activatedAt: cachedAt,
      cachedAt,
      source: "cache",
    };
    const cache = {
      getLastComplete: vi.fn().mockResolvedValue(cached),
      putComplete: vi.fn(),
    };
    const client = new CanonicalCatalogGenerationClient({
      cache,
      maxRetries: 0,
      fetchImpl: vi.fn().mockRejectedValue(new Error("offline")),
    });

    const result = await client.initialize();
    expect(result.index.products).toHaveLength(1);
    expect(result.index.products[0].variants).toEqual([malformedIndex.products[0].variants[0]]);
    const snapshot = client.snapshot();
    expect(snapshot).not.toBeNull();
    expect(snapshot?.index.products).toEqual(result.index.products);
    expect(snapshot?.source).toBe("cache-fallback");
  });
});
