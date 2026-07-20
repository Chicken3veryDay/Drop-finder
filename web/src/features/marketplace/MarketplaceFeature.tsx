import {
  DEFAULT_FILTERS,
  LINEAGES,
  SORT_OPTIONS,
  discountPercent,
  escapeSearchState,
  formatMoney,
  formatPricePerGram,
  formatRating,
  formatTotalThc,
  formatWeight,
  getInStockVariants,
  hasValidDiscount,
  keepExpandedProduct,
  labelForLineage,
  labelForSort,
  nextExpandedProduct,
  queryMarketplace,
  resolveDocument,
  resolveVariant,
  uniqueVendors,
  type DocumentKind,
  type MarketplaceDocument,
  type MarketplaceFeatureProps,
  type MarketplaceFilters,
  type MarketplaceProduct,
  type MarketplaceProductDetail,
  type MarketplaceRowProjection,
  type MarketplaceVariant,
  type NumericRange,
  type SortOption,
} from "./marketplace-core.js";
import {
  MARKETPLACE_PAGE_SIZE,
  acceptMarketplacePageZero,
  acceptMarketplaceRetainedPage,
  emptyMarketplacePageWindow,
  marketplaceQueryIdentity,
  marketplaceRetainedRows,
  nextMarketplacePageOffset,
  previousMarketplacePageOffset,
} from "./marketplace-pagination.js";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import "./marketplace.css";

const EMPTY_DETAIL: MarketplaceProductDetail = {
  productId: "",
  effects: [],
  growEnvironment: "unknown",
};
const EMPTY_DETAILS_BY_PRODUCT_ID: Record<string, MarketplaceProductDetail> = Object.freeze({});

type DetailLoadStatus = "loading" | "ready" | "error";
type DetailLoadEntry = {
  status: DetailLoadStatus;
  message: string | null;
};

function stopEvent(event: { stopPropagation(): void }): void {
  event.stopPropagation();
}

function RangeField({
  label,
  unit,
  value,
  onChange,
}: {
  label: string;
  unit: string;
  value: NumericRange;
  onChange(value: NumericRange): void;
}) {
  const id = useId();
  const update = (key: "min" | "max", raw: string) => {
    const numeric = raw === "" ? undefined : Number(raw);
    onChange({ ...value, [key]: Number.isFinite(numeric) ? numeric : undefined });
  };

  return (
    <fieldset className="df-range" aria-label={label}>
      <legend>{label}</legend>
      <label htmlFor={`${id}-min`}>Min</label>
      <span className="df-range-input">
        <input
          id={`${id}-min`}
          type="number"
          inputMode="decimal"
          value={value.min ?? ""}
          onChange={(event: any) => update("min", event.currentTarget.value)}
        />
        <span aria-hidden="true">{unit}</span>
      </span>
      <label htmlFor={`${id}-max`}>Max</label>
      <span className="df-range-input">
        <input
          id={`${id}-max`}
          type="number"
          inputMode="decimal"
          value={value.max ?? ""}
          onChange={(event: any) => update("max", event.currentTarget.value)}
        />
        <span aria-hidden="true">{unit}</span>
      </span>
    </fieldset>
  );
}

