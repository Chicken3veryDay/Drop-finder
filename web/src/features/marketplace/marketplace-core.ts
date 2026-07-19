import type { ReactNode } from "react";

export const LINEAGES = [
  "indica",
  "indica_leaning_hybrid",
  "hybrid",
  "sativa_leaning_hybrid",
  "sativa",
  "unknown",
] as const;

export type Lineage = (typeof LINEAGES)[number];

export const SORT_OPTIONS = [
  "lowest_price",
  "highest_price",
  "lowest_price_per_gram",
  "highest_price_per_gram",
  "strain_az",
  "strain_za",
  "vendor_az",
  "vendor_za",
] as const;

export type SortOption = (typeof SORT_OPTIONS)[number];
export type DocumentKind = "coa" | "terpene";
export type DocumentFormat = "pdf" | "image" | "html" | "unsupported";
export type GrowEnvironment = "indoor" | "outdoor" | "greenhouse" | "unknown";

export interface MarketplaceDocument {
  id: string;
  kind: DocumentKind;
  url: string;
  format: DocumentFormat;
  title?: string | null;
  mimeType?: string | null;
}

export interface MarketplaceVariant {
  id: string;
  grams: number;
  sourceWeightLabel: string;
  currentPrice: number;
  originalPrice?: number | null;
  pricePerGram: number;
  inStock: true;
  productUrl: string;
  imageUrl?: string | null;
  coa?: MarketplaceDocument | null;
  terpeneDocument?: MarketplaceDocument | null;
}

export interface MarketplaceProduct {
  id: string;
  vendorId: string;
  vendorName: string;
  vendorFaviconUrl?: string | null;
  strainName: string;
  lineage: Lineage;
  totalThcDisplay?: number | null;
  rating?: number | null;
  reviewCount?: number | null;
  variants: readonly MarketplaceVariant[];
}

export interface MarketplaceProductDetail {
  productId: string;
  imageUrl?: string | null;
  effects?: readonly string[] | null;
  growEnvironment: GrowEnvironment;
}

export interface NumericRange {
  min?: number | null;
  max?: number | null;
}

export interface MarketplaceFilters {
  search: string;
  vendorIds: readonly string[];
  lineages: readonly Lineage[];
  totalThc: NumericRange;
  weight: NumericRange;
  price: NumericRange;
  pricePerGram: NumericRange;
}

export interface MarketplaceRowProjection {
  product: MarketplaceProduct;
  activeVariant: MarketplaceVariant;
  availableSizeCount: number;
  stableIndex: number;
}

export interface MarketplaceQueryResult {
  rows: readonly MarketplaceRowProjection[];
  total: number;
}

export interface MarketplaceFeatureRegistration {
  id: "marketplace";
  kind: "primary";
  version: 1;
  mount: unknown;
  capabilities: readonly ["desktop", "mobile", "documents", "keyboard"];
}

export interface DocumentViewerRequest {
  productId: string;
  variantId: string;
  document: MarketplaceDocument;
  invokingElement: HTMLElement | null;
}

export interface DocumentViewerCapability {
  open(request: DocumentViewerRequest): void | Promise<void>;
}

export interface MarketplaceQueryCapability {
  query(
    products: readonly MarketplaceProduct[],
    filters: MarketplaceFilters,
    sort: SortOption,
  ): MarketplaceQueryResult;
}

export interface MarketplaceAsyncQueryPage extends MarketplaceQueryResult {
  queryKey: string;
  offset: number;
  nextOffset: number | null;
}

export interface MarketplaceAsyncQueryOptions {
  queryKey: string;
  generationId: string | null;
  offset: number;
  limit: number;
  expandedProductId: string | null;
  signal?: AbortSignal;
}

export interface MarketplaceAsyncQueryCapability {
  query(
    products: readonly MarketplaceProduct[],
    filters: MarketplaceFilters,
    sort: SortOption,
    options: MarketplaceAsyncQueryOptions,
  ): Promise<MarketplaceAsyncQueryPage>;
}

export interface VirtualMarketplaceAdapterProps {
  rows: readonly MarketplaceRowProjection[];
  pages?: readonly { offset: number; rows: readonly MarketplaceRowProjection[] }[];
  queryKey?: string;
  total: number;
  expandedProductId: string | null;
  hasPreviousPage?: boolean;
  hasNextPage?: boolean;
  renderRow(row: MarketplaceRowProjection): ReactNode;
  renderExpanded(row: MarketplaceRowProjection): ReactNode;
  onStartReached?: (() => void) | undefined;
  onEndReached?: (() => void) | undefined;
}

