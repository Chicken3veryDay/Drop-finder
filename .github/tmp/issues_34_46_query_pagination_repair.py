from pathlib import Path
import re
import textwrap


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_pattern(path: str, pattern: str, replacement: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    next_text, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(next_text, encoding="utf-8")


replace_once(
    "web/src/features/marketplace/marketplace-core.ts",
    '''export interface MarketplaceAsyncQueryPage extends MarketplaceQueryResult {
  nextOffset: number | null;
}

export interface MarketplaceAsyncQueryOptions {
  offset: number;
  limit: number;
  expandedProductId: string | null;
  signal?: AbortSignal;
}
''',
    '''export interface MarketplaceAsyncQueryPage extends MarketplaceQueryResult {
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
''',
    "async query identity contract",
)
replace_once(
    "web/src/features/marketplace/marketplace-core.ts",
    '''export interface VirtualMarketplaceAdapterProps {
  rows: readonly MarketplaceRowProjection[];
  total: number;
  expandedProductId: string | null;
  renderRow(row: MarketplaceRowProjection): ReactNode;
  renderExpanded(row: MarketplaceRowProjection): ReactNode;
  onEndReached?: (() => void) | undefined;
}
''',
    '''export interface VirtualMarketplaceAdapterProps {
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
''',
    "virtual page contract",
)

replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '} from "./marketplace-core.js";\n',
    '''} from "./marketplace-core.js";
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
''',
    "pagination imports",
)

feature_block = textwrap.dedent('''
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
    const revision = ++queryRevision.current;
    for (const controller of requestControllers.current.values()) controller.abort();
    requestControllers.current.clear();
    const controller = new AbortController();
    const requestKey = `${queryKey}:0`;
    requestControllers.current.set(requestKey, controller);
    setAsyncWindow(emptyMarketplacePageWindow(queryKey));
    setQueryLoading(true);
    setQueryError(null);
    void asyncQueryEngine.query(products, filters, sort, {
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
      if (requestControllers.current.get(requestKey) === controller) requestControllers.current.delete(requestKey);
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
      if (requestControllers.current.get(requestKey) === controller) requestControllers.current.delete(requestKey);
    };
  }, [asyncQueryEngine, catalogGenerationId, filters, products, queryKey, queryRetryToken, sort]);

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
    void asyncQueryEngine.query(products, filters, sort, {
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
  }, [activeAsyncWindow, asyncQueryEngine, catalogGenerationId, filters, products, queryKey, queryLoading, sort]);

  const loadMore = useCallback(() => loadPage("forward"), [loadPage]);
  const loadPrevious = useCallback(() => loadPage("backward"), [loadPage]);
  const retryQuery = useCallback(() => setQueryRetryToken((value) => value + 1), []);
  const effectiveLoading = loading || queryLoading;
''').lstrip("\n")
replace_pattern(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    r"  const syncQuery = useMemo\(.*?\n  const effectiveLoading = loading \|\| queryLoading;\n",
    feature_block,
    "marketplace async page lifecycle",
)
replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''          {onRetry ? <button type="button" onClick={onRetry}>Retry</button> : null}
''',
    '''          {(queryError || onRetry) ? (
            <button type="button" onClick={queryError ? retryQuery : onRetry}>Retry</button>
          ) : null}
''',
    "query retry control",
)
replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''            ? virtualization.render({
                rows: query.rows,
                total: query.total,
                expandedProductId,
                renderRow,
                renderExpanded: renderRow,
                onEndReached: loadMore,
              })
''',
    '''            ? virtualization.render({
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
''',
    "virtual page rendering",
)

replace_once(
    "web/src/features/integration/register-marketplace-props.tsx",
    '''type PlatformQueryResult = {
  rows: Array<{ productId: string; variantId: string }>;
  total: number;
  nextOffset: number | null;
};
''',
    '''type PlatformQueryResult = {
  generationId: string;
  queryKey: string;
  offset: number;
  rows: Array<{ productId: string; variantId: string }>;
  total: number;
  nextOffset: number | null;
};
''',
    "platform query result identity",
)
replace_once(
    "web/src/features/integration/register-marketplace-props.tsx",
    '''type VirtualModel = {
  replace(input: {
    rows: Array<{ productId: string; row: MarketplaceRowProjection }>;
    total: number;
    version: number;
    queryKey: string;
    preserveAnchor?: boolean;
  }): void;
  setViewport(scrollTop: number, height: number): void;
  measure(key: string, height: number): boolean;
  window(): VirtualWindow;
  subscribe(listener: () => void): () => void;
  totalHeight(): number;
};
''',
    '''type VirtualModel = {
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
''',
    "virtual model page interface",
)
replace_once(
    "web/src/features/integration/register-marketplace-props.tsx",
    '''    if (options.signal?.aborted) throw new DOMException("The operation was aborted", "AbortError");
    const productById = new Map(products.map((product) => [product.id, product]));
''',
    '''    if (options.signal?.aborted) throw new DOMException("The operation was aborted", "AbortError");
    if (options.generationId && result.generationId !== options.generationId) {
      throw new DOMException("The catalog generation changed", "AbortError");
    }
    if (result.offset !== options.offset) {
      throw new DOMException("The marketplace page offset changed", "AbortError");
    }
    const productById = new Map(products.map((product) => [product.id, product]));
''',
    "query result ownership checks",
)
replace_once(
    "web/src/features/integration/register-marketplace-props.tsx",
    '''    return {
      rows,
      total: result.total,
      nextOffset: result.nextOffset,
    };
''',
    '''    return {
      queryKey: options.queryKey,
      offset: result.offset,
      rows,
      total: result.total,
      nextOffset: result.nextOffset,
    };
''',
    "query result identity publication",
)

virtual_component = textwrap.dedent('''
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
''').lstrip("\n")
replace_pattern(
    "web/src/features/integration/register-marketplace-props.tsx",
    r"function VirtualizedMarketplace\(\{.*?\nconst createVirtualizationAdapter",
    virtual_component,
    "virtualized marketplace page integration",
)
