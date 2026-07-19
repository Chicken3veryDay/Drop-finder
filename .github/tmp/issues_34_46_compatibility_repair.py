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


def replace_exact_count(path: str, old: str, new: str, expected: int, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(new) == expected:
        return
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}: expected {expected} matches, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def scope_page_zero_controllers() -> None:
    target = Path("web/src/features/marketplace/MarketplaceFeature.tsx")
    text = target.read_text(encoding="utf-8")
    marker = "    const controllers = requestControllers.current;\n"
    if marker in text:
        return
    start_marker = "  useEffect(() => {\n    if (!asyncQueryEngine) return;\n"
    end_marker = "  }, [asyncQueryEngine, catalogGenerationId, filters, products, queryKey, queryRetryToken, sort]);"
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit("page-zero controller scope: effect start not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit("page-zero controller scope: effect end not found")
    block = text[start:end]
    if block.count("requestControllers.current") != 5:
        raise SystemExit(
            f"page-zero controller scope: expected 5 ref accesses, found {block.count('requestControllers.current')}"
        )
    block = block.replace(
        "    if (!asyncQueryEngine) return;\n",
        "    if (!asyncQueryEngine) return;\n    const controllers = requestControllers.current;\n",
        1,
    ).replace("requestControllers.current", "controllers")
    target.write_text(text[:start] + block + text[end:], encoding="utf-8")


scope_page_zero_controllers()

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

replace_exact_count(
    "web/src/platform/virtualization/virtual-marketplace-adapter.js",
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount };
''',
    '''      return { start: 0, end: 0, items: [], topSpacer: loaded.startPx, bottomSpacer: Math.max(0, totalHeight - loaded.startPx), totalCount: this.totalCount, ariaRowCount: this.totalCount, renderedCount: 0 };
''',
    2,
    "empty and offscreen virtual window metrics",
)
