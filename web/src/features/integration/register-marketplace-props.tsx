/* eslint-disable react-refresh/only-export-components */
import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import type { CapabilityReader, CapabilityRegistrationTarget } from "../../app/capabilityRegistry";
import type {
  DocumentViewerRequest,
  MarketplaceAsyncQueryCapability,
  MarketplaceAsyncQueryPage,
  MarketplaceDocument,
  MarketplaceFeatureProps,
  MarketplaceProduct,
  MarketplaceProductDetail,
  MarketplaceRowProjection,
  MarketplaceVariant,
  SortOption,
  VirtualMarketplaceAdapter,
  VirtualMarketplaceAdapterProps,
} from "../marketplace/marketplace-core";
import "./integration.css";

type CatalogGeneration = {
  generationId: string;
  index: { products?: unknown[] };
};

type CatalogClient = {
  initialize(options?: { signal?: AbortSignal; force?: boolean }): Promise<CatalogGeneration>;
  loadDetail(productId: string, options?: { signal?: AbortSignal }): Promise<unknown>;
  snapshot(): CatalogGeneration | null;
};

type PlatformQueryResult = {
  generationId: string;
  queryKey: string;
  offset: number;
  rows: Array<{ productId: string; variantId: string }>;
  total: number;
  nextOffset: number | null;
};

type PlatformQueryEngine = {
  initialize(generationId: string, products: unknown[]): Promise<void>;
  query(input: Record<string, unknown>): Promise<PlatformQueryResult>;
};

type VirtualWindow = {
  items: Array<{ productId: string; row: MarketplaceRowProjection }>;
  topSpacer: number;
  bottomSpacer: number;
  totalCount: number;
};

type VirtualModel = {
  replacePages(input: {
    pages: Array<{ offset: number; rows: Array<{ productId: string; row: MarketplaceRowProjection }> }>;
    total: number;
    version: number;
    queryKey: string;
    preserveAnchor?: boolean;
  }): void;
  setViewport(scrollTop: number, height: number): void;
  measure(key: string, height: number): boolean;
  window(): VirtualWindow;
  loadedRange(): { startPx: number; endPx: number };
  subscribe(listener: () => void): () => void;
  totalHeight(): number;
};

type ViewerState = {
  status: string;
  type: string | null;
  documentRef: MarketplaceDocument | null;
  page: number;
  pages: number | null;
  scale: number;
  fitWidth: boolean;
  displayUrl: string | null;
  error: { message?: string } | null;
  sessionId: string | null;
};

type PlatformDocumentViewer = {
  open(document: MarketplaceDocument, context?: Record<string, unknown>): Promise<unknown>;
  close(options?: { restoreFocus?: boolean }): Promise<void>;
  subscribe(listener: (state: ViewerState) => void): () => void;
  snapshot(): ViewerState;
  renderPage(canvas: HTMLCanvasElement, options?: Record<string, unknown>): Promise<unknown>;
  goToPage(page: number): void;
  zoomIn(): void;
  zoomOut(): void;
  setFitWidth(enabled?: boolean): void;
  handleKeyDown(event: KeyboardEvent, root: HTMLElement | null): boolean;
};

type PwaCoordinator = {
  register(scriptUrl?: string, options?: { scope: string }): Promise<unknown>;
  cacheOpenedDocument(document: MarketplaceDocument): Promise<boolean>;
};

export async function openMarketplaceDocument(
  viewer: PlatformDocumentViewer,
  pwa: PwaCoordinator | undefined,
  request: DocumentViewerRequest,
): Promise<void> {
  await viewer.open(request.document, {
    productId: request.productId,
    variantId: request.variantId,
    invoker: request.invokingElement,
  });
  const state = viewer.snapshot();
  if (state.status !== "ready" || (state.type !== "pdf" && state.type !== "image")) return;
  void Promise.resolve()
    .then(() => pwa?.cacheOpenedDocument(request.document))
    .catch(() => undefined);
}

