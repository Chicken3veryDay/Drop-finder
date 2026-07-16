import { createElement } from "react";
import {
  TypeAwareMarketplaceFeature as BaseTypeAwareMarketplaceFeature,
} from "./TypeAwareMarketplaceFeature";
import {
  MarketplaceFeature as BaseFlowerMarketplaceFeature,
} from "./MarketplaceFeature";
import type { MarketplaceFeatureProps } from "./marketplace-core";

type MarketplaceMountProps = MarketplaceFeatureProps & {
  catalogGenerationId?: string | null;
};

const EMPTY_DETAILS_BY_PRODUCT_ID: NonNullable<MarketplaceFeatureProps["detailsByProductId"]> = Object.freeze({});

const withStableDetails = (props: MarketplaceMountProps): MarketplaceMountProps => ({
  ...props,
  detailsByProductId: props.detailsByProductId ?? EMPTY_DETAILS_BY_PRODUCT_ID,
});

export const TypeAwareMarketplaceFeature = (props: MarketplaceMountProps) =>
  createElement(BaseTypeAwareMarketplaceFeature, withStableDetails(props));

export const FlowerMarketplaceFeature = (props: MarketplaceMountProps) =>
  createElement(BaseFlowerMarketplaceFeature, withStableDetails(props));

export const MarketplaceFeature = TypeAwareMarketplaceFeature;

export const marketplaceFeatureModule = {
  id: "marketplace",
  kind: "primary",
  version: 1,
  mount: MarketplaceFeature,
  capabilities: ["desktop", "mobile", "documents", "keyboard", "multi-product"],
} as const;

export default marketplaceFeatureModule;
export * from "./marketplace-core";
