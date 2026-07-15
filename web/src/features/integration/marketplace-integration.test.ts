import { describe, expect, it, vi } from "vitest";
import {
  createMarketplaceQueryAdapter,
  mapCatalogDetail,
  mapCatalogIndex,
} from "./register-marketplace-props";

const index = {
  products: [{
    product_id: "p1",
    vendor_id: "v1",
    vendor_name: "Vendor",
    strain_name: "Blue Dream",
    lineage: "sativa_leaning_hybrid",
    total_thc_display_percent: 24,
    variants: [{
      variant_id: "v1-7",
      grams: 7,
      source_weight_label: "Quarter",
      current_price: 42,
      original_price: 50,
      price_per_gram: 6,
      product_url: "https://example.test/product",
      in_stock: true,
    }],
  }],
};

describe("integrated marketplace contracts", () => {
  it("maps the real catalog-v4 compact index without inventing fields", () => {
    const products = mapCatalogIndex(index);
    expect(products).toHaveLength(1);
    expect(products[0]).toMatchObject({
      id: "p1",
      vendorId: "v1",
      strainName: "Blue Dream",
      lineage: "sativa_leaning_hybrid",
      totalThcDisplay: 24,
    });
    expect(products[0]?.variants[0]).toMatchObject({
      id: "v1-7",
      grams: 7,
      currentPrice: 42,
      pricePerGram: 6,
      productUrl: "https://example.test/product",
    });
  });

  it("maps lazy detail shards and preserves source-exposed effects", () => {
    const detail = mapCatalogDetail({
      products: [{
        product_id: "p1",
        image_url: "https://example.test/image.webp",
        effects: ["calm", "focus"],
        grow_environment: "indoor",
      }],
    }, "p1");
    expect(detail).toEqual({
      productId: "p1",
      imageUrl: "https://example.test/image.webp",
      effects: ["calm", "focus"],
      growEnvironment: "indoor",
    });
  });

  it("adapts exact marketplace filters and sorts to the worker engine", async () => {
    const products = mapCatalogIndex(index);
    const query = vi.fn().mockResolvedValue({
      rows: [{ productId: "p1", variantId: "v1-7" }],
      total: 1,
      nextOffset: null,
    });
    const adapter = createMarketplaceQueryAdapter({
      initialize: vi.fn(),
      query,
    });
    const result = await adapter.query(products, {
      search: "blue",
      vendorIds: ["v1"],
      lineages: ["sativa_leaning_hybrid"],
      totalThc: { min: 20 },
      weight: {},
      price: {},
      pricePerGram: {},
    }, "lowest_price_per_gram", {
      offset: 0,
      limit: 120,
      expandedProductId: null,
    });
    expect(query).toHaveBeenCalledWith(expect.objectContaining({
      lineages: ["sativa_hybrid"],
      sort: "lowest_ppg",
      minTotalThc: 20,
    }));
    expect(result.rows[0]?.product.id).toBe("p1");
    expect(result.rows[0]?.activeVariant.id).toBe("v1-7");
  });
});
