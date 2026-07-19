from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''    if (!asyncQueryEngine) return;
    const revision = ++queryRevision.current;
    for (const controller of requestControllers.current.values()) controller.abort();
    requestControllers.current.clear();
    const controller = new AbortController();
    const requestKey = `${queryKey}:0`;
    requestControllers.current.set(requestKey, controller);
''',
    '''    if (!asyncQueryEngine) return;
    const controllers = requestControllers.current;
    const revision = ++queryRevision.current;
    for (const controller of controllers.values()) controller.abort();
    controllers.clear();
    const controller = new AbortController();
    const requestKey = `${queryKey}:0`;
    controllers.set(requestKey, controller);
''',
    "page-zero controller snapshot",
)
replace_once(
    "web/src/features/marketplace/MarketplaceFeature.tsx",
    '''    }).finally(() => {
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
''',
    '''    }).finally(() => {
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
''',
    "page-zero controller cleanup",
)

replace_once(
    "web/src/features/integration/marketplace-integration.test.ts",
    '''    const query = vi.fn().mockResolvedValue({
      rows: [{ productId: "p1", variantId: "v1-7" }],
      total: 1,
      nextOffset: null,
    });
''',
    '''    const query = vi.fn().mockResolvedValue({
      generationId: "g1",
      queryKey: "worker-query",
      offset: 0,
      rows: [{ productId: "p1", variantId: "v1-7" }],
      total: 1,
      nextOffset: null,
    });
''',
    "integration query result identity fixture",
)
replace_once(
    "web/src/features/integration/marketplace-integration.test.ts",
    '''    }, "lowest_price_per_gram", {
      offset: 0,
      limit: 120,
      expandedProductId: null,
    });
''',
    '''    }, "lowest_price_per_gram", {
      queryKey: "test-query",
      generationId: "g1",
      offset: 0,
      limit: 120,
      expandedProductId: null,
    });
''',
    "integration query options identity fixture",
)

replace_once(
    "web/src/features/marketplace/MarketplaceFeature.query-path.test.tsx",
    '''    const asynchronousQuery = vi.fn<MarketplaceAsyncQueryCapability["query"]>(async () => ({
      rows: [row],
      total: 1,
      nextOffset: null,
    }));
''',
    '''    const asynchronousQuery = vi.fn<MarketplaceAsyncQueryCapability["query"]>(async (
      _products,
      _filters,
      _sort,
      options,
    ) => ({
      queryKey: options.queryKey,
      offset: options.offset,
      rows: [row],
      total: 1,
      nextOffset: null,
    }));
''',
    "async query path identity fixture",
)

replace_once(
    "web/src/platform/virtualization/virtual-marketplace-adapter.js",
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount };
''',
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount, ariaRowCount: this.totalCount, renderedCount: 0 };
''',
    "empty virtual window metrics",
)
replace_once(
    "web/src/platform/virtualization/virtual-marketplace-adapter.js",
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount };
''',
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount, ariaRowCount: this.totalCount, renderedCount: 0 };
''',
    "offscreen virtual window metrics",
)
