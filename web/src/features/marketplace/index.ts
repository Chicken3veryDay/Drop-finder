import { TypeAwareMarketplaceFeature } from "./TypeAwareMarketplaceFeature";

export { TypeAwareMarketplaceFeature };
export { MarketplaceFeature as FlowerMarketplaceFeature } from "./MarketplaceFeature";
export const MarketplaceFeature = TypeAwareMarketplaceFeature;

export const marketplaceFeatureModule = {
  id: "marketplace",
  kind: "primary",
  version: 1,
  mount: TypeAwareMarketplaceFeature,
  capabilities: ["desktop", "mobile", "documents", "keyboard", "multi-product"],
} as const;

export default marketplaceFeatureModule;
export * from "./marketplace-core";
