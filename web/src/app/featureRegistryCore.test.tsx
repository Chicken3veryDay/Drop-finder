import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type { CapabilityRegistrationTarget } from "./capabilityRegistry";
import { FEATURE_API_VERSION, type FeatureModule } from "./featureContract";
import { resolveFeatureModules } from "./featureRegistryCore";

const Surface = (): ReactNode => <div>Marketplace</div>;
const Search = (): ReactNode => <input aria-label="Feature search" />;

const feature = (overrides: Partial<FeatureModule> = {}): FeatureModule => ({
  apiVersion: FEATURE_API_VERSION,
  id: "marketplace.primary",
  kind: "marketplace",
  order: 10,
  capabilities: ["marketplace.surface"],
  slots: { marketplaceSurface: Surface },
  ...overrides,
});

describe("resolveFeatureModules", () => {
  it("orders modules deterministically by order then ID", () => {
    const registry = resolveFeatureModules({
      z: { default: feature({ id: "enhancer.z", kind: "enhancer", order: 20, capabilities: [], slots: {} }) },
      m: { default: feature() },
      a: { default: feature({ id: "enhancer.a", kind: "enhancer", order: 20, capabilities: [], slots: {} }) },
    });
    expect(registry.modules.map((module) => module.id)).toEqual(["marketplace.primary", "enhancer.a", "enhancer.z"]);
  });

  it("fails closed when IDs are duplicated", () => {
    const registry = resolveFeatureModules({ left: { default: feature() }, right: { default: feature() } });
    expect(registry.modules).toHaveLength(0);
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ code: "duplicate-id" }));
  });

  it("fails closed when more than one primary marketplace is registered", () => {
    const registry = resolveFeatureModules({
      left: { default: feature({ id: "marketplace.left" }) },
      right: { default: feature({ id: "marketplace.right" }) },
    });
    expect(registry.primaryMarketplace).toBeNull();
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ code: "duplicate-marketplace" }));
  });

  it("rejects malformed modules and capability mismatches", () => {
    const registry = resolveFeatureModules({
      malformed: { default: { id: "Bad ID" } },
      mismatch: { default: feature({ id: "enhancer.search", kind: "enhancer", capabilities: [], slots: { search: Search } }) },
    });
    expect(registry.modules).toHaveLength(0);
    expect(registry.diagnostics.map((diagnostic) => diagnostic.code)).toEqual(expect.arrayContaining(["malformed-module", "capability-mismatch"]));
  });

  it("leaves a duplicated slot unmounted instead of choosing by accident", () => {
    const registry = resolveFeatureModules({
      marketplace: { default: feature() },
      first: { default: feature({ id: "enhancer.first", kind: "enhancer", order: 20, capabilities: ["marketplace.search"], slots: { search: Search } }) },
      second: { default: feature({ id: "enhancer.second", kind: "enhancer", order: 30, capabilities: ["marketplace.search"], slots: { search: Search } }) },
    });
    expect(registry.slots.search).toBeUndefined();
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ code: "duplicate-slot" }));
  });

  it("adapts the exact issue #8 primary-v1 module shape to a composite marketplace root", () => {
    const LegacyMarketplace = (): ReactNode => <div>Legacy marketplace</div>;
    const registry = resolveFeatureModules({
      marketplace: {
        default: {
          id: "marketplace",
          kind: "primary",
          version: 1,
          mount: LegacyMarketplace,
          capabilities: ["desktop", "mobile", "documents", "keyboard"],
        },
      },
    });

    expect(registry.primaryMarketplace?.id).toBe("marketplace");
    expect(registry.slots.marketplaceRoot).toBeDefined();
    expect(registry.diagnostics).toContainEqual(expect.objectContaining({ code: "legacy-module-adapted" }));
  });

  it("runs issue #9 style capability registrars without treating them as malformed modules", () => {
    const catalog = { id: "catalog" };
    const registry = resolveFeatureModules({
      platform: {
        registerPlatformCapabilities(target: CapabilityRegistrationTarget) {
          target.registerCapability("platform.catalog", { contractVersion: 1, instance: catalog });
        },
      },
    });

    expect(registry.capabilities.getCapability("platform.catalog", 1)).toBe(catalog);
    expect(registry.diagnostics.some((diagnostic) => diagnostic.code === "malformed-module")).toBe(false);
  });
});