type GenerationAwareMarketplaceFeatureProps = MarketplaceFeatureProps & {
  catalogGenerationId?: string | null;
};

type ProviderProps = {
  mount: ComponentType<GenerationAwareMarketplaceFeatureProps>;
  capabilities: CapabilityReader;
};

const LINEAGE_TO_PLATFORM: Record<string, string> = {
  indica: "indica",
  indica_leaning_hybrid: "indica_hybrid",
  hybrid: "hybrid",
  sativa_leaning_hybrid: "sativa_hybrid",
  sativa: "sativa",
  unknown: "unknown",
};

const SORT_TO_PLATFORM: Record<SortOption, string> = {
  lowest_price: "lowest_price",
  highest_price: "highest_price",
  lowest_price_per_gram: "lowest_ppg",
  highest_price_per_gram: "highest_ppg",
  strain_az: "strain_az",
  strain_za: "strain_za",
  vendor_az: "vendor_az",
  vendor_za: "vendor_za",
};

const objectValue = (value: unknown): Record<string, unknown> | null =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const stringValue = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const numberValue = (value: unknown): number | null => {
  if (value === null || value === undefined || (typeof value === "string" && value.trim() === "")) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const documentFormat = (url: string, mimeType: string): MarketplaceDocument["format"] => {
  const normalizedMime = mimeType.toLowerCase();
  if (normalizedMime === "application/pdf" || /\.pdf(?:$|[?#])/i.test(url)) return "pdf";
  if (normalizedMime.startsWith("image/") || /\.(?:png|jpe?g|webp|gif)(?:$|[?#])/i.test(url)) return "image";
  if (normalizedMime === "text/html" || /\.html?(?:$|[?#])/i.test(url)) return "html";
  return "unsupported";
};

const mapDocument = (raw: unknown, fallbackKind: "coa" | "terpene"): MarketplaceDocument | null => {
  const row = objectValue(raw);
  if (!row) return null;
  const url = stringValue(row.public_url ?? row.url);
  const id = stringValue(row.document_id ?? row.id);
  if (!url || !id) return null;
  const rawKind = stringValue(row.kind);
  const kind = rawKind === "terpene" ? "terpene" : fallbackKind;
  const mimeType = stringValue(row.mime_type);
  return {
    id,
    kind,
    url,
    format: documentFormat(url, mimeType),
    title: stringValue(row.discovered_label ?? row.title) || null,
    mimeType: mimeType || null,
  };
};

const selectDocument = (
  documents: unknown,
  target: "coa" | "terpene",
): MarketplaceDocument | null => {
  if (!Array.isArray(documents)) return null;
  const direct = documents.find((value) => objectValue(value)?.kind === target);
  const combined = documents.find((value) => objectValue(value)?.kind === "combined");
  return mapDocument(direct ?? combined, target);
};

export const mapCatalogIndex = (index: unknown): MarketplaceProduct[] => {
  const envelope = objectValue(index);
  const rows = Array.isArray(envelope?.products) ? envelope.products : [];
  return rows.flatMap((raw): MarketplaceProduct[] => {
    const product = objectValue(raw);
    if (!product) return [];
    const id = stringValue(product.product_id ?? product.id);
    const vendorId = stringValue(product.vendor_id);
    const vendorName = stringValue(product.vendor_name ?? product.vendor);
    const strainName = stringValue(product.strain_name ?? product.strain);
    if (!id || !vendorId || !vendorName || !strainName) return [];

    const variants = (Array.isArray(product.variants) ? product.variants : []).flatMap((rawVariant): MarketplaceVariant[] => {
      const variant = objectValue(rawVariant);
      if (!variant) return [];
      const variantId = stringValue(variant.variant_id ?? variant.id);
      const grams = numberValue(variant.grams ?? variant.weight);
      const currentPrice = numberValue(variant.current_price ?? variant.price);
      const pricePerGram = numberValue(variant.price_per_gram);
      const productUrl = stringValue(variant.product_url ?? variant.variant_url);
      if (!variantId || !grams || !currentPrice || !pricePerGram || !productUrl) return [];
      const originalPrice = numberValue(variant.original_price);
      return [{
        id: variantId,
        grams,
        sourceWeightLabel: stringValue(variant.source_weight_label) || `${grams} g`,
        currentPrice,
        originalPrice,
        pricePerGram,
        inStock: true,
        productUrl,
        imageUrl: stringValue(variant.image_url) || null,
        coa: selectDocument(variant.documents, "coa"),
        terpeneDocument: selectDocument(variant.documents, "terpene"),
      }];
    });

    const lineage = stringValue(product.lineage);
    return [{
      id,
      vendorId,
      vendorName,
      vendorFaviconUrl: stringValue(product.vendor_favicon_url) || null,
      strainName,
      lineage: [
        "indica",
        "indica_leaning_hybrid",
        "hybrid",
        "sativa_leaning_hybrid",
        "sativa",
      ].includes(lineage) ? lineage as MarketplaceProduct["lineage"] : "unknown",
      totalThcDisplay: numberValue(product.total_thc_display_percent ?? product.total_thc),
      rating: numberValue(product.rating),
      reviewCount: numberValue(product.review_count),
      variants,
    }];
  });
};

const detailProduct = (payload: unknown, productId: string): Record<string, unknown> | null => {
  const value = objectValue(payload);
  if (!value) return null;
  const direct = objectValue(value.product);
  if (direct && stringValue(direct.product_id ?? direct.id) === productId) return direct;
  const rows = Array.isArray(value.products) ? value.products : [];
  return rows.map(objectValue).find((row) => row && stringValue(row.product_id ?? row.id) === productId) ?? null;
};

export const mapCatalogDetail = (payload: unknown, productId: string): MarketplaceProductDetail => {
  const product = detailProduct(payload, productId);
  const effects = Array.isArray(product?.effects)
    ? product.effects.map(stringValue).filter(Boolean)
    : [];
  const grow = stringValue(product?.grow_environment);
  return {
    productId,
    imageUrl: stringValue(product?.image_url) || null,
    effects,
    growEnvironment: ["indoor", "outdoor", "greenhouse"].includes(grow)
      ? grow as MarketplaceProductDetail["growEnvironment"]
      : "unknown",
  };
};

const enrichProduct = (
  current: MarketplaceProduct,
  payload: unknown,
): MarketplaceProduct => {
  const product = detailProduct(payload, current.id);
  if (!product) return current;
  const details = Array.isArray(product.variants)
    ? product.variants.map(objectValue).filter((value): value is Record<string, unknown> => value !== null)
    : [];
  const byId = new Map(details.map((variant) => [stringValue(variant?.variant_id ?? variant?.id), variant]));
  return {
    ...current,
    variants: current.variants.map((variant) => {
      const detail = byId.get(variant.id);
      if (!detail) return variant;
      return {
        ...variant,
        imageUrl: stringValue(detail.image_url) || variant.imageUrl,
        coa: selectDocument(detail.documents, "coa") ?? variant.coa,
        terpeneDocument: selectDocument(detail.documents, "terpene") ?? variant.terpeneDocument,
      };
    }),
  };
};

const toPlatformProducts = (products: readonly MarketplaceProduct[]) =>
  products.map((product) => ({
    id: product.id,
    vendor_id: product.vendorId,
    vendor: product.vendorName,
    strain: product.strainName,
    lineage: LINEAGE_TO_PLATFORM[product.lineage] ?? "unknown",
    total_thc: product.totalThcDisplay,
    variants: product.variants.map((variant) => ({
      id: variant.id,
      grams: variant.grams,
      price: variant.currentPrice,
      price_per_gram: variant.pricePerGram,
    })),
  }));

const bound = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

export const createMarketplaceQueryAdapter = (
  engine: PlatformQueryEngine,
): MarketplaceAsyncQueryCapability => ({
  async query(products, filters, sort, options): Promise<MarketplaceAsyncQueryPage> {
    const result = await engine.query({
      search: filters.search,
      vendors: filters.vendorIds,
      lineages: filters.lineages.map((lineage) => LINEAGE_TO_PLATFORM[lineage] ?? "unknown"),
      minTotalThc: bound(filters.totalThc.min),
      maxTotalThc: bound(filters.totalThc.max),
      minWeight: bound(filters.weight.min),
      maxWeight: bound(filters.weight.max),
      minPrice: bound(filters.price.min),
      maxPrice: bound(filters.price.max),
      minPpg: bound(filters.pricePerGram.min),
      maxPpg: bound(filters.pricePerGram.max),
      sort: SORT_TO_PLATFORM[sort],
      offset: options.offset,
      limit: options.limit,
      expandedProductId: options.expandedProductId,
    });
    if (options.signal?.aborted) throw new DOMException("The operation was aborted", "AbortError");
    if (options.generationId && result.generationId !== options.generationId) {
      throw new DOMException("The catalog generation changed", "AbortError");
    }
    if (result.offset !== options.offset) {
      throw new DOMException("The marketplace page offset changed", "AbortError");
    }
    const productById = new Map(products.map((product) => [product.id, product]));
    const rows = result.rows.flatMap((row, index): MarketplaceRowProjection[] => {
      const product = productById.get(row.productId);
      const activeVariant = product?.variants.find((variant) => variant.id === row.variantId);
      if (!product || !activeVariant) return [];
      return [{
        product,
        activeVariant,
        availableSizeCount: product.variants.length,
        stableIndex: options.offset + index,
      }];
    });
    return {
      queryKey: options.queryKey,
      offset: result.offset,
      rows,
      total: result.total,
      nextOffset: result.nextOffset,
    };
  },
});

function MeasuredRow({
  productId,
  model,
  children,
}: {
  productId: string;
  model: VirtualModel;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => model.measure(productId, element.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [model, productId]);
  return <div ref={ref} data-virtual-product={productId} role="listitem">{children}</div>;
}

function VirtualizedMarketplace({
  model,
  rows,
  pages,
  queryKey = "marketplace",
  total,
  renderRow,
  hasPreviousPage = false,
  hasNextPage = false,
  onStartReached,
  onEndReached,
}: VirtualMarketplaceAdapterProps & { model: VirtualModel }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [, setRevision] = useState(0);
  const virtualPages = useMemo(
    () => (pages ?? [{ offset: 0, rows }]).map((page) => ({
      offset: page.offset,
      rows: page.rows.map((row) => ({ productId: row.product.id, row })),
    })),
    [pages, rows],
  );

  useLayoutEffect(() => {
    model.replacePages({
      pages: virtualPages,
      total,
      version: virtualPages.length,
      queryKey,
      preserveAnchor: true,
    });
  }, [model, queryKey, total, virtualPages]);

  useEffect(() => model.subscribe(() => setRevision((value) => value + 1)), [model]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const update = () => model.setViewport(viewport.scrollTop, viewport.clientHeight);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [model]);

  const windowState = model.window();
  const onScroll = () => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    model.setViewport(viewport.scrollTop, viewport.clientHeight);
    const range = model.loadedRange();
    if (hasPreviousPage && onStartReached && viewport.scrollTop <= range.startPx + 900) {
      onStartReached();
    }
    if (
      hasNextPage &&
      onEndReached &&
      viewport.scrollTop + viewport.clientHeight >= range.endPx - 900
    ) {
      onEndReached();
    }
  };

  return (
    <div
      ref={viewportRef}
      className="df-virtual-viewport"
      onScroll={onScroll}
    >
      <div style={{ height: windowState.topSpacer }} aria-hidden="true" />
      {windowState.items.map((item) => (
        <MeasuredRow key={item.productId} productId={item.productId} model={model}>
          {renderRow(item.row)}
        </MeasuredRow>
      ))}
      <div style={{ height: windowState.bottomSpacer }} aria-hidden="true" />
    </div>
  );
}

const createVirtualizationAdapter
 = (model: VirtualModel): VirtualMarketplaceAdapter => ({
  render(props: VirtualMarketplaceAdapterProps): ReactNode {
    return <VirtualizedMarketplace {...props} model={model} />;
  },
});

function DocumentOverlay({
  viewer,
  request,
  onClosed,
}: {
  viewer: PlatformDocumentViewer;
  request: DocumentViewerRequest;
  onClosed(): void;
}) {
  const [state, setState] = useState<ViewerState>(() => viewer.snapshot());
  const dialogRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => viewer.subscribe(setState), [viewer]);
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);
  useEffect(() => {
    if (state.status !== "ready" || state.type !== "pdf" || !canvasRef.current) return;
    let current = true;
    setRenderError(null);
    void viewer.renderPage(canvasRef.current, {
      page: state.page,
      scale: state.scale,
      fitWidth: state.fitWidth,
    }).catch((error: unknown) => {
      if (current && stringValue(objectValue(error)?.name) !== "AbortError") {
        setRenderError("This document could not be rendered. Open the original document.");
      }
    });
    return () => {
      current = false;
    };
  }, [state.fitWidth, state.page, state.scale, state.sessionId, state.status, state.type, viewer]);

  const close = async () => {
    await viewer.close();
    onClosed();
  };

  const body = (
    <div className="df-platform-document-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) void close();
    }}>
      <div
        ref={dialogRef}
        className="df-platform-document-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={request.document.title || "Lab document"}
        tabIndex={-1}
        onKeyDown={(event) => viewer.handleKeyDown(event.nativeEvent, dialogRef.current)}
      >
        <header>
          <strong>{request.document.title || (request.document.kind === "coa" ? "COA" : "Terpene document")}</strong>
          <span>
            <a href={request.document.url} target="_blank" rel="noreferrer">Open original</a>
            <button type="button" onClick={() => void close()}>Close</button>
          </span>
        </header>
        <div className="df-platform-document-stage">
          {state.status === "loading" ? <p role="status">Loading document</p> : null}
          {state.status === "ready" && state.type === "pdf" ? <canvas ref={canvasRef} /> : null}
          {state.status === "ready" && state.type === "image" && state.displayUrl
            ? <img src={state.displayUrl} alt={request.document.title || "Lab document"} />
            : null}
          {["error", "unsupported", "external-only"].includes(state.status) || renderError
            ? <p role="alert">{renderError || state.error?.message || "Open the original document."}</p>
            : null}
        </div>
        {state.status === "ready" && state.type === "pdf" ? (
          <footer>
            <button type="button" onClick={() => viewer.goToPage(state.page - 1)} disabled={state.page <= 1}>Previous</button>
            <span>Page {state.page} of {state.pages ?? 1}</span>
            <button type="button" onClick={() => viewer.goToPage(state.page + 1)} disabled={state.page >= (state.pages ?? 1)}>Next</button>
            <button type="button" onClick={() => viewer.zoomOut()}>Zoom out</button>
            <button type="button" onClick={() => viewer.zoomIn()}>Zoom in</button>
            <button type="button" onClick={() => viewer.setFitWidth(true)}>Fit width</button>
          </footer>
        ) : null}
      </div>
    </div>
  );
  return createPortal(body, document.body);
}

export function IntegratedMarketplaceProvider({
  mount: Mount,
  capabilities,
}: ProviderProps) {
  const catalog = capabilities.getCapability<CatalogClient>("platform.catalog", 1);
  const queryEngine = capabilities.getCapability<PlatformQueryEngine>("platform.query", 1);
  const virtualModel = capabilities.getCapability<VirtualModel>("platform.virtualization", 1);
  const viewer = capabilities.getCapability<PlatformDocumentViewer>("platform.documents", 1);
  const pwa = capabilities.getCapability<PwaCoordinator>("platform.pwa", 1);
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [catalogGenerationId, setCatalogGenerationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documentRequest, setDocumentRequest] = useState<DocumentViewerRequest | null>(null);
  const mounted = useRef(true);

  const queryAdapter = useMemo(
    () => queryEngine ? createMarketplaceQueryAdapter(queryEngine) : undefined,
    [queryEngine],
  );
  const virtualization = useMemo(
    () => virtualModel ? createVirtualizationAdapter(virtualModel) : undefined,
    [virtualModel],
  );

  const refresh = useCallback(async (force = false, signal?: AbortSignal) => {
    if (!catalog || !queryEngine) {
      setError("Required marketplace platform capabilities are unavailable.");
      setLoading(false);
      return;
    }
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const generation = await catalog.initialize({ signal, force });
      const nextProducts = mapCatalogIndex(generation.index);
      await queryEngine.initialize(generation.generationId, toPlatformProducts(nextProducts));
      if (!mounted.current || signal?.aborted) return;
      setCatalogGenerationId(generation.generationId);
      setProducts(nextProducts);
    } catch (caught) {
      if (!mounted.current || signal?.aborted) return;
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "Marketplace data could not be loaded.");
    } finally {
      if (mounted.current && !signal?.aborted) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [catalog, queryEngine]);

  useEffect(() => {
    mounted.current = true;
    // CatalogGenerationClient deduplicates initialization through one shared
    // promise. Aborting the first StrictMode mount would poison the second
    // mount with the same AbortError, so startup is guarded by mounted state
    // instead of tying the shared generation request to component cleanup.
    void refresh(false);
    return () => {
      mounted.current = false;
    };
  }, [refresh]);

  useEffect(() => {
    if (!pwa) return;
    void pwa.register("./sw.js", { scope: "./" }).catch(() => undefined);
  }, [pwa]);

  const loadDetail = useCallback(async (productId: string, signal: AbortSignal) => {
    if (!catalog) throw new Error("Catalog detail capability is unavailable.");
    const requestedGenerationId = catalogGenerationId ?? catalog.snapshot()?.generationId;
    if (!requestedGenerationId) throw new Error("Catalog generation is unavailable.");
    const payload = await catalog.loadDetail(productId, { signal });
    const payloadGenerationId = stringValue(objectValue(payload)?.generation_id);
    if (
      signal.aborted ||
      catalog.snapshot()?.generationId !== requestedGenerationId ||
      payloadGenerationId !== requestedGenerationId
    ) {
      throw new DOMException("The catalog generation changed", "AbortError");
    }
    setProducts((current) => {
      if (catalog.snapshot()?.generationId !== requestedGenerationId) return current;
      return current.map((product) =>
        product.id === productId ? enrichProduct(product, payload) : product
      );
    });
    return mapCatalogDetail(payload, productId);
  }, [catalog, catalogGenerationId]);

  const documentViewer = useMemo(() => viewer ? {
    async open(request: DocumentViewerRequest) {
      setDocumentRequest(request);
      await openMarketplaceDocument(viewer, pwa, request);
    },
  } : undefined, [viewer, pwa]);

  return (
    <Fragment>
      <Mount
        products={products}
        loading={loading}
        refreshing={refreshing}
        error={error}
        onRetry={() => void refresh(true)}
        loadDetail={loadDetail}
        catalogGenerationId={catalogGenerationId}
        documentViewer={documentViewer}
        asyncQueryEngine={queryAdapter}
        virtualization={virtualization}
      />
      {viewer && documentRequest ? (
        <DocumentOverlay
          viewer={viewer}
          request={documentRequest}
          onClosed={() => setDocumentRequest(null)}
        />
      ) : null}
    </Fragment>
  );
}

export function registerFeatureCapabilities(registry: CapabilityRegistrationTarget): void {
  registry.registerCapability("marketplace.props", {
    contractVersion: 1,
    instance: { Provider: IntegratedMarketplaceProvider },
  });
}
