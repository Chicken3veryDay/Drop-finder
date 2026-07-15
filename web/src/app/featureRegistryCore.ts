import {
  FEATURE_API_VERSION,
  FEATURE_CAPABILITIES,
  type AppSlot,
  type FeatureCapability,
  type FeatureDiagnostic,
  type FeatureModule,
  type FeatureSlots,
  type ResolvedFeatureRegistry,
} from "./featureContract";

type UnknownRecord = Record<string, unknown>;

const SLOT_CAPABILITY: Record<AppSlot, FeatureCapability | null> = {
  search: "marketplace.search",
  filters: "marketplace.filters",
  resultHeader: "marketplace.result-header",
  marketplaceSurface: "marketplace.surface",
  overlay: null,
};

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isComponent = (value: unknown): boolean =>
  typeof value === "function" || (isRecord(value) && ["react.memo", "react.forward_ref"].some((name) => String(value.$$typeof).includes(name)));

const unwrapModule = (value: unknown): unknown => {
  if (!isRecord(value)) return value;
  if ("default" in value) return value.default;
  if ("feature" in value) return value.feature;
  return value;
};

const validateModule = (source: string, value: unknown): { module: FeatureModule | null; diagnostics: FeatureDiagnostic[] } => {
  const diagnostics: FeatureDiagnostic[] = [];
  const candidate = unwrapModule(value);
  if (!isRecord(candidate)) {
    return {
      module: null,
      diagnostics: [{ source, code: "malformed-module", message: "Feature export must be an object." }],
    };
  }

  const validId = typeof candidate.id === "string" && /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/.test(candidate.id);
  const validKind = candidate.kind === "marketplace" || candidate.kind === "enhancer";
  const validOrder = Number.isInteger(candidate.order) && Number(candidate.order) >= 0;
  const validCapabilities =
    Array.isArray(candidate.capabilities) &&
    candidate.capabilities.every((capability) => FEATURE_CAPABILITIES.includes(capability as FeatureCapability)) &&
    new Set(candidate.capabilities).size === candidate.capabilities.length;
  const validSlots = isRecord(candidate.slots) && Object.entries(candidate.slots).every(([slot, component]) =>
    ["search", "filters", "resultHeader", "marketplaceSurface", "overlay"].includes(slot) && isComponent(component),
  );

  if (candidate.apiVersion !== FEATURE_API_VERSION) diagnostics.push({ source, code: "malformed-module", message: `apiVersion must be ${FEATURE_API_VERSION}.` });
  if (!validId) diagnostics.push({ source, code: "malformed-module", message: "id must be a stable lowercase dotted or dashed identifier." });
  if (!validKind) diagnostics.push({ source, code: "malformed-module", message: "kind must be marketplace or enhancer." });
  if (!validOrder) diagnostics.push({ source, code: "malformed-module", message: "order must be a non-negative integer." });
  if (!validCapabilities) diagnostics.push({ source, code: "malformed-module", message: "capabilities must be unique supported capability names." });
  if (!validSlots) diagnostics.push({ source, code: "malformed-module", message: "slots must contain only renderable supported slot components." });

  if (diagnostics.length > 0) return { module: null, diagnostics };

  const module = candidate as unknown as FeatureModule;
  if (module.kind === "marketplace" && (!module.capabilities.includes("marketplace.surface") || !module.slots.marketplaceSurface)) {
    return {
      module: null,
      diagnostics: [{ source, code: "capability-mismatch", message: "A marketplace feature must declare and implement marketplace.surface." }],
    };
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
  const validated = Object.entries(records)
    .sort(([left], [right]) => left.localeCompare(right))
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
    diagnostics,
    primaryMarketplace: sorted.find((module) => module.kind === "marketplace") ?? null,
  };
};