export interface VirtualMarketplaceAdapter {
  render(props: VirtualMarketplaceAdapterProps): ReactNode;
}

export interface MarketplaceFeatureProps {
  products: readonly MarketplaceProduct[];
  detailsByProductId?: Readonly<Record<string, MarketplaceProductDetail | undefined>>;
  loading?: boolean;
  refreshing?: boolean;
  error?: string | null;
  onRetry?: (() => void) | undefined;
  loadDetail?: ((productId: string, signal: AbortSignal) => Promise<MarketplaceProductDetail>) | undefined;
  documentViewer?: DocumentViewerCapability | undefined;
  queryEngine?: MarketplaceQueryCapability | undefined;
  asyncQueryEngine?: MarketplaceAsyncQueryCapability | undefined;
  virtualization?: VirtualMarketplaceAdapter | undefined;
  initialSort?: SortOption;
}

const collator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
  usage: "sort",
});

const PRICE_PER_GRAM_ABSOLUTE_TOLERANCE = 0.015;
const PRICE_PER_GRAM_RELATIVE_TOLERANCE = 0.001;
const MAX_PUBLIC_URL_LENGTH = 4096;

export const DEFAULT_FILTERS: MarketplaceFilters = Object.freeze({
  search: "",
  vendorIds: Object.freeze([]),
  lineages: Object.freeze([]),
  totalThc: Object.freeze({}),
  weight: Object.freeze({}),
  price: Object.freeze({}),
  pricePerGram: Object.freeze({}),
});

export function normalizeSearch(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[\p{P}\p{S}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

export function isHttpUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_PUBLIC_URL_LENGTH) {
    return false;
  }
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLocaleLowerCase();
    const isIpLiteral =
      /^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname) ||
      hostname.startsWith("[");
    return (
      (parsed.protocol === "https:" || parsed.protocol === "http:") &&
      hostname.length > 0 &&
      parsed.username.length === 0 &&
      parsed.password.length === 0 &&
      hostname !== "localhost" &&
      !hostname.endsWith(".localhost") &&
      !isIpLiteral
    );
  } catch {
    return false;
  }
}

export interface SanitizedNumericRange {
  min?: number;
  max?: number;
}

export function sanitizeRange(range: NumericRange): SanitizedNumericRange {
  const min = typeof range.min === "number" && Number.isFinite(range.min) ? range.min : undefined;
  const max = typeof range.max === "number" && Number.isFinite(range.max) ? range.max : undefined;
  const normalized: SanitizedNumericRange = {};
  if (min !== undefined) normalized.min = min;
  if (max !== undefined) normalized.max = max;
  return normalized;
}

export function isInvalidRange(range: NumericRange): boolean {
  const normalized = sanitizeRange(range);
  return (
    normalized.min !== undefined &&
    normalized.max !== undefined &&
    normalized.min > normalized.max
  );
}

export function inRange(value: number, range: NumericRange): boolean {
  const normalized = sanitizeRange(range);
  if (isInvalidRange(normalized)) return false;
  if (normalized.min !== undefined && value < normalized.min) return false;
  if (normalized.max !== undefined && value > normalized.max) return false;
  return true;
}

export function hasConsistentPricePerGram(variant: MarketplaceVariant): boolean {
  if (
    !finitePositive(variant.grams) ||
    !finitePositive(variant.currentPrice) ||
    !finitePositive(variant.pricePerGram)
  ) {
    return false;
  }
  const calculated = variant.currentPrice / variant.grams;
  const tolerance = Math.max(
    PRICE_PER_GRAM_ABSOLUTE_TOLERANCE,
    calculated * PRICE_PER_GRAM_RELATIVE_TOLERANCE,
  );
  return Math.abs(variant.pricePerGram - calculated) <= tolerance;
}

export function isRenderableVariant(variant: MarketplaceVariant): boolean {
  return (
    variant.inStock === true &&
    hasConsistentPricePerGram(variant) &&
    typeof variant.id === "string" &&
    variant.id.trim().length > 0 &&
    isHttpUrl(variant.productUrl)
  );
}

function compareVariantPreference(a: MarketplaceVariant, b: MarketplaceVariant): number {
  return (
    a.pricePerGram - b.pricePerGram ||
    a.currentPrice - b.currentPrice ||
    collator.compare(a.id, b.id)
  );
}

function weightKey(grams: number): string {
  return grams.toFixed(6);
}

