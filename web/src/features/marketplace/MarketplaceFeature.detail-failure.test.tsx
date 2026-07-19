import { useCallback, useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MarketplaceFeature } from "./MarketplaceFeature.js";
import type { MarketplaceProduct, MarketplaceProductDetail } from "./marketplace-core.js";

const product: MarketplaceProduct = {
  id: "product-1",
  vendorId: "vendor-1",
  vendorName: "Example Vendor",
  strainName: "Blue Example",
  lineage: "hybrid",
  totalThcDisplay: 24.5,
  variants: [{
    id: "variant-1",
    grams: 3.5,
    sourceWeightLabel: "3.5 g",
    currentPrice: 30,
    pricePerGram: 30 / 3.5,
    inStock: true,
    productUrl: "https://example.test/products/blue-example",
  }],
};

const detail: MarketplaceProductDetail = {
  productId: product.id,
  effects: ["Calm"],
  growEnvironment: "indoor",
};

const coa = {
  id: "coa-1",
  kind: "coa" as const,
  url: "https://example.test/coa.pdf",
  format: "pdf" as const,
  mimeType: "application/pdf",
};

function rowButton(): HTMLElement {
  return screen.getByRole("button", { name: /Example Vendor.*Blue Example/i });
}

describe("MarketplaceFeature detail failure state", () => {
  it("shows a degraded state and restores document controls after retry", async () => {
    const user = userEvent.setup();
    let attempts = 0;

    function Harness() {
      const [products, setProducts] = useState<MarketplaceProduct[]>([product]);
      const loadDetail = useCallback(async () => {
        attempts += 1;
        if (attempts === 1) throw new Error("detail hash mismatch");
        setProducts([{ ...product, variants: [{ ...product.variants[0]!, coa }] }]);
        return detail;
      }, []);
      return (
        <MarketplaceFeature
          products={products}
          catalogGenerationId="generation-1"
          loadDetail={loadDetail}
        />
      );
    }

    render(<Harness />);
    await user.click(rowButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Product details and lab documents could not be loaded.");
    expect(screen.queryByRole("button", { name: "Open COA" })).not.toBeInTheDocument();
    expect(screen.queryByText("Grow")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry details" }));
    expect(await screen.findByRole("button", { name: "Open COA" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Calm")).toBeInTheDocument();
    expect(screen.getByText("indoor")).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("keeps collapse and supersession aborts quiet", async () => {
    const user = userEvent.setup();
    const loadDetail = vi.fn((_productId: string, signal: AbortSignal) => new Promise<MarketplaceProductDetail>((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    }));

    render(
      <MarketplaceFeature
        products={[product]}
        catalogGenerationId="generation-1"
        loadDetail={loadDetail}
      />,
    );

    await user.click(rowButton());
    expect(await screen.findByRole("status")).toHaveTextContent("Loading product details and lab documents");
    await user.click(rowButton());
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(loadDetail).toHaveBeenCalledTimes(1);
  });
});