function CompactMultiSelect<T extends string>({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  selected: readonly T[];
  onChange(value: readonly T[]): void;
}) {
  const selectedSet = new Set(selected);
  const summary = selected.length === 0 ? label : `${label} (${selected.length})`;
  const toggle = (value: T) => {
    const next = new Set(selectedSet);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange([...next]);
  };

  return (
    <details className="df-multiselect">
      <summary>{summary}</summary>
      <div className="df-multiselect-menu" role="group" aria-label={label}>
        {options.map((option) => (
          <label key={option.value}>
            <input
              type="checkbox"
              checked={selectedSet.has(option.value)}
              onChange={() => toggle(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

function PriceBlock({ variant }: { variant: MarketplaceVariant }) {
  const discount = discountPercent(variant);
  return (
    <span className="df-price-block">
      <strong>{formatMoney(variant.currentPrice)}</strong>
      {hasValidDiscount(variant) ? (
        <>
          <del>{formatMoney(variant.originalPrice!)}</del>
          <span className="df-discount">-{discount}%</span>
        </>
      ) : null}
    </span>
  );
}

function VendorIdentity({ product }: { product: MarketplaceProduct }) {
  const [failed, setFailed] = useState(false);
  const fallback = product.vendorName.slice(0, 1).toLocaleUpperCase() || "•";
  return (
    <span className="df-vendor-identity">
      {!failed && product.vendorFaviconUrl ? (
        <img
          src={product.vendorFaviconUrl}
          alt=""
          width="18"
          height="18"
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="df-favicon-fallback" aria-hidden="true">
          {fallback}
        </span>
      )}
      <span>{product.vendorName}</span>
    </span>
  );
}

function SkeletonRows() {
  return (
    <div className="df-skeleton-list" aria-label="Loading marketplace">
      {Array.from({ length: 8 }, (_, index) => (
        <div className="df-skeleton-row" key={index} aria-hidden="true">
          {Array.from({ length: 8 }, (__, cell) => (
            <span key={cell} />
          ))}
        </div>
      ))}
    </div>
  );
}

function FallbackDocumentOverlay({
  document,
  onClose,
  returnFocus,
}: {
  document: MarketplaceDocument;
  onClose(): void;
  returnFocus: HTMLElement | null;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const panel = panelRef.current;
    const previousOverflow = documentBody().style.overflow;
    documentBody().style.overflow = "hidden";
    panel?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const focusable = [...panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && globalThis.document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && globalThis.document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    globalThis.document.addEventListener("keydown", onKeyDown);
    return () => {
      globalThis.document.removeEventListener("keydown", onKeyDown);
      documentBody().style.overflow = previousOverflow;
      returnFocus?.focus();
    };
  }, [onClose, returnFocus]);

  return (
    <div className="df-document-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="df-document-panel"
        role="dialog"
        aria-modal="true"
        aria-label={document.title || (document.kind === "coa" ? "COA document" : "Terpene document")}
        tabIndex={-1}
        ref={panelRef}
        onMouseDown={stopEvent}
      >
        <header>
          <strong>{document.title || (document.kind === "coa" ? "COA" : "Terpene document")}</strong>
          <span>
            <a href={document.url} target="_blank" rel="noreferrer">
              Open original
            </a>
            <button type="button" onClick={onClose} aria-label="Close document">
              Close
            </button>
          </span>
        </header>
        <div className="df-document-content">
          {document.format === "image" ? (
            <img src={document.url} alt={document.title || "Lab document"} />
          ) : (
            <p>
              This document opens in its original source. PDF rendering is supplied by the platform document
              capability when issue #9 is integrated.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function documentBody(): HTMLElement {
  return globalThis.document.body;
}

function ExpandedDetail({
  row,
  detail,
  detailStatus,
  detailError,
  selectedVariantId,
  onVariantChange,
  onOpenDocument,
  onRetryDetail,
}: {
  row: MarketplaceRowProjection;
  detail: MarketplaceProductDetail;
  detailStatus: DetailLoadStatus;
  detailError: string | null;
  selectedVariantId: string | undefined;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
  onRetryDetail(): void;
}) {
  const variant = resolveVariant(row.product, selectedVariantId, row.activeVariant);
  const imageUrl = variant.imageUrl || detail.imageUrl;
  const effects = (detail.effects ?? []).filter(Boolean);
  const coa = detailStatus === "ready" ? resolveDocument(variant, "coa") : null;
  const terpene = detailStatus === "ready" ? resolveDocument(variant, "terpene") : null;

  return (
    <div className="df-expanded" id={`detail-${row.product.id}`} role="region" aria-label={`${row.product.strainName} details`}>
      <div className="df-expanded-image">
        {imageUrl ? <img src={imageUrl} alt={`${row.product.strainName} product`} loading="lazy" /> : <span>Image unavailable</span>}
      </div>
      <div className="df-expanded-meta">
        <label>
          <span>Weight</span>
          <select value={variant.id} onChange={(event: any) => onVariantChange(event.currentTarget.value)}>
            {getInStockVariants(row.product).map((item) => (
              <option value={item.id} key={item.id}>
                {item.sourceWeightLabel || formatWeight(item.grams)}
              </option>
            ))}
          </select>
        </label>
        <div>
          <span className="df-expanded-label">Price</span>
          <PriceBlock variant={variant} />
        </div>
        <div>
          <span className="df-expanded-label">Price/g</span>
          <strong>{formatPricePerGram(variant.pricePerGram)}</strong>
        </div>
      </div>
      {detailStatus === "error" ? (
        <div className="df-detail-state" role="alert">
          <p>{detailError || "Product details and lab documents could not be loaded."}</p>
          <button
            type="button"
            onClick={(event: any) => {
              stopEvent(event);
              onRetryDetail();
            }}
          >
            Retry details
          </button>
        </div>
      ) : detailStatus === "loading" ? (
        <div className="df-detail-state" role="status" aria-live="polite">
          Loading product details and lab documents…
        </div>
      ) : (
        <div className="df-expanded-facts">
          <p>
            <span>Effects</span>
            <strong>{effects.length > 0 ? effects.join(", ") : "—"}</strong>
          </p>
          <p>
            <span>Grow</span>
            <strong>{detail.growEnvironment === "unknown" ? "Unknown" : detail.growEnvironment}</strong>
          </p>
        </div>
      )}
      <div className="df-expanded-actions">
        <a href={variant.productUrl} target="_blank" rel="noreferrer" onClick={stopEvent}>
          Product link
        </a>
        {coa ? (
          <button
            type="button"
            onClick={(event: any) => {
              stopEvent(event);
              onOpenDocument("coa", variant, event.currentTarget);
            }}
          >
            Open COA
          </button>
        ) : null}
        {terpene ? (
          <button
            type="button"
            onClick={(event: any) => {
              stopEvent(event);
              onOpenDocument("terpene", variant, event.currentTarget);
            }}
          >
            Open terpene document
          </button>
        ) : null}
      </div>
    </div>
  );
}

function MarketplaceRow({
  row,
  expanded,
  detail,
  detailStatus,
  detailError,
  selectedVariantId,
  onToggle,
  onVariantChange,
  onOpenDocument,
  onRetryDetail,
}: {
  row: MarketplaceRowProjection;
  expanded: boolean;
  detail: MarketplaceProductDetail;
  detailStatus: DetailLoadStatus;
  detailError: string | null;
  selectedVariantId: string | undefined;
  onToggle(): void;
  onVariantChange(variantId: string): void;
  onOpenDocument(kind: DocumentKind, variant: MarketplaceVariant, element: HTMLElement): void;
  onRetryDetail(): void;
}) {
  const rating = formatRating(row.product.rating, row.product.reviewCount);
  const onKeyDown = (event: { key: string; preventDefault(): void }) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggle();
    }
  };

  return (
    <article className={`df-product df-lineage-${row.product.lineage}`} data-expanded={expanded || undefined}>
      <div
        className="df-row"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-controls={`detail-${row.product.id}`}
        onClick={onToggle}
        onKeyDown={onKeyDown}
      >
        <span className="df-cell df-vendor" data-label="Vendor"><VendorIdentity product={row.product} /></span>
        <span className="df-cell df-strain" data-label="Strain Name">{row.product.strainName}</span>
        <span className="df-cell df-lineage" data-label="Lineage">{labelForLineage(row.product.lineage)}</span>
        <span className="df-cell df-thc" data-label="Total THC">{formatTotalThc(row.product.totalThcDisplay)}</span>
        <span className="df-cell df-weight" data-label="Weight">{formatWeight(row.activeVariant.grams)} ({row.availableSizeCount})</span>
        <span className="df-cell df-price" data-label="Price"><PriceBlock variant={row.activeVariant} /></span>
        <span className="df-cell df-ppg" data-label="Price/g">{formatPricePerGram(row.activeVariant.pricePerGram)}</span>
        <span className="df-cell df-rating" data-label="Rating">{rating ?? "—"}</span>
      </div>
      {expanded ? (
        <ExpandedDetail
          row={row}
          detail={detail}
          detailStatus={detailStatus}
          detailError={detailError}
          selectedVariantId={selectedVariantId}
          onVariantChange={onVariantChange}
          onOpenDocument={onOpenDocument}
          onRetryDetail={onRetryDetail}
        />
      ) : null}
    </article>
  );
}

export function MarketplaceFeature({
  products,
  detailsByProductId = EMPTY_DETAILS_BY_PRODUCT_ID,
  loading = false,
  refreshing = false,
  error = null,
  onRetry,
  loadDetail,
  documentViewer,
  queryEngine,
  asyncQueryEngine,
  virtualization,
  initialSort = "lowest_price_per_gram",
  catalogGenerationId = null,
}: MarketplaceFeatureProps & { catalogGenerationId?: string | null }) {
  const [filters, setFilters] = useState<MarketplaceFilters>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortOption>(initialSort);
  const [expandedProductId, setExpandedProductId] = useState<string | null>(null);
  const [selectedVariantIds, setSelectedVariantIds] = useState<Record<string, string>>({});
  const [loadedDetailState, setLoadedDetailState] = useState<{
    generationId: string | null;
    details: Record<string, MarketplaceProductDetail>;
  }>({ generationId: catalogGenerationId, details: {} });
  const loadedDetails = useMemo(
    () => loadedDetailState.generationId === catalogGenerationId
      ? loadedDetailState.details
      : EMPTY_DETAILS_BY_PRODUCT_ID,
    [catalogGenerationId, loadedDetailState],
  );
  const [detailLoadState, setDetailLoadState] = useState<{
    generationId: string | null;
    entries: Record<string, DetailLoadEntry>;
  }>({ generationId: catalogGenerationId, entries: {} });
  const [detailRetryTokens, setDetailRetryTokens] = useState<Record<string, number>>({});
  const activeDetailLoads = useMemo(
    () => detailLoadState.generationId === catalogGenerationId
      ? detailLoadState.entries
      : {},
    [catalogGenerationId, detailLoadState],
  );
  const [fallbackDocument, setFallbackDocument] = useState<{
    document: MarketplaceDocument;
    returnFocus: HTMLElement | null;
  } | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
const syncQuery = useMemo(
  () => asyncQueryEngine
    ? { rows: [], total: 0 }
    : queryEngine?.query(products, filters, sort) ?? queryMarketplace(products, filters, sort),
  [asyncQueryEngine, products, filters, sort, queryEngine],
);
const queryKey = useMemo(() => marketplaceQueryIdentity({
  catalogGenerationId,
  productType: "cannabis_flower",
  products,
  filters,
  sort,
}), [catalogGenerationId, filters, products, sort]);
const activeQueryKey = useRef(queryKey);
activeQueryKey.current = queryKey;
const expandedProductIdRef = useRef(expandedProductId);
expandedProductIdRef.current = expandedProductId;
const productsRef = useRef(products);
productsRef.current = products;
const [asyncWindow, setAsyncWindow] = useState(() => emptyMarketplacePageWindow(queryKey));
const activeAsyncWindow = useMemo(
  () => asyncWindow.queryKey === queryKey ? asyncWindow : emptyMarketplacePageWindow(queryKey),
  [asyncWindow, queryKey],
);
const [queryLoading, setQueryLoading] = useState(false);
const [queryError, setQueryError] = useState<string | null>(null);
const [queryRetryToken, setQueryRetryToken] = useState(0);
const requestControllers = useRef(new Map<string, AbortController>());
const queryRevision = useRef(0);
const asyncRows = useMemo(() => marketplaceRetainedRows(activeAsyncWindow), [activeAsyncWindow]);
const query = asyncQueryEngine
  ? { rows: asyncRows, total: activeAsyncWindow.total }
  : syncQuery;
const virtualPages = useMemo(
  () => asyncQueryEngine
    ? activeAsyncWindow.pages.map((page) => ({ offset: page.offset, rows: page.rows }))
    : [{ offset: 0, rows: syncQuery.rows }],
  [activeAsyncWindow.pages, asyncQueryEngine, syncQuery.rows],
);
const vendors = useMemo(() => uniqueVendors(products), [products]);

useEffect(() => {
  if (!asyncQueryEngine) return;
  const controllers = requestControllers.current;
  const revision = ++queryRevision.current;
  for (const controller of controllers.values()) controller.abort();
  controllers.clear();
  const controller = new AbortController();
  const requestKey = `${queryKey}:0`;
  controllers.set(requestKey, controller);
  setAsyncWindow(emptyMarketplacePageWindow(queryKey));
  setQueryLoading(true);
  setQueryError(null);
  void asyncQueryEngine.query(productsRef.current, filters, sort, {
    queryKey,
    generationId: catalogGenerationId,
    offset: 0,
    limit: MARKETPLACE_PAGE_SIZE,
    expandedProductId: expandedProductIdRef.current,
    signal: controller.signal,
  }).then((result) => {
    if (
      revision === queryRevision.current &&
      activeQueryKey.current === queryKey &&
      !controller.signal.aborted
    ) {
      setAsyncWindow((current) => acceptMarketplacePageZero(
        current.queryKey === queryKey ? current : emptyMarketplacePageWindow(queryKey),
        result,
      ));
    }
  }).catch((caught: unknown) => {
    if (
      revision === queryRevision.current &&
      activeQueryKey.current === queryKey &&
      !controller.signal.aborted &&
      !(caught instanceof DOMException && caught.name === "AbortError")
    ) {
      setQueryError(caught instanceof Error ? caught.message : "Marketplace query failed.");
    }
  }).finally(() => {
    if (controllers.get(requestKey) === controller) controllers.delete(requestKey);
    if (
      revision === queryRevision.current &&
      activeQueryKey.current === queryKey &&
      !controller.signal.aborted
    ) {
      setQueryLoading(false);
    }
  });
  return () => {
    controller.abort();
    if (controllers.get(requestKey) === controller) controllers.delete(requestKey);
  };
}, [asyncQueryEngine, catalogGenerationId, filters, queryKey, queryRetryToken, sort]);

const loadPage = useCallback((direction: "forward" | "backward") => {
  if (!asyncQueryEngine || queryLoading || !activeAsyncWindow.pageZeroAccepted) return;
  const offset = direction === "forward"
    ? nextMarketplacePageOffset(activeAsyncWindow)
    : previousMarketplacePageOffset(activeAsyncWindow);
  if (offset === null) return;
  const requestKey = `${queryKey}:${offset}`;
  if (requestControllers.current.has(requestKey)) return;
  const controller = new AbortController();
  requestControllers.current.set(requestKey, controller);
  void asyncQueryEngine.query(productsRef.current, filters, sort, {
    queryKey,
    generationId: catalogGenerationId,
    offset,
    limit: MARKETPLACE_PAGE_SIZE,
    expandedProductId: expandedProductIdRef.current,
    signal: controller.signal,
  }).then((result) => {
    if (activeQueryKey.current !== queryKey || controller.signal.aborted) return;
    setAsyncWindow((current) => acceptMarketplaceRetainedPage(current, result, direction));
  }).catch((caught: unknown) => {
    if (!(caught instanceof DOMException && caught.name === "AbortError")) {
      setQueryError(caught instanceof Error ? caught.message : "Additional results could not be loaded.");
    }
  }).finally(() => {
    if (requestControllers.current.get(requestKey) === controller) requestControllers.current.delete(requestKey);
  });
}, [activeAsyncWindow, asyncQueryEngine, catalogGenerationId, filters, queryKey, queryLoading, sort]);

const loadMore = useCallback(() => loadPage("forward"), [loadPage]);
const loadPrevious = useCallback(() => loadPage("backward"), [loadPage]);
const retryQuery = useCallback(() => setQueryRetryToken((value) => value + 1), []);
const effectiveLoading = loading || queryLoading;
  const effectiveError = error || queryError;

  useEffect(() => {
    setExpandedProductId((current) => keepExpandedProduct(current, query.rows));
  }, [query.rows]);

  useEffect(() => {
    if (!expandedProductId || !loadDetail || detailsByProductId[expandedProductId] || loadedDetails[expandedProductId]) return;
    const productId = expandedProductId;
    const controller = new AbortController();
    setDetailLoadState((current) => ({
      generationId: catalogGenerationId,
      entries: {
        ...(current.generationId === catalogGenerationId ? current.entries : {}),
        [productId]: { status: "loading", message: null },
      },
    }));
    void loadDetail(productId, controller.signal).then((detail) => {
      if (controller.signal.aborted) return;
      setLoadedDetailState((current) => ({
        generationId: catalogGenerationId,
        details: current.generationId === catalogGenerationId
          ? { ...current.details, [detail.productId]: detail }
          : { [detail.productId]: detail },
      }));
      setDetailLoadState((current) => ({
        generationId: catalogGenerationId,
        entries: {
          ...(current.generationId === catalogGenerationId ? current.entries : {}),
          [productId]: { status: "ready", message: null },
        },
      }));
    }).catch((caught: unknown) => {
      if (controller.signal.aborted || (caught instanceof DOMException && caught.name === "AbortError")) return;
      setDetailLoadState((current) => ({
        generationId: catalogGenerationId,
        entries: {
          ...(current.generationId === catalogGenerationId ? current.entries : {}),
          [productId]: {
            status: "error",
            message: "Product details and lab documents could not be loaded.",
          },
        },
      }));
    });
    return () => controller.abort();
  }, [
    catalogGenerationId,
    expandedProductId,
    loadDetail,
    detailsByProductId,
    loadedDetails,
    detailRetryTokens,
  ]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = target?.matches("input, textarea, select, [contenteditable='true']") ?? false;
      if (event.key === "/" && !editing) {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    globalThis.document.addEventListener("keydown", onKeyDown);
    return () => globalThis.document.removeEventListener("keydown", onKeyDown);
  }, []);

  const updateFilter = <K extends keyof MarketplaceFilters>(key: K, value: MarketplaceFilters[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const clearFilters = () => setFilters(DEFAULT_FILTERS);
  const retryDetail = useCallback((productId: string) => {
    setDetailRetryTokens((current) => ({
      ...current,
      [productId]: (current[productId] ?? 0) + 1,
    }));
  }, []);

  const openDocument = async (
    kind: DocumentKind,
    variant: MarketplaceVariant,
    invokingElement: HTMLElement,
    productId: string,
  ) => {
    const mapped = resolveDocument(variant, kind);
    if (!mapped) return;
    if (documentViewer) {
      await documentViewer.open({
        productId,
        variantId: variant.id,
        document: mapped,
        invokingElement,
      });
      return;
    }
    setFallbackDocument({ document: mapped, returnFocus: invokingElement });
  };

  const renderRow = (row: MarketplaceRowProjection) => (
    <MarketplaceRow
      key={row.product.id}
      row={row}
      expanded={expandedProductId === row.product.id}
      detail={detailsByProductId[row.product.id] || loadedDetails[row.product.id] || { ...EMPTY_DETAIL, productId: row.product.id }}
      detailStatus={
        detailsByProductId[row.product.id] || loadedDetails[row.product.id] || !loadDetail
          ? "ready"
          : activeDetailLoads[row.product.id]?.status ?? "loading"
      }
      detailError={activeDetailLoads[row.product.id]?.message ?? null}
      selectedVariantId={selectedVariantIds[row.product.id]}
      onToggle={() => setExpandedProductId((current) => nextExpandedProduct(current, row.product.id))}
      onVariantChange={(variantId) => setSelectedVariantIds((current) => ({ ...current, [row.product.id]: variantId }))}
      onOpenDocument={(kind, variant, element) => void openDocument(kind, variant, element, row.product.id)}
      onRetryDetail={() => retryDetail(row.product.id)}
    />
  );

  return (
    <section className="df-marketplace" aria-label="Marketplace">
      <div className="df-search-wrap">
        <label className="df-visually-hidden" htmlFor="df-marketplace-search">Search vendor or strain</label>
        <input
          id="df-marketplace-search"
          ref={searchRef}
          className="df-search"
          type="search"
          placeholder="Search vendor or strain"
          value={filters.search}
          onChange={(event: any) => updateFilter("search", event.currentTarget.value)}
          onKeyDown={(event: any) => {
            if (event.key !== "Escape") return;
            const result = escapeSearchState(filters.search, globalThis.document.activeElement === searchRef.current);
            if (result.value !== filters.search) updateFilter("search", result.value);
            if (result.shouldBlur) searchRef.current?.blur();
          }}
        />
      </div>

      <div className="df-filter-row" aria-label="Marketplace filters">
        <CompactMultiSelect
          label="Vendor"
          options={vendors.map((vendor) => ({ value: vendor.id, label: vendor.name }))}
          selected={filters.vendorIds}
          onChange={(value) => updateFilter("vendorIds", value)}
        />
        <CompactMultiSelect
          label="Lineage"
          options={LINEAGES.map((lineage) => ({ value: lineage, label: labelForLineage(lineage) }))}
          selected={filters.lineages}
          onChange={(value) => updateFilter("lineages", value)}
        />
        <RangeField label="Total THC" unit="%" value={filters.totalThc} onChange={(value) => updateFilter("totalThc", value)} />
        <RangeField label="Weight" unit="g" value={filters.weight} onChange={(value) => updateFilter("weight", value)} />
        <RangeField label="Price" unit="$" value={filters.price} onChange={(value) => updateFilter("price", value)} />
        <RangeField label="Price/g" unit="$/g" value={filters.pricePerGram} onChange={(value) => updateFilter("pricePerGram", value)} />
        <span className="df-filter-separator" aria-hidden="true" />
        <label className="df-sort">
          <span>Sort</span>
          <select value={sort} onChange={(event: any) => setSort(event.currentTarget.value as SortOption)}>
            {SORT_OPTIONS.map((option) => (
              <option value={option} key={option}>{labelForSort(option)}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="df-result-header">
        <span aria-live="polite" aria-atomic="true">{query.total.toLocaleString()} results</span>
        {refreshing ? <span className="df-refreshing">Updating</span> : null}
      </div>

      <div className="df-column-header" aria-hidden="true">
        <span>Vendor</span><span>Strain Name</span><span>Lineage</span><span>Total THC</span>
        <span>Weight</span><span>Price</span><span>Price/g</span><span>Rating</span>
      </div>

      {effectiveLoading && query.rows.length === 0 ? <SkeletonRows /> : null}
      {effectiveError && query.rows.length === 0 ? (
        <div className="df-state" role="alert">
          <p>{effectiveError}</p>
          {(queryError || onRetry) ? (
            <button type="button" onClick={queryError ? retryQuery : onRetry}>Retry</button>
          ) : null}
        </div>
      ) : null}
      {!loading && !effectiveError && query.rows.length === 0 ? (
        <div className="df-state">
          <p>No products match these filters.</p>
          <button type="button" onClick={clearFilters}>Clear filters</button>
        </div>
      ) : null}

      {query.rows.length > 0 ? (
        <div
          className="df-list"
          role={virtualization ? undefined : "list"}
          aria-label={virtualization ? undefined : `${query.total} marketplace results`}
        >
          {virtualization
            ? virtualization.render({
                rows: query.rows,
                pages: virtualPages,
                queryKey,
                total: query.total,
                expandedProductId,
                hasPreviousPage: asyncQueryEngine
                  ? previousMarketplacePageOffset(activeAsyncWindow) !== null
                  : false,
                hasNextPage: asyncQueryEngine
                  ? nextMarketplacePageOffset(activeAsyncWindow) !== null
                  : false,
                renderRow,
                renderExpanded: renderRow,
                onStartReached: loadPrevious,
                onEndReached: loadMore,
              })
            : query.rows.map(renderRow)}
        </div>
      ) : null}

      {fallbackDocument ? (
        <FallbackDocumentOverlay
          document={fallbackDocument.document}
          returnFocus={fallbackDocument.returnFocus}
          onClose={() => setFallbackDocument(null)}
        />
      ) : null}
    </section>
  );
}

export const marketplaceFeatureModule = {
  id: "marketplace",
  kind: "primary",
  version: 1,
  mount: MarketplaceFeature,
  capabilities: ["desktop", "mobile", "documents", "keyboard"],
} as const;

export default marketplaceFeatureModule;
