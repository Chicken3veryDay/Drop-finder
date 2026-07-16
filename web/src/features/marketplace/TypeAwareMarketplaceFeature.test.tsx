import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TypeAwareMarketplaceFeature,
  inferProductType,
  normalizeRawCatalog,
} from "./TypeAwareMarketplaceFeature";

const response = (products: unknown[]) => ({
  ok: true,
  status: 200,
  json: async () => ({ products }),
}) as Response;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("type-aware marketplace", () => {
  it("migrates legacy strict-flower records forward", () => {
    const legacy = {
      id: "flower",
      name: "Blue Dream THCA Flower",
      classification_evidence: {
        explicit_thca: true,
        explicit_flower: true,
      },
    };
    expect(inferProductType(legacy)).toBe("cannabis_flower");
    expect(normalizeRawCatalog({ products: [legacy, { name: "Accessory" }] })).toEqual([legacy]);
  });

  it("shows one active product type and suppresses controlled purchase links", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response([
      {
        id: "mushroom",
        source_id: "vendor",
        vendor: "Example Vendor",
        name: "Golden Teacher",
        primary_type: "psilocybin_mushroom",
        type_tags: ["psilocybin_mushroom"],
        species: "Psilocybe Cubensis",
        grams: 7,
        price: 70,
        price_per_gram: 10,
        completeness_score: 80,
        availability: "in_stock",
        url: "",
        public_purchase_url: null,
        classification_evidence: {
          primary_type: "psilocybin_mushroom",
          explicit_psilocybin: true,
          explicit_mushroom: true,
          explicit_vape: false,
          amanita_signal: false,
        },
      },
    ]));

    const user = userEvent.setup();
    render(<TypeAwareMarketplaceFeature products={[]} />);

    await user.click(screen.getByRole("tab", { name: /Mushrooms/ }));
    await waitFor(() => expect(screen.getByText("Golden Teacher")).toBeInTheDocument());

    expect(screen.getByText("Psilocybe Cubensis")).toBeInTheDocument();
    expect(screen.getByText("Informational listing")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View product" })).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("Search vendor or strain")).not.toBeInTheDocument();
  });

  it("renders cannabis vapes with milliliter comparison pricing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response([
      {
        id: "vape",
        source_id: "vendor",
        vendor: "Example Vendor",
        name: "Live Resin Disposable",
        primary_type: "cannabis_vape",
        type_tags: ["cannabis_vape"],
        volume_ml: 1,
        price: 25,
        price_per_ml: 25,
        device_type: "disposable",
        terpenes: ["myrcene", "limonene"],
        completeness_score: 90,
        availability: "in_stock",
        public_purchase_url: "https://example.test/products/vape",
        classification_evidence: {
          primary_type: "cannabis_vape",
          explicit_cannabis: true,
          explicit_vape: true,
        },
      },
    ]));

    const user = userEvent.setup();
    render(<TypeAwareMarketplaceFeature products={[]} />);
    await user.click(screen.getByRole("tab", { name: /Cannabis vapes/ }));

    await waitFor(() => expect(screen.getByText("Live Resin Disposable")).toBeInTheDocument());
    expect(screen.getByText("1 mL")).toBeInTheDocument();
    expect(screen.getAllByText("$25.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("link", { name: "View product" })).toHaveAttribute(
      "href",
      "https://example.test/products/vape",
    );
  });
});
