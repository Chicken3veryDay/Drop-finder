import { describe, expect, it } from "vitest";
import type { MarketplaceProduct } from "../marketplace/marketplace-core";
import { sectionForProduct } from "./register-product-sections";

const product = (strainName: string, extra: Record<string, unknown> = {}): MarketplaceProduct => ({
  id: strainName.toLowerCase().replace(/\W+/g, "-"),
  vendorId: "fixture",
  vendorName: "Fixture Vendor",
  strainName,
  lineage: "unknown",
  variants: [],
  ...extra,
});

describe("marketplace product sections", () => {
  it("keeps ordinary THCA flower in the flower section", () => {
    expect(sectionForProduct(product("Blue Dream THCA Flower"))).toBe("flower");
  });

  it("routes explicitly named vape products to Vapes", () => {
    expect(sectionForProduct(product("Blue Dream THCA Disposable Vape 1g"))).toBe("vapes");
  });

  it("routes mushroom products and mushroom vapes to Mushrooms", () => {
    expect(sectionForProduct(product("Amanita Mushroom Caps 7g"))).toBe("mushrooms");
    expect(sectionForProduct(product("Psilocybin Mushroom Vape 1ml"))).toBe("mushrooms");
  });

  it("prefers explicit catalog type metadata over title inference", () => {
    expect(sectionForProduct(product("Blue Dream", { productType: "cannabis_vape" }))).toBe("vapes");
    expect(sectionForProduct(product("Golden Teacher", { product_type: "mushroom" }))).toBe("mushrooms");
  });
});
