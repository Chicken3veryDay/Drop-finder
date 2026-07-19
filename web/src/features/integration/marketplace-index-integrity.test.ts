import { describe, expect, it } from "vitest";
import { mapCatalogIndex } from "./register-marketplace-props";

const validIndex = () => ({
  product_count: 1,
  in_stock_variant_count: 2,
  products: [{
    product_id: "p1",
    vendor_id: "vendor-1",
    vendor_name: "Vendor One",
    strain_name: "Blue Dream",
    lineage: "sativa",
    variants: [
      {
        variant_id: "v1",
        grams: 3.5,
        current_price: 20,
        price_per_gram: 20 / 3.5,
        product_url: "https://vendor.example/products/blue-dream?variant=v1",
        in_stock: true,
      },
      {
        variant_id: "v2",
        grams: 7,
        current_price: 36,
        price_per_gram: 36 / 7,
        product_url: "https://vendor.example/products/blue-dream?variant=v2",
        in_stock: true,
      },
    ],
  }],
});

const clone = <T>(value: T): T => structuredClone(value);

describe("catalog index consumer integrity", () => {
  it("maps a valid index without changing declared product or variant counts", () => {
    const index = validIndex();
    const products = mapCatalogIndex(index);
    expect(products).toHaveLength(index.product_count);
    expect(products.flatMap((product) => product.variants)).toHaveLength(index.in_stock_variant_count);
  });

  it.each(["vendor_id", "vendor_name", "strain_name"] as const)(
    "rejects a product missing %s instead of silently removing it",
    (field) => {
      const index = clone(validIndex());
      delete index.products[0][field];
      expect(() => mapCatalogIndex(index)).toThrow(/catalog product.*missing/i);
    },
  );

  it("rejects any published variant without an HTTPS navigation URL", () => {
    const index = clone(validIndex());
    index.products[0].variants[1].product_url = "http://vendor.example/products/blue-dream";
    expect(() => mapCatalogIndex(index)).toThrow(/catalog variant.*url/i);
  });

  it("rejects non-stock variants in the compact shopper index", () => {
    const index = clone(validIndex());
    index.products[0].variants[0].in_stock = false;
    expect(() => mapCatalogIndex(index)).toThrow(/catalog variant.*stock/i);
  });

  it("rejects duplicate product and variant identities", () => {
    const duplicateProduct = clone(validIndex());
    duplicateProduct.products.push(clone(duplicateProduct.products[0]));
    duplicateProduct.product_count = 2;
    duplicateProduct.in_stock_variant_count = 4;
    expect(() => mapCatalogIndex(duplicateProduct)).toThrow(/duplicate catalog product/i);

    const duplicateVariant = clone(validIndex());
    duplicateVariant.products[0].variants[1].variant_id = "v1";
    expect(() => mapCatalogIndex(duplicateVariant)).toThrow(/duplicate catalog variant/i);
  });

  it("rejects declared count mismatches instead of exposing a partial marketplace", () => {
    const productMismatch = clone(validIndex());
    productMismatch.product_count = 2;
    expect(() => mapCatalogIndex(productMismatch)).toThrow(/product count mismatch/i);

    const variantMismatch = clone(validIndex());
    variantMismatch.in_stock_variant_count = 3;
    expect(() => mapCatalogIndex(variantMismatch)).toThrow(/variant count mismatch/i);
  });

  it("rejects a malformed index envelope", () => {
    expect(() => mapCatalogIndex({ products: "not-an-array" })).toThrow(/products must be an array/i);
  });
});
