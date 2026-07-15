import type { ComponentType, RefObject } from "react";
import type { CapabilityReader } from "./capabilityRegistry";

export const FEATURE_API_VERSION = "1.0.0" as const;

export const FEATURE_CAPABILITIES = [
  "marketplace.root",
  "marketplace.surface",
  "marketplace.search",
  "marketplace.filters",
  "marketplace.result-header",
  "platform.catalog",
  "platform.query",
  "platform.documents",
  "platform.document-overlay",
  "platform.virtualization",
  "platform.pwa",
  "platform.pwa-status",
  "platform.mobile-rendering",
] as const;

export type FeatureCapability = (typeof FEATURE_CAPABILITIES)[number];
export type FeatureKind = "marketplace" | "enhancer";
export type AppSlot = "marketplaceRoot" | "search" | "filters" | "resultHeader" | "marketplaceSurface" | "overlay";

export interface CapabilityAwareSlotProps {
  capabilities: CapabilityReader;
}

export type MarketplaceRootSlotProps = CapabilityAwareSlotProps;

export interface SearchSlotProps extends CapabilityAwareSlotProps {
  value: string;
  onValueChange: (value: string) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}

export interface FilterSlotProps extends CapabilityAwareSlotProps {
  searchValue: string;
}

export interface ResultHeaderSlotProps extends CapabilityAwareSlotProps {
  searchValue: string;
}

export interface MarketplaceSurfaceSlotProps extends CapabilityAwareSlotProps {
  searchValue: string;
}

export interface OverlaySlotProps extends CapabilityAwareSlotProps {
  portalElement: HTMLElement | null;
}

export interface FeatureSlots {
  marketplaceRoot?: ComponentType<MarketplaceRootSlotProps>;
  search?: ComponentType<SearchSlotProps>;
  filters?: ComponentType<FilterSlotProps>;
  resultHeader?: ComponentType<ResultHeaderSlotProps>;
  marketplaceSurface?: ComponentType<MarketplaceSurfaceSlotProps>;
  overlay?: ComponentType<OverlaySlotProps>;
}

export interface FeatureModule {
  apiVersion: typeof FEATURE_API_VERSION;
  id: string;
  kind: FeatureKind;
  order: number;
  capabilities: readonly FeatureCapability[];
  slots: FeatureSlots;
}

export interface FeatureDiagnostic {
  source: string;
  code:
    | "malformed-module"
    | "duplicate-id"
    | "duplicate-marketplace"
    | "duplicate-slot"
    | "capability-mismatch"
    | "legacy-module-adapted"
    | "malformed-capability"
    | "duplicate-capability"
    | "registrar-error";
  message: string;
}

export interface ResolvedFeatureRegistry {
  modules: readonly FeatureModule[];
  slots: FeatureSlots;
  capabilities: CapabilityReader;
  diagnostics: readonly FeatureDiagnostic[];
  primaryMarketplace: FeatureModule | null;
}

export const defineFeature = (feature: FeatureModule): FeatureModule => feature;