export function getInStockVariants(product: MarketplaceProduct): MarketplaceVariant[] {
  const seenIds = new Set<string>();
  const byWeight = new Map<string, MarketplaceVariant>();

  for (const variant of product.variants) {
    if (!isRenderableVariant(variant) || seenIds.has(variant.id)) continue;
    seenIds.add(variant.id);

    const key = weightKey(variant.grams);
    const current = byWeight.get(key);
    if (!current || compareVariantPreference(variant, current) < 0) {
      byWeight.set(key, variant);
    }
  }

  return [...byWeight.values()].sort(
    (a, b) => a.grams - b.grams || collator.compare(a.id, b.id),
  );
}

export function selectActiveVariant(
  product: MarketplaceProduct,
  weightRange: NumericRange,
): MarketplaceVariant | null {
  const candidates = getInStockVariants(product)
    .filter((variant) => inRange(variant.grams, weightRange))
    .sort((a, b) => {
      return (
        a.pricePerGram - b.pricePerGram ||
        a.currentPrice - b.currentPrice ||
        a.grams - b.grams ||
        collator.compare(a.id, b.id)
      );
    });
  return candidates[0] ?? null;
}

export function hasValidDiscount(variant: MarketplaceVariant): boolean {
  return (
    finitePositive(variant.originalPrice) &&
    variant.originalPrice > variant.currentPrice &&
    variant.currentPrice > 0
  );
}

export function discountPercent(variant: MarketplaceVariant): number | null {
  if (!hasValidDiscount(variant)) return null;
  return Math.round(((variant.originalPrice! - variant.currentPrice) / variant.originalPrice!) * 100);
}

export function formatMoney(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const decimals = Number.isInteger(value) ? 0 : 2;
  return `$${value.toFixed(decimals)}`;
}

export function formatPricePerGram(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return `$${value.toFixed(2)}/g`;
}

export function formatWeight(grams: number): string {
  if (!Number.isFinite(grams)) return "—";
  return `${Number.isInteger(grams) ? grams.toFixed(0) : grams.toFixed(1)}g`;
}

export function formatTotalThc(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) return "—";
  return `${Math.round(value)}%`;
}

export function formatRating(
  rating: number | null | undefined,
  reviewCount: number | null | undefined,
): string | null {
  if (
    typeof rating !== "number" ||
    !Number.isFinite(rating) ||
    rating < 0 ||
    rating > 5 ||
    typeof reviewCount !== "number" ||
    !Number.isInteger(reviewCount) ||
    reviewCount < 1
  ) {
    return null;
  }
  return `${rating.toFixed(1)} (${reviewCount})`;
}

export function labelForLineage(lineage: Lineage): string {
  switch (lineage) {
    case "indica":
      return "Indica";
    case "indica_leaning_hybrid":
      return "Indica-leaning hybrid";
    case "hybrid":
      return "Hybrid";
    case "sativa_leaning_hybrid":
      return "Sativa-leaning hybrid";
    case "sativa":
      return "Sativa";
    case "unknown":
      return "Unknown";
  }
}

export function labelForSort(sort: SortOption): string {
  switch (sort) {
    case "lowest_price":
      return "Lowest price";
    case "highest_price":
      return "Highest price";
    case "lowest_price_per_gram":
      return "Lowest price per gram";
    case "highest_price_per_gram":
      return "Highest price per gram";
    case "strain_az":
      return "Strain name A–Z";
    case "strain_za":
      return "Strain name Z–A";
    case "vendor_az":
      return "Vendor A–Z";
    case "vendor_za":
      return "Vendor Z–A";
  }
}

function compareRows(a: MarketplaceRowProjection, b: MarketplaceRowProjection, sort: SortOption): number {
  let result = 0;
  switch (sort) {
    case "lowest_price":
      result = a.activeVariant.currentPrice - b.activeVariant.currentPrice;
      break;
    case "highest_price":
      result = b.activeVariant.currentPrice - a.activeVariant.currentPrice;
      break;
    case "lowest_price_per_gram":
      result = a.activeVariant.pricePerGram - b.activeVariant.pricePerGram;
      break;
    case "highest_price_per_gram":
      result = b.activeVariant.pricePerGram - a.activeVariant.pricePerGram;
      break;
    case "strain_az":
      result = collator.compare(a.product.strainName, b.product.strainName);
      break;
    case "strain_za":
      result = collator.compare(b.product.strainName, a.product.strainName);
      break;
    case "vendor_az":
      result = collator.compare(a.product.vendorName, b.product.vendorName);
      break;
    case "vendor_za":
      result = collator.compare(b.product.vendorName, a.product.vendorName);
      break;
  }
  return result || collator.compare(a.product.id, b.product.id) || a.stableIndex - b.stableIndex;
}

