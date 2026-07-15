import { createElement, type ComponentType } from "react";
import {
  FEATURE_API_VERSION,
  FEATURE_CAPABILITIES,
  type AppSlot,
  type FeatureCapability,
  type FeatureDiagnostic,
  type FeatureModule,
  type FeatureSlots,
  type MarketplaceRootSlotProps,
  type ResolvedFeatureRegistry,
} from "./featureContract";
import { RuntimeCapabilityRegistry, type CapabilityRegistrationTarget } from "./capabilityRegistry";

type UnknownRecord = Record<string, unknown>;
type Registrar = (registry: CapabilityRegistrationTarget) => unknown;

const SLOT_CAPABILITY: Record<AppSlot, FeatureCapability | null> = {
  marketplaceRoot: "marketplace.root",
  search: "marketplace.search",
  filters: "marketplace.filters",
  resultHeader: "marketplace.result-header",
  marketplaceSurface: "marketplace.surface",
  overlay: null,
};

const SUPPORTED_SLOTS = new Set<AppSlot>([
  "marketplaceRoot",
  "search",
  "filters",
  "resultHeader",
  "marketplaceSurface",
  "overlay",
]);

const REGISTRAR_EXPORTS = ["registerFeatureCapabilities", "registerPlatformCapabilities"] as const;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isComponent = (value: unknown): boolean =>
  typeof value === "function" || (isRecord(value) && ["react.memo", "react.forward_ref"].some((name) => String(value.$$typeof).includes(name)));

const unwrapModule = (value: unknown): unknown => {
  if (!isRecord(value)) return value;
  if ("default" in value) return value.default;
  if ("feature" in value) return value.feature;
  if ("id" in value || "kind" in value || "slots" in value || "mount" in value) return value;
  return null;
};

const registerCapabilities = (source: string, value: unknown, registry: RuntimeCapabilityRegistry): void => {
  if (!isRecord(value)) return;
  const seen = new Set<Registrar>();
  for (const exportName of REGISTRAR_EXPORTS) {
    const candidate = value[exportName];
    if (typeof candidate !== "function" || seen.has(candidate as Registrar)) continue;
    seen.add(candidate as Registrar);
    registry.registerFrom(source, candidate as Registrar);
  }
};

const adaptLegacyMarketplaceModule = (
  source: string,
  candidate: UnknownRecord,
): { module: FeatureModule | null; diagnostics: FeatureDiagnostic[] } | null => {
  if (candidate.kind !== "primary" || candidate.version !== 1) return null;

  const diagnostics: FeatureDiagnostic[] = [];
  const validId = typeof candidate.id === "string" && /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(candidate.id);
  const validMount = isComponent(candidate.mount);
  const validCapabilities = Array.isArray(candidate.capabilities) && candidate.capabilities.every((capability) => typeof capability === "string");
  if (!validId) diagnostics.push({ source, code: "malformed-module", message: "Legacy primary marketplace id is invalid." });
  if (!validMount) diagnostics.push({ source, code: "malformed-module", message: "Legacy primary marketplace mount must be a React component." });
  if (!validCapabilities) diagnostics.push({ source, code: "malformed-module", message: "Legacy primary marketplace capabilities must be strings." });
  if (diagnostics.length > 0) return { module: null, diagnostics };

  const Mount = candidate.mount as ComponentType<Record<string, unknown>>;
  const LegacyMarketplaceRoot = ({ capabilities }: MarketplaceRootSlotProps) => {
    const supplied = capabilities.getCapability<unknown>("marketplace.props", 1);
    const suppliedProps = isRecord(supplied) ? supplied : {};
    const Provider = suppliedProps.Provider;
    if (isComponent(Provider)) {
      return createElement(
        Provider as ComponentType<{
          mount: typeof Mount;
          capabilities: MarketplaceRootSlotProps["capabilities"];
        }>,
        { mount: Mount, capabilities },
      );
    }
    const products = Array.isArray(suppliedProps.products) ? suppliedProps.products : [];
    return createElement(Mount, { ...suppliedProps, products, capabilities });
  };

  return {
    module: {
      apiVersion: FEATURE_API_VERSION,
      id: candidate.id as string,
      kind: "marketplace",
      order: 100,
      capabilities: ["marketplace.root"],
      slots: { marketplaceRoot: LegacyMarketplaceRoot },
    },
    diagnostics: [{
      source,
      code: "legacy-module-adapted",
      message: "Adapted the issue #8 primary-v1 whole-marketplace module to marketplace.root.",
    }],
  };
};

