import type {
  MarketplaceAsyncQueryPage,
  MarketplaceFilters,
  MarketplaceProduct,
  MarketplaceRowProjection,
  SortOption,
} from "./marketplace-core.js";

export const MARKETPLACE_PAGE_SIZE = 120;
export const MARKETPLACE_MAX_RETAINED_PAGES = 8;

export type MarketplacePageDirection = "forward" | "backward";

export interface MarketplacePageWindow {
  queryKey: string;
  pages: readonly MarketplaceAsyncQueryPage[];
  total: number;
  pageZeroAccepted: boolean;
}

export function emptyMarketplacePageWindow(queryKey: string): MarketplacePageWindow {
  return {
    queryKey,
    pages: [],
    total: 0,
    pageZeroAccepted: false,
  };
}

export function acceptMarketplacePageZero(
  current: MarketplacePageWindow,
  page: MarketplaceAsyncQueryPage,
): MarketplacePageWindow {
  if (page.queryKey !== current.queryKey || page.offset !== 0) return current;
  return {
    queryKey: current.queryKey,
    pages: [page],
    total: page.total,
    pageZeroAccepted: true,
  };
}

export function acceptMarketplaceRetainedPage(
  current: MarketplacePageWindow,
  page: MarketplaceAsyncQueryPage,
  direction: MarketplacePageDirection,
  maxRetainedPages = MARKETPLACE_MAX_RETAINED_PAGES,
): MarketplacePageWindow {
  if (!current.pageZeroAccepted || page.queryKey !== current.queryKey) return current;
  if (page.total !== current.total || current.pages.some((candidate) => candidate.offset === page.offset)) {
    return current;
  }
  const expectedOffset = direction === "forward"
    ? nextMarketplacePageOffset(current)
    : previousMarketplacePageOffset(current);
  if (expectedOffset === null || page.offset !== expectedOffset) return current;

  const pages = [...current.pages, page].sort((left, right) => left.offset - right.offset);
  while (pages.length > Math.max(1, maxRetainedPages)) {
    if (direction === "forward") pages.shift();
    else pages.pop();
  }
  return { ...current, pages };
}

export function marketplaceRetainedRows(
  current: MarketplacePageWindow,
): readonly MarketplaceRowProjection[] {
  const rows: MarketplaceRowProjection[] = [];
  const seen = new Set<string>();
  for (const page of [...current.pages].sort((left, right) => left.offset - right.offset)) {
    for (const row of page.rows) {
      if (seen.has(row.product.id)) continue;
      seen.add(row.product.id);
      rows.push(row);
    }
  }
  return rows;
}

export function nextMarketplacePageOffset(current: MarketplacePageWindow): number | null {
  if (!current.pageZeroAccepted || current.pages.length === 0) return null;
  return current.pages[current.pages.length - 1]?.nextOffset ?? null;
}

export function previousMarketplacePageOffset(current: MarketplacePageWindow): number | null {
  if (!current.pageZeroAccepted || current.pages.length === 0) return null;
  const firstOffset = current.pages[0]?.offset ?? 0;
  return firstOffset > 0 ? Math.max(0, firstOffset - MARKETPLACE_PAGE_SIZE) : null;
}

export function marketplaceRetainedBaseOffset(current: MarketplacePageWindow): number {
  return current.pages[0]?.offset ?? 0;
}

export function marketplaceRetainedEndOffset(current: MarketplacePageWindow): number {
  const last = current.pages[current.pages.length - 1];
  return last ? last.offset + last.rows.length : 0;
}

function normalizedSearch(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase()
    .replace(/[\p{P}\p{S}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizedRange(value: { min?: number | null; max?: number | null }) {
  return {
    min: typeof value.min === "number" && Number.isFinite(value.min) ? value.min : null,
    max: typeof value.max === "number" && Number.isFinite(value.max) ? value.max : null,
  };
}

export function marketplaceQueryIdentity(input: {
  catalogGenerationId: string | null;
  productType: string;
  products: readonly MarketplaceProduct[];
  filters: MarketplaceFilters;
  sort: SortOption;
}): string {
  const productIndex = input.products.map((product) => (
    `${product.id}:${product.variants.map((variant) => variant.id).join(",")}`
  ));
  return JSON.stringify({
    generation: input.catalogGenerationId ?? "unscoped",
    productType: input.productType,
    productIndex,
    search: normalizedSearch(input.filters.search),
    vendors: [...input.filters.vendorIds].sort(),
    lineages: [...input.filters.lineages].sort(),
    totalThc: normalizedRange(input.filters.totalThc),
    weight: normalizedRange(input.filters.weight),
    price: normalizedRange(input.filters.price),
    comparisonPrice: normalizedRange(input.filters.pricePerGram),
    stock: "in_stock",
    sort: input.sort,
    favorites: [],
    expandedQueryInputs: null,
  });
}