export function productSearchText(product: MarketplaceProduct): string {
  return `${normalizeSearch(product.vendorName)} ${normalizeSearch(product.strainName)}`;
}

export function queryMarketplace(
  products: readonly MarketplaceProduct[],
  filters: MarketplaceFilters,
  sort: SortOption,
): MarketplaceQueryResult {
  const normalizedNeedle = normalizeSearch(filters.search);
  const vendorSet = new Set(filters.vendorIds);
  const lineageSet = new Set(filters.lineages);
  const seenProductIds = new Set<string>();
  const rows: MarketplaceRowProjection[] = [];

  for (let stableIndex = 0; stableIndex < products.length; stableIndex += 1) {
    const product = products[stableIndex]!;
    if (
      typeof product.id !== "string" ||
      product.id.trim().length === 0 ||
      seenProductIds.has(product.id)
    ) {
      continue;
    }

    const activeVariant = selectActiveVariant(product, filters.weight);
    if (!activeVariant) continue;
    seenProductIds.add(product.id);

    if (vendorSet.size > 0 && !vendorSet.has(product.vendorId)) continue;
    if (lineageSet.size > 0 && !lineageSet.has(product.lineage)) continue;

    if (normalizedNeedle && !productSearchText(product).includes(normalizedNeedle)) continue;

    if (
      typeof product.totalThcDisplay !== "number" ||
      !Number.isFinite(product.totalThcDisplay)
    ) {
      const potencyRange = sanitizeRange(filters.totalThc);
      if (potencyRange.min !== undefined || potencyRange.max !== undefined) continue;
    } else if (!inRange(product.totalThcDisplay, filters.totalThc)) {
      continue;
    }

    if (!inRange(activeVariant.currentPrice, filters.price)) continue;
    if (!inRange(activeVariant.pricePerGram, filters.pricePerGram)) continue;

    rows.push({
      product,
      activeVariant,
      availableSizeCount: getInStockVariants(product).length,
      stableIndex,
    });
  }

  rows.sort((a, b) => compareRows(a, b, sort));
  return { rows, total: rows.length };
}

export function resolveVariant(
  product: MarketplaceProduct,
  variantId: string | null | undefined,
  fallback: MarketplaceVariant,
): MarketplaceVariant {
  if (!variantId) return fallback;
  return getInStockVariants(product).find((variant) => variant.id === variantId) ?? fallback;
}

export function isRenderableDocument(
  document: MarketplaceDocument | null | undefined,
  expectedKind?: DocumentKind,
): document is MarketplaceDocument {
  return (
    document !== null &&
    document !== undefined &&
    typeof document.id === "string" &&
    document.id.trim().length > 0 &&
    (expectedKind === undefined || document.kind === expectedKind) &&
    isHttpUrl(document.url) &&
    (document.format === "pdf" ||
      document.format === "image" ||
      document.format === "html" ||
      document.format === "unsupported")
  );
}

export function resolveDocument(
  variant: MarketplaceVariant,
  kind: DocumentKind,
): MarketplaceDocument | null {
  const document = kind === "coa" ? variant.coa : variant.terpeneDocument;
  return isRenderableDocument(document, kind) ? document : null;
}

export function nextExpandedProduct(
  currentProductId: string | null,
  requestedProductId: string,
): string | null {
  return currentProductId === requestedProductId ? null : requestedProductId;
}

export function keepExpandedProduct(
  expandedProductId: string | null,
  rows: readonly MarketplaceRowProjection[],
): string | null {
  if (!expandedProductId) return null;
  return rows.some((row) => row.product.id === expandedProductId) ? expandedProductId : null;
}

export function escapeSearchState(value: string, isFocused: boolean): {
  value: string;
  shouldBlur: boolean;
} {
  if (value) return { value: "", shouldBlur: false };
  return { value, shouldBlur: isFocused };
}

export function uniqueVendors(products: readonly MarketplaceProduct[]): Array<{ id: string; name: string }> {
  const vendors = new Map<string, string>();
  for (const product of products) {
    if (
      typeof product.vendorId !== "string" ||
      product.vendorId.trim().length === 0 ||
      typeof product.vendorName !== "string" ||
      product.vendorName.trim().length === 0 ||
      getInStockVariants(product).length === 0
    ) {
      continue;
    }
    if (!vendors.has(product.vendorId)) vendors.set(product.vendorId, product.vendorName);
  }
  return [...vendors.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => collator.compare(a.name, b.name));
}