const validateModule = (source: string, value: unknown): { module: FeatureModule | null; diagnostics: FeatureDiagnostic[] } => {
  const diagnostics: FeatureDiagnostic[] = [];
  const candidate = unwrapModule(value);
  if (candidate === null) return { module: null, diagnostics };
  if (!isRecord(candidate)) {
    return {
      module: null,
      diagnostics: [{ source, code: "malformed-module", message: "Feature export must be an object." }],
    };
  }

  const legacy = adaptLegacyMarketplaceModule(source, candidate);
  if (legacy) return legacy;

  const validId = typeof candidate.id === "string" && /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(candidate.id);
  const validKind = candidate.kind === "marketplace" || candidate.kind === "enhancer";
  const validOrder = Number.isInteger(candidate.order) && Number(candidate.order) >= 0;
  const validCapabilities =
    Array.isArray(candidate.capabilities) &&
    candidate.capabilities.every((capability) => FEATURE_CAPABILITIES.includes(capability as FeatureCapability)) &&
    new Set(candidate.capabilities).size === candidate.capabilities.length;
  const validSlots = isRecord(candidate.slots) && Object.entries(candidate.slots).every(([slot, component]) =>
    SUPPORTED_SLOTS.has(slot as AppSlot) && isComponent(component),
  );

  if (candidate.apiVersion !== FEATURE_API_VERSION) diagnostics.push({ source, code: "malformed-module", message: `apiVersion must be ${FEATURE_API_VERSION}.` });
  if (!validId) diagnostics.push({ source, code: "malformed-module", message: "id must be a stable lowercase dotted or dashed identifier." });
  if (!validKind) diagnostics.push({ source, code: "malformed-module", message: "kind must be marketplace or enhancer." });
  if (!validOrder) diagnostics.push({ source, code: "malformed-module", message: "order must be a non-negative integer." });
  if (!validCapabilities) diagnostics.push({ source, code: "malformed-module", message: "capabilities must be unique supported capability names." });
  if (!validSlots) diagnostics.push({ source, code: "malformed-module", message: "slots must contain only renderable supported slot components." });

  if (diagnostics.length > 0) return { module: null, diagnostics };

  const module = candidate as unknown as FeatureModule;
  if (module.kind === "marketplace") {
    const hasRoot = module.capabilities.includes("marketplace.root") && Boolean(module.slots.marketplaceRoot);
    const hasSurface = module.capabilities.includes("marketplace.surface") && Boolean(module.slots.marketplaceSurface);
    if (!hasRoot && !hasSurface) {
      diagnostics.push({ source, code: "capability-mismatch", message: "A marketplace feature must implement marketplace.root or marketplace.surface." });
    }
    if (hasRoot && [module.slots.search, module.slots.filters, module.slots.resultHeader, module.slots.marketplaceSurface].some(Boolean)) {
      diagnostics.push({ source, code: "capability-mismatch", message: "A marketplace.root provider may not also provide decomposed marketplace slots." });
    }
  }

  for (const [slot, component] of Object.entries(module.slots) as [AppSlot, unknown][]) {
    if (!component) continue;
    const requiredCapability = SLOT_CAPABILITY[slot];
    if (requiredCapability && !module.capabilities.includes(requiredCapability)) {
      diagnostics.push({ source, code: "capability-mismatch", message: `${slot} requires capability ${requiredCapability}.` });
    }
  }

  if (diagnostics.length > 0) return { module: null, diagnostics };
  return { module, diagnostics: [] };
};

export const resolveFeatureModules = (records: Record<string, unknown>): ResolvedFeatureRegistry => {
  const diagnostics: FeatureDiagnostic[] = [];
  const capabilityRegistry = new RuntimeCapabilityRegistry();
  const orderedRecords = Object.entries(records).sort(([left], [right]) => left.localeCompare(right));

  for (const [source, value] of orderedRecords) registerCapabilities(source, value, capabilityRegistry);
  diagnostics.push(...capabilityRegistry.diagnostics);

  const validated = orderedRecords
    .map(([source, value]) => {
      const result = validateModule(source, value);
      diagnostics.push(...result.diagnostics);
      return { source, module: result.module };
    })
    .filter((entry): entry is { source: string; module: FeatureModule } => entry.module !== null);

  const byId = new Map<string, { source: string; module: FeatureModule }[]>();
  for (const entry of validated) {
    const group = byId.get(entry.module.id) ?? [];
    group.push(entry);
    byId.set(entry.module.id, group);
  }

  const unique = validated.filter((entry) => {
    const group = byId.get(entry.module.id) ?? [];
    if (group.length === 1) return true;
    if (group[0] === entry) diagnostics.push({
      source: group.map((item) => item.source).join(", "),
      code: "duplicate-id",
      message: `Duplicate feature id ${entry.module.id}; all copies were rejected.`,
    });
    return false;
  });

  const marketplaces = unique.filter((entry) => entry.module.kind === "marketplace");
  const withoutAmbiguousMarketplace = marketplaces.length <= 1
    ? unique
    : unique.filter((entry) => entry.module.kind !== "marketplace");
  if (marketplaces.length > 1) diagnostics.push({
    source: marketplaces.map((entry) => entry.source).join(", "),
    code: "duplicate-marketplace",
    message: "More than one primary marketplace feature was registered; all marketplace modules were rejected.",
  });

  const sorted = withoutAmbiguousMarketplace
    .map((entry) => entry.module)
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));

  const slots: FeatureSlots = {};
  const slotOwners = new Map<AppSlot, FeatureModule[]>();
  for (const module of sorted) {
    for (const [slot, component] of Object.entries(module.slots) as [AppSlot, FeatureSlots[AppSlot]][]) {
      if (!component) continue;
      const owners = slotOwners.get(slot) ?? [];
      owners.push(module);
      slotOwners.set(slot, owners);
    }
  }

  for (const [slot, owners] of slotOwners) {
    if (owners.length > 1) {
      diagnostics.push({
        source: owners.map((owner) => owner.id).join(", "),
        code: "duplicate-slot",
        message: `Slot ${slot} has multiple providers and was left unmounted.`,
      });
      continue;
    }
    const component = owners[0]?.slots[slot];
    if (component) Object.assign(slots, { [slot]: component });
  }

  return {
    modules: sorted,
    slots,
    capabilities: capabilityRegistry,
    diagnostics,
    primaryMarketplace: sorted.find((module) => module.kind === "marketplace") ?? null,
  };
};
