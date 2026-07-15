import {
  CATALOG_SCHEMA_VERSION,
  GROW_ENVIRONMENTS,
  LINEAGES,
  type CatalogManifest,
  type CatalogPage,
  type EvidenceMetadata,
  type InStockVariant,
  type MarketplaceProduct,
  type ProductDocumentRecord,
  type ValidationIssue,
  type ValidationResult,
} from "./catalog";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === "string";
const isNonEmptyString = (value: unknown): value is string => isString(value) && value.trim().length > 0;
const isFiniteNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isNonNegativeInteger = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 0;
const isPositiveNumber = (value: unknown): value is number => isFiniteNumber(value) && value > 0;
const isNullable = <T>(value: unknown, predicate: (candidate: unknown) => candidate is T): value is T | null =>
  value === null || predicate(value);
const isStringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every(isNonEmptyString);
const isIsoDate = (value: unknown): value is string =>
  isNonEmptyString(value) && !Number.isNaN(Date.parse(value));
const isUrl = (value: unknown): value is string => {
  if (!isNonEmptyString(value)) return false;
  try {
    const parsed = new URL(value, "https://dropfinder.invalid/");
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
};

class Collector {
  readonly issues: ValidationIssue[] = [];

  add(path: string, message: string): void {
    this.issues.push({ path, message });
  }

  expect(path: string, condition: boolean, message: string): void {
    if (!condition) this.add(path, message);
  }
}

const validateEvidence = (value: unknown, path: string, collector: Collector): value is EvidenceMetadata => {
  if (!isRecord(value)) {
    collector.add(path, "must be an evidence object");
    return false;
  }
  collector.expect(`${path}.sourceUrl`, isUrl(value.sourceUrl), "must be a valid HTTP(S) URL");
  collector.expect(`${path}.capturedAt`, isIsoDate(value.capturedAt), "must be an ISO date-time");
  collector.expect(`${path}.field`, isNonEmptyString(value.field), "must be a non-empty field name");
  collector.expect(`${path}.method`, ["source", "derived", "manual"].includes(String(value.method)), "must be source, derived, or manual");
  collector.expect(`${path}.confidence`, ["high", "medium", "low"].includes(String(value.confidence)), "must be high, medium, or low");
  if (value.notes !== undefined) collector.expect(`${path}.notes`, isStringArray(value.notes), "must be an array of non-empty strings");
  return true;
};

const validateEvidenceArray = (value: unknown, path: string, collector: Collector): boolean => {
  if (!Array.isArray(value)) {
    collector.add(path, "must be an evidence array");
    return false;
  }
  value.forEach((entry, index) => validateEvidence(entry, `${path}[${index}]`, collector));
  return true;
};

const validateMoney = (value: unknown, path: string, collector: Collector): boolean => {
  if (!isRecord(value)) {
    collector.add(path, "must be a money object");
    return false;
  }
  collector.expect(`${path}.currency`, value.currency === "USD", "must use USD");
  collector.expect(`${path}.cents`, isNonNegativeInteger(value.cents), "must be a non-negative integer number of cents");
  return true;
};

const validateVariant = (value: unknown, path: string, collector: Collector): value is InStockVariant => {
  if (!isRecord(value)) {
    collector.add(path, "must be an in-stock variant object");
    return false;
  }
  collector.expect(`${path}.id`, isNonEmptyString(value.id), "must be a non-empty ID");
  collector.expect(`${path}.label`, isNonEmptyString(value.label), "must be a non-empty label");
  if (isRecord(value.weight)) {
    collector.expect(`${path}.weight.grams`, isPositiveNumber(value.weight.grams), "must be greater than zero");
    collector.expect(`${path}.weight.display`, isNonEmptyString(value.weight.display), "must be a non-empty display weight");
  } else {
    collector.add(`${path}.weight`, "must be a weight object");
  }
  validateMoney(value.currentPrice, `${path}.currentPrice`, collector);
  if (value.originalPrice !== null) validateMoney(value.originalPrice, `${path}.originalPrice`, collector);
  collector.expect(`${path}.originalPrice`, value.originalPrice === null || isRecord(value.originalPrice), "must be money or null");
  collector.expect(`${path}.discountPercent`, value.discountPercent === null || (isFiniteNumber(value.discountPercent) && value.discountPercent >= 0 && value.discountPercent <= 100), "must be null or between 0 and 100");
  validateMoney(value.pricePerGram, `${path}.pricePerGram`, collector);
  collector.expect(`${path}.productUrl`, isUrl(value.productUrl), "must be a valid HTTP(S) URL");
  collector.expect(`${path}.imageUrl`, isNullable(value.imageUrl, isUrl), "must be a valid HTTP(S) URL or null");
  collector.expect(`${path}.documentIds`, isStringArray(value.documentIds), "must be an array of document IDs");
  collector.expect(`${path}.batchIds`, isStringArray(value.batchIds), "must be an array of batch IDs");
  if (isRecord(value.stock)) {
    collector.expect(`${path}.stock.state`, value.stock.state === "in_stock", "frontend variants must be explicitly in stock");
    collector.expect(`${path}.stock.available`, value.stock.available === true, "frontend variants must be available");
    collector.expect(`${path}.stock.observedAt`, isIsoDate(value.stock.observedAt), "must be an ISO date-time");
  } else {
    collector.add(`${path}.stock`, "must be an explicit in-stock state");
  }
  validateEvidenceArray(value.evidence, `${path}.evidence`, collector);
  return true;
};

const validateDocument = (value: unknown, path: string, collector: Collector): value is ProductDocumentRecord => {
  if (!isRecord(value)) {
    collector.add(path, "must be a document record");
    return false;
  }
  collector.expect(`${path}.id`, isNonEmptyString(value.id), "must be a non-empty ID");
  collector.expect(`${path}.kind`, value.kind === "coa" || value.kind === "terpene", "must be coa or terpene");
  collector.expect(`${path}.title`, isNonEmptyString(value.title), "must be a non-empty title");
  collector.expect(`${path}.url`, isUrl(value.url), "must be a valid HTTP(S) URL");
  collector.expect(`${path}.vendorId`, isNonEmptyString(value.vendorId), "must be a vendor ID");
  collector.expect(`${path}.productId`, isNonEmptyString(value.productId), "must be a product ID");
  collector.expect(`${path}.variantIds`, isStringArray(value.variantIds), "must be an array of variant IDs");
  collector.expect(`${path}.batchIds`, isStringArray(value.batchIds), "must be an array of batch IDs");
  collector.expect(`${path}.publishedAt`, isNullable(value.publishedAt, isIsoDate), "must be an ISO date-time or null");
  validateEvidenceArray(value.evidence, `${path}.evidence`, collector);
  return true;
};

const duplicateValues = (values: readonly string[]): string[] => {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
};

export const validateMarketplaceProduct = (input: unknown): ValidationResult<MarketplaceProduct> => {
  const collector = new Collector();
  if (!isRecord(input)) return { ok: false, issues: [{ path: "$", message: "must be a marketplace product object" }] };

  collector.expect("schemaVersion", input.schemaVersion === CATALOG_SCHEMA_VERSION, `must equal ${CATALOG_SCHEMA_VERSION}`);
  collector.expect("id", isNonEmptyString(input.id), "must be a non-empty ID");

  if (isRecord(input.identity)) {
    collector.expect("identity.vendorProductId", isNonEmptyString(input.identity.vendorProductId), "must be a non-empty ID");
    collector.expect("identity.canonicalStrainId", isNonEmptyString(input.identity.canonicalStrainId), "must be a non-empty ID");
    collector.expect("identity.canonicalProductId", isNonEmptyString(input.identity.canonicalProductId), "must be a non-empty ID");
  } else collector.add("identity", "must be a canonical identity object");

  if (isRecord(input.vendor)) {
    collector.expect("vendor.id", isNonEmptyString(input.vendor.id), "must be a non-empty ID");
    collector.expect("vendor.name", isNonEmptyString(input.vendor.name), "must be a non-empty name");
    collector.expect("vendor.faviconUrl", isNullable(input.vendor.faviconUrl, isUrl), "must be a valid HTTP(S) URL or null");
    collector.expect("vendor.ageGate", ["none", "soft", "hard", "unknown"].includes(String(input.vendor.ageGate)), "must be none, soft, hard, or unknown");
    validateEvidenceArray(input.vendor.evidence, "vendor.evidence", collector);
  } else collector.add("vendor", "must be a vendor object");

  collector.expect("strainName", isNonEmptyString(input.strainName), "must be a non-empty Strain Name");
  collector.expect("lineage", LINEAGES.includes(input.lineage as never), "must be a supported Lineage");

  if (!Array.isArray(input.variants) || input.variants.length === 0) {
    collector.add("variants", "must contain at least one explicitly in-stock variant");
  } else {
    input.variants.forEach((variant, index) => validateVariant(variant, `variants[${index}]`, collector));
    const IDs = input.variants.filter(isRecord).map((variant) => String(variant.id));
    for (const duplicate of duplicateValues(IDs)) collector.add("variants", `contains duplicate variant ID ${duplicate}`);
  }

  if (isRecord(input.totalThc)) {
    collector.expect("totalThc.calculatedPercent", isNullable(input.totalThc.calculatedPercent, isFiniteNumber), "must be a finite number or null");
    collector.expect("totalThc.roundedDisplayPercent", isNullable(input.totalThc.roundedDisplayPercent, isNonNegativeInteger), "must be a whole non-negative percent or null");
    collector.expect("totalThc.method", ["reported-total-thc", "thca-conversion", "unavailable"].includes(String(input.totalThc.method)), "must be a supported Total THC method");
    collector.expect("totalThc.formula", input.totalThc.formula === null || input.totalThc.formula === "thca * 0.877 + delta9_thc", "must be the approved formula or null");
    if (isRecord(input.totalThc.raw)) {
      for (const field of ["thcaPercent", "delta9ThcPercent", "reportedTotalThcPercent"] as const) {
        collector.expect(`totalThc.raw.${field}`, isNullable(input.totalThc.raw[field], isFiniteNumber), "must be a finite number or null");
      }
    } else collector.add("totalThc.raw", "must contain internal raw cannabinoid values");
    if (isFiniteNumber(input.totalThc.calculatedPercent) && isNonNegativeInteger(input.totalThc.roundedDisplayPercent)) {
      collector.expect("totalThc.roundedDisplayPercent", input.totalThc.roundedDisplayPercent === Math.round(input.totalThc.calculatedPercent), "must be the rounded whole-percent display value");
    }
    if (input.totalThc.method === "thca-conversion") {
      collector.expect("totalThc.formula", input.totalThc.formula === "thca * 0.877 + delta9_thc", "is required for THCA conversion");
    }
    validateEvidenceArray(input.totalThc.provenance, "totalThc.provenance", collector);
  } else collector.add("totalThc", "must be a Total THC measurement object");

  if (input.rating !== null) {
    if (isRecord(input.rating)) {
      collector.expect("rating.value", isFiniteNumber(input.rating.value) && input.rating.value >= 0 && input.rating.value <= 5, "must be between 0 and 5");
      collector.expect("rating.reviewCount", isNonNegativeInteger(input.rating.reviewCount), "must be a non-negative integer");
    } else collector.add("rating", "must be a rating object or null");
  }

  collector.expect("effects", isStringArray(input.effects), "must be an array of non-empty effect names");
  collector.expect("growEnvironment", GROW_ENVIRONMENTS.includes(input.growEnvironment as never), "must be indoor, outdoor, greenhouse, or unknown");

  if (Array.isArray(input.documents)) {
    input.documents.forEach((document, index) => validateDocument(document, `documents[${index}]`, collector));
    const IDs = input.documents.filter(isRecord).map((document) => String(document.id));
    for (const duplicate of duplicateValues(IDs)) collector.add("documents", `contains duplicate document ID ${duplicate}`);
  } else collector.add("documents", "must be a document array");

  validateEvidenceArray(input.evidence, "evidence", collector);

  if (collector.issues.length > 0) return { ok: false, issues: collector.issues };
  return { ok: true, value: input as unknown as MarketplaceProduct };
};

export const validateCatalogManifest = (input: unknown): ValidationResult<CatalogManifest> => {
  const collector = new Collector();
  if (!isRecord(input)) return { ok: false, issues: [{ path: "$", message: "must be a catalog manifest object" }] };
  collector.expect("schemaVersion", input.schemaVersion === CATALOG_SCHEMA_VERSION, `must equal ${CATALOG_SCHEMA_VERSION}`);
  collector.expect("catalogVersion", isNonEmptyString(input.catalogVersion), "must be a non-empty version");
  collector.expect("generatedAt", isIsoDate(input.generatedAt), "must be an ISO date-time");
  if (isRecord(input.index)) {
    collector.expect("index.url", isUrl(input.index.url), "must be a valid relative or HTTP(S) URL");
    collector.expect("index.sha256", isNonEmptyString(input.index.sha256), "must contain a digest");
    collector.expect("index.generatedAt", isIsoDate(input.index.generatedAt), "must be an ISO date-time");
    collector.expect("index.productCount", isNonNegativeInteger(input.index.productCount), "must be a non-negative integer");
    collector.expect("index.pageCount", isNonNegativeInteger(input.index.pageCount), "must be a non-negative integer");
  } else collector.add("index", "must be index metadata");
  if (Array.isArray(input.pages)) {
    input.pages.forEach((page, index) => {
      const path = `pages[${index}]`;
      if (!isRecord(page)) {
        collector.add(path, "must be page metadata");
        return;
      }
      collector.expect(`${path}.id`, isNonEmptyString(page.id), "must be a non-empty ID");
      collector.expect(`${path}.url`, isUrl(page.url), "must be a valid relative or HTTP(S) URL");
      collector.expect(`${path}.sha256`, isNonEmptyString(page.sha256), "must contain a digest");
      collector.expect(`${path}.productCount`, isNonNegativeInteger(page.productCount), "must be a non-negative integer");
      collector.expect(`${path}.firstProductKey`, isNullable(page.firstProductKey, isNonEmptyString), "must be a product key or null");
      collector.expect(`${path}.lastProductKey`, isNullable(page.lastProductKey, isNonEmptyString), "must be a product key or null");
    });
  } else collector.add("pages", "must be an array of page metadata");
  if (collector.issues.length > 0) return { ok: false, issues: collector.issues };
  return { ok: true, value: input as unknown as CatalogManifest };
};

export const validateCatalogPage = (input: unknown): ValidationResult<CatalogPage> => {
  const collector = new Collector();
  if (!isRecord(input)) return { ok: false, issues: [{ path: "$", message: "must be a catalog page object" }] };
  collector.expect("schemaVersion", input.schemaVersion === CATALOG_SCHEMA_VERSION, `must equal ${CATALOG_SCHEMA_VERSION}`);
  collector.expect("catalogVersion", isNonEmptyString(input.catalogVersion), "must be a non-empty version");
  if (!isRecord(input.page)) collector.add("page", "must be page metadata");
  if (!Array.isArray(input.products)) collector.add("products", "must be a product array");
  else input.products.forEach((product, index) => {
    const result = validateMarketplaceProduct(product);
    if (!result.ok) result.issues.forEach((issue) => collector.add(`products[${index}].${issue.path}`, issue.message));
  });
  if (collector.issues.length > 0) return { ok: false, issues: collector.issues };
  return { ok: true, value: input as unknown as CatalogPage };
};
