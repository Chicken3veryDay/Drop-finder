import type { ComponentType, RefObject } from "react";

export const FEATURE_API_VERSION = "1.0.0" as const;

export const FEATURE_CAPABILITIES = [
  "marketplace.surface",
  "marketplace.search",
  "marketplace.filters",
  "marketplace.result-header",
  "platform.document-overlay",
  "platform.virtualization",
  "platform.pwa-status",
  "platform.mobile-rendering",
] as const;

export type FeatureCapability = (typeof FEATURE_CAPABILITIES)[number];
export type FeatureKind = "marketplace" | "enhancer";
export type AppSlot = "search" | "filters" | "resultHeader" | "marketplaceSurface" | "overlay";

export interface SearchSlotProps {
  value: string;
  onValueChange: (value: string) => void;
  inputRef: RefObject<HTMLInputElement | null>;
}

export interface FilterSlotProps {
  searchValue: string;
}

export interface ResultHeaderSlotProps {
  searchValue: string;
}

export interface MarketplaceSurfaceSlotProps {
  searchValue: string;
}

export interface OverlaySlotProps {
  portalElement: HTMLElement | null;
}

export interface FeatureSlots {
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
    | "capability-mismatch";
  message: string;
}

export interface ResolvedFeatureRegistry {
  modules: readonly FeatureModule[];
  slots: FeatureSlots;
  diagnostics: readonly FeatureDiagnostic[];
  primaryMarketplace: FeatureModule | null;
}

export const defineFeature = (feature: FeatureModule): FeatureModule => feature;
