export const CATALOG_SCHEMA_VERSION = "1.0.0" as const;

export const LINEAGES = [
  "indica",
  "indica-leaning-hybrid",
  "hybrid",
  "sativa-leaning-hybrid",
  "sativa",
  "unknown",
] as const;

export type Lineage = (typeof LINEAGES)[number];

export const GROW_ENVIRONMENTS = ["indoor", "outdoor", "greenhouse", "unknown"] as const;
export type GrowEnvironment = (typeof GROW_ENVIRONMENTS)[number];

export type EvidenceConfidence = "high" | "medium" | "low";
export type EvidenceMethod = "source" | "derived" | "manual";

export interface EvidenceMetadata {
  sourceUrl: string;
  capturedAt: string;
  field: string;
  method: EvidenceMethod;
  confidence: EvidenceConfidence;
  notes?: readonly string[];
}

export type AgeGateClassification = "none" | "soft" | "hard" | "unknown";

export interface VendorSummary {
  id: string;
  name: string;
  faviconUrl: string | null;
  ageGate: AgeGateClassification;
  evidence: readonly EvidenceMetadata[];
}

export interface Money {
  currency: "USD";
  cents: number;
}

export interface InStockVariant {
  id: string;
  label: string;
  weight: {
    grams: number;
    display: string;
  };
  currentPrice: Money;
  originalPrice: Money | null;
  discountPercent: number | null;
  pricePerGram: Money;
  productUrl: string;
  imageUrl: string | null;
  documentIds: readonly string[];
  batchIds: readonly string[];
  stock: {
    state: "in_stock";
    available: true;
    observedAt: string;
  };
  evidence: readonly EvidenceMetadata[];
}

export type TotalThcMethod = "reported-total-thc" | "thca-conversion" | "unavailable";

export interface TotalThcMeasurement {
  calculatedPercent: number | null;
  roundedDisplayPercent: number | null;
  raw: {
    thcaPercent: number | null;
    delta9ThcPercent: number | null;
    reportedTotalThcPercent: number | null;
  };
  method: TotalThcMethod;
  formula: "thca * 0.877 + delta9_thc" | null;
  provenance: readonly EvidenceMetadata[];
}

export interface RatingSummary {
  value: number;
  reviewCount: number;
}

export type DocumentKind = "coa" | "terpene";

export interface ProductDocumentRecord {
  id: string;
  kind: DocumentKind;
  title: string;
  url: string;
  vendorId: string;
  productId: string;
  variantIds: readonly string[];
  batchIds: readonly string[];
  publishedAt: string | null;
  evidence: readonly EvidenceMetadata[];
}

export interface CanonicalProductIdentity {
  vendorProductId: string;
  canonicalStrainId: string;
  canonicalProductId: string;
}

export interface MarketplaceProduct {
  schemaVersion: typeof CATALOG_SCHEMA_VERSION;
  id: string;
  identity: CanonicalProductIdentity;
  vendor: VendorSummary;
  strainName: string;
  lineage: Lineage;
  variants: readonly [InStockVariant, ...InStockVariant[]];
  totalThc: TotalThcMeasurement;
  rating: RatingSummary | null;
  effects: readonly string[];
  growEnvironment: GrowEnvironment;
  documents: readonly ProductDocumentRecord[];
  evidence: readonly EvidenceMetadata[];
}

export interface CatalogIndexMetadata {
  url: string;
  sha256: string;
  generatedAt: string;
  productCount: number;
  pageCount: number;
}

export interface CatalogPageMetadata {
  id: string;
  url: string;
  sha256: string;
  productCount: number;
  firstProductKey: string | null;
  lastProductKey: string | null;
}

export interface CatalogManifest {
  schemaVersion: typeof CATALOG_SCHEMA_VERSION;
  catalogVersion: string;
  generatedAt: string;
  index: CatalogIndexMetadata;
  pages: readonly CatalogPageMetadata[];
}

export interface CatalogPage {
  schemaVersion: typeof CATALOG_SCHEMA_VERSION;
  catalogVersion: string;
  page: CatalogPageMetadata;
  products: readonly MarketplaceProduct[];
}

export interface ValidationIssue {
  path: string;
  message: string;
}

export type ValidationResult<T> =
  | { ok: true; value: T }
  | { ok: false; issues: readonly ValidationIssue[] };
