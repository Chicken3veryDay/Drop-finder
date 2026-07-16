/* eslint-disable react-refresh/only-export-components */
import { useMemo, useState, type ComponentType } from "react";
import type { CapabilityReader, CapabilityRegistrationTarget } from "../../app/capabilityRegistry";
import type { MarketplaceFeatureProps, MarketplaceProduct } from "../marketplace/marketplace-core";
import { IntegratedMarketplaceProvider } from "./register-marketplace-props";
import "./product-sections.css";

export type MarketplaceSection = "flower" | "vapes" | "mushrooms";

type ProviderProps = {
  mount: ComponentType<MarketplaceFeatureProps>;
  capabilities: CapabilityReader;
};

type SectionDefinition = {
  id: MarketplaceSection;
  label: string;
};

const SECTIONS: readonly SectionDefinition[] = [
  { id: "flower", label: "Flower" },
  { id: "vapes", label: "Vapes" },
  { id: "mushrooms", label: "Mushrooms" },
] as const;

const VAPE_SIGNAL = /\b(?:vapes?|cartridges?|carts?|disposables?|all[- ]?in[- ]?one|510(?:[- ]thread)?)\b/i;
const MUSHROOM_SIGNAL = /\b(?:mushrooms?|amanita|muscaria|psilocybin|functional\s+mushroom|lion'?s\s+mane|cordyceps|reishi)\b/i;

const stringValue = (value: unknown): string => typeof value === "string" ? value.trim() : "";

export const sectionForProduct = (product: MarketplaceProduct): MarketplaceSection => {
  const record = product as MarketplaceProduct & {
    productType?: unknown;
    product_type?: unknown;
    typeTags?: unknown;
    type_tags?: unknown;
  };
  const explicitType = stringValue(record.productType ?? record.product_type);
  if (explicitType === "cannabis_vape") return "vapes";
  if (["mushroom", "mushroom_vape", "psilocybin_mushroom", "psilocybin_vape"].includes(explicitType)) {
    return "mushrooms";
  }
  const tags = Array.isArray(record.typeTags)
    ? record.typeTags
    : Array.isArray(record.type_tags)
      ? record.type_tags
      : [];
  if (tags.some((value) => ["mushroom", "mushroom_vape", "psilocybin_mushroom", "psilocybin_vape"].includes(stringValue(value)))) {
    return "mushrooms";
  }
  if (tags.some((value) => stringValue(value) === "cannabis_vape")) return "vapes";

  const searchable = `${product.strainName} ${product.vendorName}`;
  if (MUSHROOM_SIGNAL.test(searchable)) return "mushrooms";
  if (VAPE_SIGNAL.test(searchable)) return "vapes";
  return "flower";
};

function SectionedMarketplace({
  mount: Mount,
  marketplaceProps,
}: {
  mount: ComponentType<MarketplaceFeatureProps>;
  marketplaceProps: MarketplaceFeatureProps;
}) {
  const [activeSection, setActiveSection] = useState<MarketplaceSection>("flower");
  const grouped = useMemo(() => {
    const next: Record<MarketplaceSection, MarketplaceProduct[]> = {
      flower: [],
      vapes: [],
      mushrooms: [],
    };
    for (const product of marketplaceProps.products) {
      next[sectionForProduct(product)].push(product);
    }
    return next;
  }, [marketplaceProps.products]);

  const typedCatalog = grouped.vapes.length > 0 || grouped.mushrooms.length > 0;
  const activeProducts = grouped[activeSection];

  return (
    <div className={`df-product-sections df-section-${activeSection}`}>
      <nav className="df-product-section-nav" aria-label="Product section">
        <div className="df-product-section-tabs" role="tablist" aria-label="Marketplace product sections">
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              role="tab"
              aria-selected={activeSection === section.id}
              className="df-product-section-tab"
              onClick={() => setActiveSection(section.id)}
            >
              <span>{section.label}</span>
              <span className="df-product-section-count" aria-label={`${grouped[section.id].length} products`}>
                {grouped[section.id].length.toLocaleString()}
              </span>
            </button>
          ))}
        </div>
      </nav>

      {activeSection === "mushrooms" ? (
        <p className="df-product-section-notice" role="note">
          Mushroom listings are informational. Outbound product purchase links are hidden in this section.
        </p>
      ) : null}

      <div role="tabpanel" aria-label={`${SECTIONS.find((section) => section.id === activeSection)?.label ?? "Marketplace"} products`}>
        <Mount
          key={activeSection}
          {...marketplaceProps}
          products={activeProducts}
          asyncQueryEngine={typedCatalog ? undefined : marketplaceProps.asyncQueryEngine}
        />
      </div>
    </div>
  );
}

export function ProductSectionMarketplaceProvider({
  mount: Mount,
  capabilities,
}: ProviderProps) {
  const SectionedMount = useMemo<ComponentType<MarketplaceFeatureProps>>(() => {
    const WrappedMarketplace = (props: MarketplaceFeatureProps) => (
      <SectionedMarketplace mount={Mount} marketplaceProps={props} />
    );
    WrappedMarketplace.displayName = "SectionedMarketplace";
    return WrappedMarketplace;
  }, [Mount]);

  return <IntegratedMarketplaceProvider mount={SectionedMount} capabilities={capabilities} />;
}

export function registerFeatureCapabilities(registry: CapabilityRegistrationTarget): void {
  registry.registerCapability("marketplace.props", {
    contractVersion: 1,
    instance: { Provider: ProductSectionMarketplaceProvider },
  });
}
