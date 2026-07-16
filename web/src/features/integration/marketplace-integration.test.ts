import { createElement } from "react";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  createMarketplaceQueryAdapter,
  IntegratedMarketplaceProvider,
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

const malformedIndex = {
  products: [
    {
      product_id: "p1",
      vendor_id: "v1",
      vendor_name: "Vendor",
      strain_name: "Blue Dream",
      lineage: "sativa_leaning_hybrid",
      total_thc_display_percent: 24,
      variants: [
        {
          variant_id: "valid-7",
          grams: 7,
          current_price: 35,
          price_per_gram: 5,
          product_url: "https://example.test/products/blue-dream?variant=valid-7",
          in_stock: true,
        },
        {
          variant_id: "duplicate-7",
          grams: 7,
          current_price: 42,
          price_per_gram: 6,
          product_url: "https://example.test/products/blue-dream?variant=duplicate-7",
          in_stock: true,
        },
        {
          variant_id: "bad-ppg",
          grams: 14,
          current_price: 28,
          price_per_gram: 1,
          product_url: "https://example.test/products/blue-dream?variant=bad-ppg",
          in_stock: true,
        },
        {
          variant_id: "unsafe-28",
          grams: 28,
          current_price: 56,
          price_per_gram: 2,
          product_url: "javascript:alert(1)",
          in_stock: true,
        },
        {
          variant_id: "valid-14",
          grams: 14,
          current_price: 42,
          price_per_gram: 3,
          product_url: "https://example.test/products/blue-dream?variant=valid-14",
          in_stock: true,
        },
      ],
    },
    {
      product_id: "empty",
      vendor_id: "v1",
      vendor_name: "Vendor",
      strain_name: "Unsafe Only",
      lineage: "hybrid",
      variants: [{
        variant_id: "unsafe-only",
        grams: 7,
        current_price: 7,
        price_per_gram: 1,
        product_url: "http://localhost/product",
        in_stock: true,
      }],
    },
  ],
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

  it("canonicalizes renderable unique-size variants before worker initialization", async () => {
    const products = mapCatalogIndex(malformedIndex);
    expect(products).toHaveLength(1);
    expect(products[0]?.variants.map((variant) => variant.id)).toEqual(["valid-7", "valid-14"]);

    const catalog = {
      initialize: vi.fn().mockResolvedValue({ generationId: "generation-1", index: malformedIndex }),
      loadDetail: vi.fn(),
    };
    const initialize = vi.fn().mockResolvedValue(undefined);
    const query = vi.fn();
    const engine = { initialize, query };
    const capabilities = {
      getCapability: vi.fn((id: string) => {
        if (id === "platform.catalog") return catalog;
        if (id === "platform.query") return engine;
        return undefined;
      }),
    };
    const Mount = vi.fn(() => null);

    render(createElement(IntegratedMarketplaceProvider, {
      mount: Mount,
      capabilities: capabilities as never,
    }));

    await waitFor(() => expect(initialize).toHaveBeenCalledTimes(1));
    expect(initialize).toHaveBeenCalledWith("generation-1", [{
      id: "p1",
      vendor_id: "v1",
      vendor: "Vendor",
      strain: "Blue Dream",
      lineage: "sativa_hybrid",
      total_thc: 24,
      variants: [
        { id: "valid-7", grams: 7, price: 35, price_per_gram: 5 },
        { id: "valid-14", grams: 14, price: 42, price_per_gram: 3 },
      ],
    }]);
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

  it("adapts exact marketplace filters and canonical size counts to the worker engine", async () => {
    const products = mapCatalogIndex(malformedIndex);
    const query = vi.fn().mockResolvedValue({
      rows: [{ productId: "p1", variantId: "valid-7" }],
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
    expect(result.rows[0]?.activeVariant.id).toBe("valid-7");
    expect(result.rows[0]?.availableSizeCount).toBe(2);
  });
});
